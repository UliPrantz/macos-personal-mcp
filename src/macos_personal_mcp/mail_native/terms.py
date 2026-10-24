"""Bounded observed BurstTrie and posting formats, independently implemented."""

import mmap
import re
import unicodedata
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path

from macos_personal_mcp.mail_native.alphabet import ALPHABET, INVERSE
from macos_personal_mcp.mail_native.checkpoint import Checkpoint, Header
from macos_personal_mcp.mail_native.common import Budget, Buffer, be64, leb, u32, variable
from macos_personal_mcp.process import NativeError

MASK = (1 << 62) - 1


def encode(word: str) -> bytes:
    return unicodedata.normalize("NFD", word).encode().translate(ALPHABET)


def fold(data: bytes) -> bytes:
    return bytes(b + 1 if 46 <= b <= 97 and not b & 1 else b for b in data)


@dataclass(frozen=True)
class Term:
    value: int
    compacted: bool


class Segment:
    def __init__(
        self, paths: dict[str, Path], info: Header, budget: Budget, stack: ExitStack
    ) -> None:
        self.info, self.budget = info, budget
        self.maps: dict[str, mmap.mmap] = {}
        for name, path in paths.items():
            if name == "indexHead":
                continue
            stream = stack.enter_context(path.open("rb"))
            size = path.stat().st_size
            if not 0 < size <= 2_000_000_000:
                raise NativeError(
                    "native_format", "Native mapped file exceeds compatibility bounds"
                )
            self.maps[name] = stack.enter_context(
                mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ)
            )

    def bucket(self, number: int, prefix: bytes) -> list[tuple[bytes, Term]]:
        data = self.maps["indexArrays"]
        offset = number * 64
        if offset < 0 or offset + 8 > len(data):
            raise NativeError("native_format", "Native trie bucket is out of bounds")
        used = int.from_bytes(data[offset : offset + 2], "little")
        pos, end = offset + 8, offset + 8 + used
        if end > len(data):
            raise NativeError("native_format", "Native trie bucket is truncated")
        previous = b""
        posting = position = 0
        result: list[tuple[bytes, Term]] = []
        while pos < end:
            self.budget.check()
            length, pos = variable(data, pos, end)
            common, pos = variable(data, pos, end)
            if length + common > 1100 or common > len(previous) or pos + length > end:
                raise NativeError("native_format", "Invalid native front-coded suffix")
            suffix = previous[:common] + data[pos : pos + length]
            previous, pos = suffix, pos + length
            value, pos = variable(data, pos, end)
            if self.info.flags & 4:
                posting += value
                delta, pos = variable(data, pos, end)
                position += delta
                if posting >= len(self.maps["indexPostings"]) or (
                    delta and position >= len(self.maps["indexPositions"])
                ):
                    raise NativeError(
                        "native_format", "Compacted native offsets exceed companion files"
                    )
                term = Term(posting, True)
            else:
                term = Term(value, False)
            result.append((prefix + suffix, term))
        return result

    def terms(self, word: str) -> set[Term]:
        target = fold(encode(word))
        if not target:
            raise NativeError("invalid_query", "Empty native token")
        stack = [(3, 1, b"")]
        seen: set[tuple[int, int]] = set()
        result: set[Term] = set()

        def emit(token: bytes, term: Term) -> None:
            folded = fold(token)
            if not folded.startswith(target):
                return
            if folded == target or folded.endswith(b"\x01\x02"):
                result.add(term)
                return
            raw = token.translate(INVERSE)
            if any(b < 32 for b in raw):
                return
            remainder = token[len(target) :].translate(INVERSE).decode("utf-8", errors="strict")
            if remainder and unicodedata.category(remainder[0])[0] not in {"L", "N", "M"}:
                result.add(term)

        while stack:
            self.budget.check()
            kind, number, prefix = stack.pop()
            if (kind, number) in seen or len(seen) >= 10000 or len(prefix) > 1100:
                raise NativeError("search_limit", "Native trie cycle or traversal limit")
            seen.add((kind, number))
            if kind == 0:
                for token, term in self.bucket(number, prefix):
                    emit(token, term)
                continue
            data = self.maps["indexDirectory" if kind == 3 else "indexCompactDirectory"]
            offset = number * (1028 if kind == 3 else 4)
            terminal = u32(data, offset)
            if terminal and len(prefix) >= len(target):
                if self.info.flags & 4:
                    if terminal & 1:
                        raise NativeError("native_format", "Invalid compacted trie terminal")
                    for token, term in self.bucket(terminal >> 1, prefix):
                        emit(token, term)
                else:
                    emit(prefix, Term(terminal, False))
            if len(prefix) < len(target):
                byte = target[len(prefix)]
                allowed = [byte, byte - 1] if 47 <= byte <= 97 and byte & 1 else [byte]
            else:
                allowed = range(256)
            if kind != 3 and offset + 38 > len(data):
                raise NativeError("native_format", "Truncated compact trie node")
            bitmap = int.from_bytes(data[offset + 4 : offset + 36], "little") if kind != 3 else 0
            for byte in allowed:
                if kind == 3:
                    desc = u32(data, offset + 4 + 4 * byte)
                else:
                    if not bitmap >> byte & 1:
                        continue
                    rank = (bitmap & ((1 << byte) - 1)).bit_count()
                    desc = u32(data, offset + 38 + 4 * rank)
                if not desc:
                    continue
                if desc & 3 == 1:
                    child: tuple[int, int] = 1, desc >> 2
                elif desc & 7 == 3:
                    child = 3, desc >> 3
                elif not desc & 1:
                    child = 0, desc >> 1
                else:
                    raise NativeError("native_format", "Unknown native trie pointer")
                stack.append((child[0], child[1], prefix + bytes([byte])))
            if len(result) > 2000:
                raise NativeError("search_limit", "Native token expansion exceeds bound")
        return result

    def postings(self, term: Term) -> set[int]:
        raw = (
            term.value
            if term.compacted
            else int.from_bytes(self.take("indexTermIds", term.value * 8, 8), "little")
        )
        offset = raw & MASK
        visited: set[int] = set()
        docs: set[int] = set()
        data = self.maps["indexPostings"]
        limit, index, capacity = self.info.posting_regions

        def region_end(pos: int) -> int:
            end = limit if pos < limit else capacity if index <= pos < capacity else 0
            if not 0 < end <= len(data):
                raise NativeError("native_format", "Posting points outside committed arenas")
            return end

        while offset:
            self.budget.check()
            if offset in visited or len(visited) > 100000:
                raise NativeError("native_format", "Native posting link cycle or limit")
            visited.add(offset)
            end = region_end(offset)
            link, pos = leb(data, offset, end)
            following = (link >> 1) & MASK
            if link & 1:
                size, pos = leb(data, pos, end)
                stop = pos + size
                if stop > end:
                    raise NativeError("native_format", "Posting chunk crosses committed arena")
                while pos < stop:
                    self.budget.check()
                    found, pos, terminal = posting_chunk(
                        data, pos, stop, self.info.documents, self.budget
                    )
                    docs.update(found)
                    if terminal:
                        break
            else:
                value, pos = leb(data, pos, end)
                doc = value >> 1
                frequency = 1
                if not value & 1:
                    frequency, pos = leb(data, pos, end)
                if not frequency:
                    update, pos = leb(data, pos, end)
                    if update not in {0, 1, 2}:
                        raise NativeError("native_format", "Unsupported native posting update")
                if doc:
                    check_doc(doc, self.info.documents)
                    docs.add(doc)
            if following == offset:
                break  # Native final record uses a self-link sentinel.
            offset = following
        return docs

    def take(self, name: str, offset: int, size: int) -> bytes:
        data = self.maps[name]
        if offset < 0 or offset + size > len(data):
            raise NativeError("native_format", "Native table offset exceeds file")
        return data[offset : offset + size]

    def active_oids(self, docs: set[int] | None = None) -> set[int]:
        result: set[int] = set()
        groups, ids = self.maps["indexGroups"], self.maps["indexIds"]
        if docs is None:
            # C-level scan skips the millions of inactive native allocation slots.
            # Header document count, not mmap allocation length, bounds the scan.
            self.budget.check(self.info.documents)
            selected = (
                hit.start()
                for hit in re.compile(rb"[^\x00\x20]").finditer(groups, 1, self.info.documents)
            )
        else:
            selected = iter(docs)
        for doc in selected:
            self.budget.check()
            check_doc(doc, self.info.documents)
            if groups[doc] & 0xDF:
                result.add(be64(ids, 8 * doc))
        return result


