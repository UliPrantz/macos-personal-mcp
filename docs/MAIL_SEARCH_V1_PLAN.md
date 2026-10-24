# Mail search V1 implementation handoff

> Implementation update, 24 October: the owner authorized execution. Version 0.2.0
> implements the native hybrid as `mail_search_native`; see decision
> [0012](decisions/0012-native-hybrid-mail-search.md) and [STATUS.md](STATUS.md).
> Research/deferred wording below describes the earlier planning checkpoint.
> New-tool desktop discovery/readback is pending connection reload.


Prepared 24 October 2026. **Plan only: the owner deferred production implementation
to a cheaper model.** No backend switch or runtime activation accompanies this
file. Read AGENTS.md, CODEX_HANDOFF.md, STATUS.md,
[the research results](EXPERIMENTS_NATIVE_MAIL.md) and
[the format handoff](NATIVE_MAIL_INDEX_FORMAT.md) first.

## Recommendation and product bar

Use a native hybrid: Envelope Index selects current metadata/date scopes; small
scopes read their original MIME bodies directly, while large/all-history scopes
use Apple's existing Core Spotlight term index and verify candidate bodies.
Maintain a process-memory identity/coverage map for the indexed route and inspect
bounded missing/pending exceptions. **Do not build a separate full-body database
by default.**

This directly addresses the owner's recent-mail priority. Reading and checking
the fixed week's 401 bodies took 1.45 seconds; three days/185 bodies took 0.63
seconds, with zero identity/read failures and unchanged flags. These are warm
filesystem research timings, not cold disk or desktop MCP benchmarks. An initial
small-scope threshold of 500 rows is a proposal to validate, with byte/time bounds;
it is not permission to turn an unrestricted archive request into a full scan.

This recommendation supersedes the earlier incremental-FTS-first plan because the
extended investigation actually recovered native body-word search. It is a
proposed next implementation, not a claim that the installed MCP uses it. Current
scoped FTS remains available and unchanged during rollout.

The owner's product criterion is practical parity with Apple Mail, with strongest
coverage for recent mail, especially the last week. Small historical gaps are
acceptable. Do not reject the native approach just because a few old local rows
are absent. Conversely, distinguish measured recall from a mathematical guarantee:
metadata presence alone does not prove that every body word is indexed. Report
known gaps and incomplete searches honestly without blocking useful results.

Must support keywords, exact phrases and aware date ranges (for example, the past
three days). Fuzzy spelling is a demonstrated extension; semantic search is a
separate desired feature with no proven native-vector query route. Do not make
semantic search or complete arbitrary-language tokenization a V1 dependency.

## Implementation sequence

1. **Freeze the compatibility and query contracts.** Add a decision record for
   activating the new backend; the current research recommendation is provisional.
   Define body-token AND semantics and quoted normalized exact phrases, case and
   Unicode behavior, metadata filters, stable ordering and pagination. Preserve
   lower-inclusive/upper-exclusive date bounds, using aware instants; document
   received-date versus sent-date semantics. A host resolves “past three days” to
   concrete instants. Do not silently reuse FTS5 Boolean syntax with different
   meaning. Existing callers must receive an explicit version/capability change.

2. **Build typed read-only native adapters.** Validate Mail schema/store identity
   and the supported Spotlight format/OS profile. Open SQLite with `mode=ro` and
   normal WAL behavior, never `immutable=1`. Implement bounded dictionary,
   posting, checkpoint and narrow metadata readers from the documented observed
   format. Validate offsets, lengths, cycles, decompression limits, document
   counts, reserved slots, active groups and integer overflow. Unknown forms
   produce unsupported/partial results. Preserve original native identities and
   distinct physical mailbox copies.

3. **Acquire a coherent persisted view only for the indexed route.** First count
   the filtered SQL scope and select the small direct-read route described below
   when appropriate. A dirty, unsupported or unavailable Spotlight store must not
   block an otherwise valid bounded direct scan. For the indexed route, use the validated shadow-file mapping,
   requiring matching current/shadow generations and prefix counts. Read all
   relevant generations. Observe full headers/state and opened-file identity
   before/after work. Check catalogue device/inode and SQLite data_version too.
   Reject changed or stable-but-lagging views; never treat them as empty searches.
   Use one absolute deadline across acquisition, every segment, expansion,
   postings, body reads and retries. At most one bounded fresh-view retry is a
   reasonable initial policy; retain parent cancellation, kill and child reaping.

