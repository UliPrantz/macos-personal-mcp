# 0013: One default Mail search with explicit legacy fallback

Status: implemented, SDK-verified and desktop-verified, 24 October 2026. See
STATUS.md and decision 0014 for actual search-to-read activation evidence.

## Decision

The owner identified ambiguity in two default search tools returning different
answers, then authorized the combination most likely to produce useful results.
Version 0.3.0 uses one canonical `mail_search` over native subject, sender and body
data. It removes `mail_search_native` and moves the old FTS implementation to
`mail_search_legacy`, available only with `--enable-legacy-mail-search` at startup.
Disabled legacy calls are rejected as well as omitted from discovery. The default
registry has 16 read tools, or 19 with writes; legacy opt-in adds one tool.

This supersedes decision 0012's choice to expose both search implementations by
default. Its native format, identity, deadline, MIME and coverage limits continue
to apply. Send/create approval, read-only mode, native account access and installed
registration remain unchanged. There is no new provider connection or OS grant.

## Unified matching contract

`search_fields` defaults to `subject`, `sender`, `body` and accepts a nonempty,
nonduplicated subset. Each AND predicate can be satisfied in any selected field;
an exact quoted phrase must occur entirely within one field. A subject token and
a body token can therefore satisfy a query together without inventing a phrase
across the boundary. Matching uses NFC/casefold with accents preserved. Quote
addresses and punctuation-bearing text, for example
`{"query":"\"person@example.com\"","search_fields":["sender"]}`.
Bounded single-word ASCII fuzzy spelling
remains optional; Boolean operators and semantic search remain unsupported.

Read and match selected headers first. Keep header-proven positives without
requiring their bodies. For unresolved rows, derive native candidates from the
query predicates still unmatched in headers, so a header token cannot incorrectly
be required in the body index. At most 500 messages still requiring body matching
use original MIME; larger unresolved sets use guarded native candidates and bounded
missing/pending exceptions. Header-only queries require neither MIME nor Spotlight.
If all rows are proven by headers, a search uses only the catalogue even above 500
rows, within the existing catalogue bound. Physical copies remain distinct and
results remain newest-first.

The result version is `native-mail-v2`. Each hit identifies observed supporting
`matched_fields`, a bounded normalized `excerpt`, and its `excerpt_field`.
Excerpts use normalized text rather than applying normalized offsets to original
Unicode. These fields describe evidence actually checked, not every field that
might match. `searched_headers` and `header_matches` distinguish metadata work
and metadata-proven positives from `searched_bodies` and body coverage. Existing
partial/unavailable/unsearched counts, errors and snapshot pagination remain.
`execution_complete` does not certify archive recall; `exhaustive` remains false.

Native format/profile failures remain explicit failures for body-search requests;
they do not silently reduce the search to headers. An explicit header-only field
selection remains independent of Spotlight. Per-body failures retain verified
header positives alongside the incomplete-body diagnostics.

## Legacy lifecycle and migration

Legacy FTS retains its public Mail RFC-source ingestion, exact scope, explicit
resumable `index` maintenance, complete-ingestion guard and 30-minute plus current
inventory freshness checks. It can help when direct native files or their format
are unavailable. No search silently builds or refreshes an index, changes backend,
or unions incompatible results. No old cache is deleted by this change.

Its Boolean/column queries, combined metadata matching, accent folding, BM25
ranking, excerpts and plain/HTML alternative handling are different semantics,
not a second measurement of unified search completeness. They do not justify a
second default model-facing search engine.

Clients must reload and rediscover the version 0.3.0 schema. Old native callers
change `mail_search_native` to `mail_search`, using `search_fields=["body"]` when
they need the former body-only behavior. Old FTS callers explicitly enable and
call `mail_search_legacy`. Reusing the canonical name is a documented breaking
change, not an FTS-compatible alias. The versioned result makes the contract
observable. Actual desktop readback remains separate from SDK verification.
