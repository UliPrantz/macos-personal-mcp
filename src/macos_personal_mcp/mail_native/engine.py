"""On-demand hybrid search. No body cache, native writes or background indexing."""

import platform
import re
import time
import unicodedata
from collections import Counter
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from macos_personal_mcp.mail_native.catalogue import Catalogue, Row, snapshot
from macos_personal_mcp.mail_native.checkpoint import ROOT, Checkpoint
from macos_personal_mcp.mail_native.common import Budget
from macos_personal_mcp.mail_native.contracts import (
    NativeMatch,
    NativeSearch,
    NativeSearchResult,
    SearchField,
)
from macos_personal_mcp.mail_native.identities import Inventory
from macos_personal_mcp.mail_native.terms import Terms, edit_row, fuzzy_candidates
from macos_personal_mcp.process import NativeError

TOKEN = re.compile(r"[^\W_]+(?:['\u2019][^\W_]+)*", re.UNICODE)


def normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


@dataclass(frozen=True)
class Evidence:
    predicates: frozenset[int]
    spellings: frozenset[str]
    excerpt: str


class Query:
    def __init__(self, query: str, fuzzy_distance: int = 0) -> None:
        self.fuzzy_distance = fuzzy_distance
        self.spellings: set[str] = set()
        self.predicates: list[re.Pattern[str]] = []
        self.predicate_anchors: list[list[str]] = []
        anchors: list[str] = []
        position = 0
        for match in re.finditer(r'"([^"\n]+)"|([^\s"]+)', query):
            if query[position : match.start()].strip():
                raise NativeError("invalid_query", "Unbalanced quotes or invalid query syntax")
            position = match.end()
            phrase, bare = match.groups()
            text = normalized(phrase or bare)
            words = TOKEN.findall(text)
            if not words or (
                bare is not None and (words != [text] or bare in {"AND", "OR", "NOT", "NEAR"})
            ):
                raise NativeError(
                    "invalid_query",
                    "Use tokens and quoted phrases (quote email addresses); FTS operators are unsupported",
                )
            self.predicates.append(re.compile(r"(?<!\w)" + re.escape(text) + r"(?!\w)"))
            # Apostrophe-bearing tokens may use split native terms. A constituent
            # supplies candidates; the full original token remains mandatory.
            words = re.findall(r"[^\W_]+", unicodedata.normalize("NFC", phrase or bare or ""))
            self.predicate_anchors.append(words)
            anchors.extend(words)
        if query[position:].strip() or not self.predicates or len(anchors) > 40:
            raise NativeError("invalid_query", "Require 1-40 words with balanced phrase quotes")
        self.anchors = sorted(set(anchors), key=lambda word: (-len(word), word))[:3]
        self.anchor = self.anchors[0]

    def matches(self, body: str, budget: Budget | None = None) -> bool:
        evidence = self.evidence(body, budget)
        self.spellings = set(evidence.spellings)
        return len(evidence.predicates) == len(self.predicates)

    def evidence(self, body: str, budget: Budget | None = None) -> Evidence:
        text = normalized(body)
        positions: list[int] = []
        found: set[int] = set()
        spellings: set[str] = set()
        if self.fuzzy_distance:
            seen: set[str] = set()
            for match in TOKEN.finditer(text):
                word = match.group()
                if budget is not None:
                    budget.check()
                if word in seen:
                    continue
                seen.add(word)
                if (
                    not word.isascii()
                    or not word.isalnum()
                    or abs(len(word) - len(self.anchor)) > self.fuzzy_distance
                ):
                    continue
                row = list(range(len(self.anchor) + 1))
                for char in word:
                    row = edit_row(row, char, self.anchor.lower())
                    if min(row) > self.fuzzy_distance:
                        break
                else:
                    if row[-1] <= self.fuzzy_distance:
                        spellings.add(word)
                        positions.append(match.start())
                        found.add(0)
        else:
            for index, predicate in enumerate(self.predicates):
                if budget is not None:
                    budget.check()
                match = predicate.search(text)
                if match is not None:
                    found.add(index)
                    positions.append(match.start())
        # Offsets refer to normalized text, so excerpts deliberately use that
        # same representation (case folding can change Unicode string length).
        start = max(0, min(positions, default=0) - 60)
        end = min(len(text), start + 300)
        excerpt = ("…" if start else "") + text[start:end] + ("…" if end < len(text) else "")
        return Evidence(frozenset(found), frozenset(spellings), excerpt if found else "")

    def anchors_for(self, missing: frozenset[int]) -> list[str]:
        words = {word for index in missing for word in self.predicate_anchors[index]}
        return sorted(words, key=lambda word: (-len(word), word))[:3]