4. **Select the bounded route, then reconcile indexed coverage on demand.** Count
   the filtered native scope cheaply. For a small scope, verify every eligible
   local body directly under the total deadline, with explicit unavailable/partial
   MIME counts. This bypasses index lag and tokenization gaps without a body cache
   or full metadata inventory. For a large scope, decode OID→Mail ROWID identity fields
   from both native metadata stores. Keep only identity tuples, native update
   versions, block fingerprints and diagnostics in process memory. Hash captured
   compressed blocks and actual auxiliary-map bytes; reuse unchanged decoded
   blocks. Rebuild the reference set each refresh to observe deletions/rebuilds.
   Intersect active checkpoint slots with fresh scoped SQL rows. Date/account/
   mailbox filters must reduce candidates before expensive MIME reads. Missing
   metadata/slots, body-indexing-pending rows and bounded missing-RFC-ID rows
   become explicit fallback IDs. The fixed week has two such exceptional messages:
   one pending body and one missing RFC ID; the latter is also missed by Mail UI.
   Do not use a last-received-date watermark as proof of no edits or deletions.

5. **Verify keyword and phrase results in original bodies.** Query normalized
   terms, validated compound aliases and punctuation boundaries with shared work
   budgets. Native postings can include headers/attachments, so verify final
   body-only predicates after identity-checked MIME decoding. For phrases choose
   selective native anchor terms and verify exact normalized order/spacing in
   their candidates; decoding all native position formats is not required for
   V1. Prune attachment subtrees, including attached RFC messages. Handle
   multipart alternatives deliberately and validate `.partial.emlx` completeness.
   Preserve HTML text-node/link boundaries without manufacturing merged words;
   preserve contractions as documented tokens. Otherwise a whole-word verifier
   can discard a correct native hit. Add explicit synthetic adjacent-label and
   contraction cases, rather than treating text extraction as rendering parity.
   Use the existing hardened production source/MIME behavior, not the permissive
   research body helper wholesale.
   Strict RFC equality requires both identities to be nonempty. For malformed or
   missing RFC Message-IDs, a separately tested exact native binding can
   use account, mailbox, remote UID, local file/row identity and matching native
   timestamps/conversation metadata. Never use lossy text normalization alone
   as identity proof. Keep this a distinct validated path, otherwise report the
   message unavailable rather than silently returning an unrelated body.

6. **Search bounded exceptions and expose uncertainty.** Try local bodies for
   missing/pending rows, newest first, within a measured total deadline/count
   budget. Optional public Mail source fallback remains identity-checked and
   bounded; no provider APIs or UI automation. Do not alter read flags or restore
   them speculatively. Return useful verified matches even when old exceptions
   remain. Distinguish catalogue rows, native-covered rows, pending rows,
   unavailable bodies, decoder/expansion limits and unsearched candidates.
   A partial zero means no match in the searched subset. Native checkpoint
   coverage and sampled recall must not be labeled exhaustive body completeness.
   Separate completed execution of a native-index query from exhaustive archive
   coverage in the response schema; expose backend and observation/checkpoint
   provenance. Avoid making a useful native search unusable merely because
   exhaustive word-level completeness cannot be established from native metadata.

7. **Integrate the MCP without a background service.** Discover capabilities
   cheaply at startup; build no metadata inventory until the first body query.
   The measured warm coverage cache requires a living process. Current disposable
   per-call workers would pay the cold inventory cost each time. The Apache-only
   full inventory measured 11.07 seconds cold under research load and 0.97–1.07
   seconds warm. The earlier ~2.4 / 0.4-second inventory uses a GPL research helper
   and is not the demonstrated performance of that replacement. Small-scope direct
   reads avoid this startup cost. Give a first large-scope query an explicit
   sufficient deadline/progress contract; do not hide repeated cold builds behind
   warm benchmark claims. If warm targets require reuse, use a lazily created supervised
   read worker tied to the STDIO connection, with bounded framed I/O, serialized
   requests, cancellation/kill/reap and clean restart. It is not a daemon or a
   scheduled worker. Losing its cache changes latency only, never semantics.
   Keep native mmap parsing in the supervised child: concurrent truncation can
   fault a mapping before a final consistency check, and must not kill the MCP
   protocol process. Measure resident memory as well as latency.
   Do not keep bodies/snippets or queries as hidden process history. Keep stdout
   protocol-only and diagnostics redacted. Freeze cursor scope/checkpoint or
   reject pagination after a changed generation.