def check_doc(doc: int, maximum: int) -> None:
    if not 0 < doc < maximum:
        raise NativeError("native_format", "Native posting document exceeds checkpoint bounds")


def posting_chunk(
    data: Buffer, pos: int, end: int, maximum: int, budget: Budget
) -> tuple[set[int], int, bool]:
    first, pos = leb(data, pos, end)
    if not first:
        return set(), pos, True
    second, pos = leb(data, pos, end)
    docs: set[int] = set()
    if first > second:
        check_doc(first, maximum)
        docs.add(first)
        delta = second
        while delta:
            budget.check()
            if delta >= first:
                raise NativeError("native_format", "Invalid native posting delta")
            first -= delta
            check_doc(first, maximum)
            docs.add(first)
            delta, pos = leb(data, pos, end)
    elif first == second:
        update, pos = leb(data, pos, end)
        if update not in {0, 1, 2}:
            raise NativeError("native_format", "Unknown native posting update")
        check_doc(first, maximum)
        docs.add(first)
        if update:
            while True:
                budget.check()
                delta, pos = leb(data, pos, end)
                if not delta:
                    break
                if delta >= first:
                    raise NativeError("native_format", "Invalid native update delta")
                first -= delta
                docs.add(first)
    else:
        check_doc(first, maximum)
        if second > maximum or pos >= end:
            raise NativeError("native_format", "Native posting range exceeds bounds")
        if data[pos]:
            length = second - first
            size = (length + 7) // 8
            if pos + size > end:
                raise NativeError("native_format", "Truncated native posting bitmap")
            bits = int.from_bytes(data[pos : pos + size], "little")
            pos += size
            if bits >> length:
                raise NativeError("native_format", "Native bitmap has nonzero padding")
            while bits:
                budget.check()
                bit = (bits & -bits).bit_length() - 1
                docs.add(second - 1 - bit)
                bits &= bits - 1
        else:
            pos += 1
            cursor = second
            while True:
                budget.check()
                delta, pos = leb(data, pos, end)
                if delta > cursor - first:
                    raise NativeError("native_format", "Native complementary gap exceeds range")
                low = first if not delta else cursor - delta + 1
                budget.check(cursor - low)
                docs.update(range(low, cursor))
                if not delta:
                    break
                cursor -= delta
    return docs, pos, False


