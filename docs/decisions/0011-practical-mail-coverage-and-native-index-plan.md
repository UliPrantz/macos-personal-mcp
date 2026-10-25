# 0011: Practical Mail coverage and native-index implementation plan

Status: product acceptance clarification agreed by the owner, 24 October 2026.
Native hybrid implemented in decision 0012; current unified search is defined by
decision 0013. Decision 0005 applies only to the optional legacy FTS backend.

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
for the native implementation. Keep scoped legacy FTS available by opt-in; an
incremental archive cache remains a fallback if native-format compatibility or
maintenance proves disproportionate.

This recommendation involves undocumented on-disk structures. Detect unsupported
formats, source changes and lagging checkpoints and fail explicitly. No native
store writes, private API calls, entitlement changes, process injection, UI
extraction or provider connections are authorized by this decision. Existing
send/calendar approval policy is unchanged and invitations remain excluded.

## Implementation

The initial research and delivery plan have been completed. The durable format
observations are in the [native index reference](../NATIVE_MAIL_INDEX_FORMAT.md),
including provenance and compatibility limits. Decisions 0012/0013 define shipped
behavior; [STATUS.md](../STATUS.md) records actual verification. Semantic-vector
reuse remains unproven and is not part of the current search implementation.