def matched_message(row: Row, evidence: dict[SearchField, Evidence]) -> NativeMatch:
    fields: list[SearchField] = [field for field, item in evidence.items() if item.predicates]
    chosen: SearchField = (
        "body" if "body" in fields else "subject" if "subject" in fields else "sender"
    )
    return row.match().model_copy(
        update={
            "matched_fields": fields,
            "excerpt": evidence[chosen].excerpt,
            "excerpt_field": chosen,
        }
    )


class Engine:
    def __init__(self, mail_root: Path | None = None, index_root: Path = ROOT) -> None:
        self.require_host_profile = mail_root is None
        self.mail_root = mail_root or Path.home() / "Library/Mail/V10"
        self.index_root = index_root
        self.inventory = Inventory()

    def search(self, request: NativeSearch, deadline: float) -> NativeSearchResult:
        started = time.monotonic()
        budget = Budget(deadline, remaining=20_000_000)
        query = Query(request.query, request.fuzzy_distance)
        for attempt in range(2):
            budget.check()
            try:
                result = self.once(request, query, budget)
                return result.model_copy(update={"elapsed_ms": (time.monotonic() - started) * 1000})
            except NativeError as error:
                if error.code not in {"source_changed", "checkpoint_not_ready"} or attempt:
                    raise
        raise NativeError("source_changed", "Native source changed during both bounded attempts")

    def once(self, request: NativeSearch, query: Query, budget: Budget) -> NativeSearchResult:
        started = time.monotonic()
        catalogue = Catalogue(self.mail_root, budget)
        try:
            rows = catalogue.rows(request)
            matches: dict[int, NativeMatch] = {}
            spellings: set[str] = set()
            header_evidence: dict[int, dict[SearchField, Evidence]] = {}
            missing: dict[int, frozenset[int]] = {}
            predicates = frozenset(range(len(query.predicates)))
            headers: list[SearchField] = [
                field for field in request.search_fields if field != "body"
            ]
            for row in rows:
                budget.check()
                evidence: dict[SearchField, Evidence] = {}
                found: set[int] = set()
                for field in headers:
                    item = query.evidence(row.subject if field == "subject" else row.sender, budget)
                    if item.predicates:
                        evidence[field] = item
                        found.update(item.predicates)
                if predicates <= found:
                    matches[row.local_id] = matched_message(row, evidence)
                    for item in evidence.values():
                        spellings.update(item.spellings)
                elif "body" in request.search_fields:
                    missing[row.local_id] = predicates - found
                    if evidence:
                        header_evidence[row.local_id] = evidence
            header_matches = len(matches)
            body_rows = [row for row in rows if row.local_id in missing]
            covered = exceptions = 0
            checkpoint = ""
            metadata_before = None
            errors: Counter[str] = Counter()
            with ExitStack() as stack:
                view: Checkpoint | None = None
                if not body_rows:
                    backend = "catalogue-only"
                    candidates: list[Row] = []
                elif len(body_rows) <= 500:
                    backend = "direct-mime"
                    candidates = body_rows
                else:
                    backend = "native-spotlight"
                    if self.require_host_profile and platform.mac_ver()[0] != "26.5.2":
                        raise NativeError(
                            "native_profile",
                            "Indexed native search requires the validated macOS 26.5.2 profile; bounded direct scopes remain independent",
                        )
                    view = Checkpoint(self.index_root, budget)
                    terms = Terms(view, budget, stack)
                    identities, metadata_before = self.inventory.refresh(self.index_root, budget)
                    active = terms.active()
                    native_rows = {pair[0] for oid, pair in identities.items() if oid in active}
                    covered = sum(row.local_id in native_rows for row in rows)
                    exceptional = {
                        row.local_id
                        for row in body_rows
                        if row.local_id not in native_rows
                        or not row.body_indexed
                        or not row.message_id
                    }
                    exceptions = len(exceptional)
                    if exceptions > 500:
                        errors["exception_limit"] = exceptions - 500
                        exceptional = set(
                            [row.local_id for row in body_rows if row.local_id in exceptional][:500]
                        )
                    postings: dict[str, set[int]] = {}
                    resolved: dict[str, set[int]] = {}
                    groups: dict[frozenset[int], set[int]] = {}
                    empty = set[int]()
                    for needed in sorted(set(missing.values()), key=lambda item: sorted(item)):
                        budget.check()
                        if request.fuzzy_distance:
                            selected = query.anchor
                            oids = fuzzy_candidates(
                                terms, query.anchor.lower(), request.fuzzy_distance
                            )
                        else:
                            # Header-satisfied words must never be mandatory in
                            # body postings. Select an anchor only among this
                            # group's still-unmet predicates, retaining the
                            # existing nonempty-anchor/stopword behavior.
                            anchors = query.anchors_for(needed)
                            for anchor in anchors:
                                if anchor not in postings:
                                    postings[anchor] = terms.candidates(anchor)
                            choices = [anchor for anchor in anchors if postings[anchor]]
                            if not choices:
                                groups[needed] = empty
                                continue
                            selected = min(choices, key=lambda anchor: len(postings[anchor]))
                            oids = postings[selected]
                        if selected not in resolved:
                            translated: set[int] = set()
                            for oid in oids:
                                budget.check()
                                if oid in identities:
                                    translated.add(identities[oid][0])
                            resolved[selected] = translated
                        # Share resolved posting sets across header masks. Copying
                        # them per mask would amplify memory for long queries.
                        groups[needed] = resolved[selected]
                    candidates = [
                        row
                        for row in body_rows
                        if row.local_id in groups[missing[row.local_id]]
                        or row.local_id in exceptional
                    ]
                    checkpoint = view.digest()
                    if self.inventory.errors:
                        errors["metadata_records_unsupported"] = self.inventory.errors
                scope_key = request.model_copy(
                    update={"offset": 0, "limit": 50, "snapshot": None}
                ).model_dump_json()
                searched = partial = unavailable = consumed = 0
                raw_bytes = 0
                # Useful positives remain available under explicit limits, but a
                # limit must never imply complete/exhaustive execution.
                for row in candidates[:2000]:
                    budget.check()
                    if raw_bytes >= 100_000_000:
                        errors["body_byte_limit"] += 1
                        break
                    consumed += 1
                    try:
                        body, incomplete, size = catalogue.body(row, 100_000_000 - raw_bytes)
                        raw_bytes += size
                        searched += 1
                        partial += incomplete
                        item = query.evidence(body, budget)
                        if missing[row.local_id] <= item.predicates:
                            evidence = dict(header_evidence.get(row.local_id, {}))
                            evidence["body"] = item
                            matches[row.local_id] = matched_message(row, evidence)
                            for item in evidence.values():
                                spellings.update(item.spellings)
                    except NativeError as error:
                        if error.code == "body_byte_limit":
                            consumed -= 1
                            errors[error.code] += 1
                            break
                        if error.code in {"deadline", "source_changed", "search_limit"}:
                            raise
                        errors[error.code] += 1
                        unavailable += 1
                    except OSError, ValueError:
                        errors["body_unavailable"] += 1
                        unavailable += 1
                catalogue.check()
                if view is not None:
                    view.check()
                    if self.inventory.observations(self.index_root) != metadata_before:
                        raise NativeError(
                            "source_changed", "Metadata changed during body verification"
                        )
                unsearched = len(candidates) - consumed + errors.get("exception_limit", 0)
                file_marker = repr(
                    sorted((str(path), observed) for path, observed in catalogue.files.items())
                )
                token = snapshot(rows, checkpoint + scope_key + file_marker)
                if request.snapshot is not None and request.snapshot != token:
                    raise NativeError(
                        "stale_cursor",
                        "Source or query changed; restart pagination from offset zero",
                    )
                ordered = [matches[row.local_id] for row in rows if row.local_id in matches]
                page = ordered[request.offset : request.offset + request.limit]
                budget.check()
                result = NativeSearchResult(
                    backend=backend,
                    search_fields=request.search_fields,
                    fuzzy_distance=request.fuzzy_distance,
                    matched_spellings=sorted(spellings),
                    matches=page,
                    total_matches=len(matches),
                    next_offset=request.offset + len(page)
                    if request.offset + len(page) < len(matches)
                    else None,
                    snapshot=token,
                    catalogue_messages=len(rows),
                    searched_headers=len(rows) if headers else 0,
                    header_matches=header_matches,
                    native_covered=covered,
                    exception_messages=exceptions,
                    candidate_messages=len(candidates),
                    searched_bodies=searched,
                    unavailable_bodies=unavailable,
                    partial_bodies=partial,
                    unsearched_candidates=unsearched,
                    error_counts=dict(errors),
                    execution_complete=not errors and not unsearched and not unavailable,
                    flags_unchanged=True,
                    observed_at=datetime.now(UTC),
                    elapsed_ms=(time.monotonic() - started) * 1000,
                )
                # Account for serialization inside the same absolute deadline.
                result.model_dump_json()
                budget.check()
                return result
        finally:
            catalogue.close()