class Terms:
    def __init__(self, view: Checkpoint, budget: Budget, stack: ExitStack) -> None:
        self.segments = [
            Segment(paths, view.headers[base], budget, stack) for base, paths in view.paths.items()
        ]

    def candidates(self, word: str) -> set[int]:
        result: set[int] = set()
        for segment in self.segments:
            docs: set[int] = set()
            variants = {word}
            if not word.isascii():
                variants.update((word.lower(), word.upper(), word.casefold()))
            if "ss" in word.lower():
                variants.add(word.lower().replace("ss", "ß"))
            for variant in variants:
                for term in segment.terms(variant):
                    docs.update(segment.postings(term))
            result.update(segment.active_oids(docs))
        return result

    def active(self) -> set[int]:
        result: set[int] = set()
        for segment in self.segments:
            result.update(segment.active_oids())
        return result


def edit_row(row: list[int], char: str, query: str) -> list[int]:
    result = [row[0] + 1]
    for index, wanted in enumerate(query, 1):
        result.append(min(result[-1] + 1, row[index] + 1, row[index - 1] + (char != wanted)))
    return result


def ascii_character(byte: int) -> str | None:
    char = chr(INVERSE[byte])
    return char.lower() if char.isascii() and char.isalnum() else None


def fuzzy_terms(segment: Segment, query: str, distance: int) -> dict[str, set[Term]]:
    """Edit-distance-pruned native vocabulary traversal; no vocabulary copy."""
    stack: list[tuple[int, int, str, list[int]]] = [(3, 1, "", list(range(len(query) + 1)))]
    seen: set[tuple[int, int]] = set()
    found: dict[str, set[Term]] = {}

    def collect(word: str, term: Term, row: list[int]) -> None:
        if row[-1] <= distance:
            found.setdefault(word, set()).add(term)
            if len(found) > 100:
                raise NativeError(
                    "search_limit", "Native fuzzy spelling expansion exceeds 100 words"
                )

    def bucket(number: int, prefix: str, row: list[int]) -> None:
        for encoded, term in segment.bucket(number, b""):
            segment.budget.check()
            if not len(query) - distance <= len(prefix) + len(encoded) <= len(query) + distance:
                continue
            chars: list[str] = []
            next_row = row
            for byte in encoded:
                char = ascii_character(byte)
                if char is None:
                    break
                chars.append(char)
                next_row = edit_row(next_row, char, query)
                if min(next_row) > distance:
                    break
            else:
                collect(prefix + "".join(chars), term, next_row)

    while stack:
        segment.budget.check()
        kind, number, prefix, row = stack.pop()
        if (kind, number) in seen or len(seen) >= 5000:
            raise NativeError("search_limit", "Native fuzzy trie cycle or node limit")
        seen.add((kind, number))
        if kind == 0:
            bucket(number, prefix, row)
            continue
        data = segment.maps["indexDirectory" if kind == 3 else "indexCompactDirectory"]
        offset = number * (1028 if kind == 3 else 4)
        terminal = u32(data, offset)
        if terminal and row[-1] <= distance:
            if segment.info.flags & 4:
                if terminal & 1:
                    raise NativeError("native_format", "Unsupported compact fuzzy terminal")
                bucket(terminal >> 1, prefix, row)
            else:
                collect(prefix, Term(terminal, False), row)
        if len(prefix) >= len(query) + distance:
            continue
        bitmap = int.from_bytes(data[offset + 4 : offset + 36], "little") if kind != 3 else 0
        for byte in range(256):
            char = ascii_character(byte)
            if char is None:
                continue
            if kind == 3:
                desc = u32(data, offset + 4 + 4 * byte)
            else:
                if not bitmap >> byte & 1:
                    continue
                rank = (bitmap & ((1 << byte) - 1)).bit_count()
                desc = u32(data, offset + 38 + 4 * rank)
            if not desc:
                continue
            next_row = edit_row(row, char, query)
            if min(next_row) > distance:
                continue
            if desc & 3 == 1:
                child = 1, desc >> 2
            elif desc & 7 == 3:
                child = 3, desc >> 3
            elif not desc & 1:
                child = 0, desc >> 1
            else:
                raise NativeError("native_format", "Unknown native fuzzy trie pointer")
            stack.append((child[0], child[1], prefix + char, next_row))
    return found


def fuzzy_candidates(terms: Terms, query: str, distance: int) -> set[int]:
    result: set[int] = set()
    vocabulary: set[str] = set()
    for segment in terms.segments:
        docs: set[int] = set()
        for word, variants in fuzzy_terms(segment, query, distance).items():
            vocabulary.add(word)
            if len(vocabulary) > 100:
                raise NativeError("search_limit", "Native fuzzy expansion exceeds 100 words")
            for term in variants:
                docs.update(segment.postings(term))
        result.update(segment.active_oids(docs))
    return result