8. **Add fuzzy spelling after core queries pass.** The research trie traversal
   supports edit-distance pruning without a copied vocabulary. Keep node/time/
   result limits and expose partial expansion. Verify candidate spelling and
   original bodies; label fuzzy results. Do not present spelling distance as
   semantic similarity or reuse native vectors with an unrelated encoder.
   The demonstrated prototype accepts ASCII alphanumeric words only; Unicode
   spelling distance is additional work, distinct from verified Unicode keywords.

## Acceptance before activation

- Synthetic tests cover dictionary node/bucket forms, NFD/umlauts, case,
  compounds, apostrophes, malformed pointers, cycles, posting forms and update
  records, inactive/deleted/reserved slots and compacted live generations.
- Checkpoint tests cover changing and stable-lagging headers, prefix-count
  mismatches, source replacement, corrupt/truncated files, metadata-map changes,
  changed cached blocks, stale diagnostic reuse, cancellation and bounded retry.
  Source failure must never become a successful empty result or mass deletion.
- Body tests cover header-only and attachment-only negatives, attached RFC
  subtrees, HTML/plain alternatives, long bodies, charset/transfer decoding,
  unavailable/incomplete MIME, identity mismatch, wrong-order phrases and date
  boundary negatives. Preserve native flags.
- Reproduce the private owner examples and controlled self-email without sending
  again. Validate recent-week positive/negative queries with explicit denominators
  and missing reasons, then a diverse older corpus. Small old gaps are acceptable;
  no known fresh-message gap may be silently ignored.
- Demonstrate new arrivals, deletions/moves, native rebuild/compaction and an
  indexing-pending exception through natural updates or synthetic fixtures.
  Never mutate the owner's mail merely to exercise a test.
- Benchmark cold process startup, cold first query/coverage, warm query and real
  MCP end-to-end separately. The research Python timings are not MCP SDK/desktop
  measurements. Targets remain index p95 ≤1 second and warm MCP p95 ≤2 seconds;
  report realistic body-heavy query limits and any measured tradeoff.
- Use the official SDK for real STDIO tests, then the actual desktop host after
  saving/pushing. Verify native-storage access from that process. Ask for a reload
  only when a verified implementation is ready; no reload is needed for this plan.
- Run Ruff format/check, strict Pyright, synthetic/protocol tests and required CI.
  Update README, specification, decision record and STATUS. Use unsigned Codex
  identity, push to the verified project origin. Send/calendar approval
  policy and the exclusion of invitations remain unchanged.

## Fallback if native compatibility fails

Retain the existing explicit-scope FTS route. A future owner-selected broader
cache can use one owner-only SQLite FTS5 database over native catalogue/MIME data,
with incremental upserts and successful-inventory-only deletion reconciliation.
Track source fingerprints and unavailable reasons; do not append solely by date.
Make persistent-cache maintenance explicit and resumable with honest annotations.
Use no scheduler/provider connection. This is the practical alternative if native
format maintenance proves disproportionate, not additional work required before
trying the demonstrated native route.

## Saved research and boundaries

Production source/tests remain at `pre-release revision`. Research readers and private fixtures
are under `.local/native-index-two-hour-20261024/` and
`.local/known-mail-examples-20261024/`; the format handoff maps their roles.
The interrupted earlier incremental implementation named by
`.local/incremental-mail-draft-backup.txt` is unverified and inactive. Do not apply
it or the older direct-store prototype wholesale. Never commit private messages,
addresses, native identifiers or database copies.

Use an explicitly compatible metadata dependency. The mac_apt helper used in
research is GPL-3.0-or-later despite its repository's MIT root license. A narrow
Apache-2.0 dtformats-based identity reader was independently demonstrated on all
401 recent-week identities and a full 42,548-identity inventory, including native
update versions. Retain upstream attribution and lock dependencies;
no research-only package installs, decompiler, binary cache extraction or network
access belongs in the runtime.
