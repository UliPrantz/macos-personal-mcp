# 0011: Practical Mail coverage and native-index implementation plan

Status: product acceptance clarification agreed by the owner, 24 October 2026.
Native-index backend recommended by research; implementation was then deferred.
The owner subsequently authorized implementation; see decision 0012 and STATUS.md.
Decision 0005 still describes the installed explicit-scope FTS backend.

## Product criterion

Full-body search remains required. Keywords, exact phrases and date ranges are
musts; fuzzy and semantic search would be valuable additions. The owner clarified
that a few missing older emails are acceptable, and that parity with Apple Mail's
own search is the practical standard. Prioritize the last week and recent mail.
Do not reject a working native approach solely for small historical gaps.

This is a product tolerance, not permission to invent coverage or call unknown
results exhaustive. Report known missing/pending/unavailable messages and search
limits. Metadata presence, active document membership, sampled term recall and
whole-body completeness are different measurements. Useful partial results may
ship; a partial zero must not imply that no matching email exists.

## Architecture recommendation

The extended read-only investigation recovered the native character permutation,
term dictionary, posting lists, active document selection and OID-to-Mail identity
mapping. Keyword queries, original-body phrase checks, date filtering and bounded
fuzzy spelling were demonstrated. The initial ten-minute negative was caused by
comparing encoded keys with unencoded text, not evidence that Mail lacked an index.

Prefer a native hybrid: direct identity-checked MIME scans for bounded small scopes
and native indexed candidates plus current catalogue filters/targeted MIME reads
for larger scopes. The entire fixed week (401 messages) was read in 1.45 seconds
warm, avoiding native indexing/tokenization gaps for that decoded text. Keep only
process-memory identity/fingerprint caches, and inspect a bounded missing/pending
exception set directly. Avoid a second full-body database
for this first implementation. Keep the current scoped FTS route available; an
incremental archive cache remains a fallback if native-format compatibility or
maintenance proves disproportionate.

This recommendation involves undocumented on-disk structures. Detect unsupported
formats, source changes and lagging checkpoints and fail explicitly. No native
store writes, private API calls, entitlement changes, process injection, UI
extraction or provider connections are authorized by this decision. Existing
send/calendar approval policy is unchanged and invitations remain excluded.

## Delivery boundary

The owner asked for research and a concrete plan that a cheaper model can
implement. This commit changes documentation only. Research prototypes and
private fixtures remain ignored locally. No runtime switch, tool registration,
permission grant or host reload is part of this work.

Follow [the V1 plan](../MAIL_SEARCH_V1_PLAN.md) and
[the format notes](../NATIVE_MAIL_INDEX_FORMAT.md), including license provenance,
synthetic failure tests and actual SDK/desktop verification before activation.
Semantic-vector reuse is not demonstrated and must not delay V1.
