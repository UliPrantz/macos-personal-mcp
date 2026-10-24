# What other Apple Mail MCPs teach us

Source review and a local metadata experiment, 25 October 2026.

**We found useful improvements and credible faster designs. We did not find a
simpler way to query Apple's private full-body index in the reviewed projects.**
Several fast servers build their own incremental FTS5 index. Others search only
Mail's metadata, scan bodies through AppleScript, or query a separately configured
mail provider. Those are different workloads and trade-offs.

Our native-index work was not based on a nonexistent distinction: Mail's SQLite
**Envelope Index** contains metadata and snippets, while its full-text search
also uses a separate **Core Spotlight** store. We read both, then verify body
matches against original MIME. However, we added avoidable work around those
reads. Avoiding a duplicate body index does not automatically make our search
faster or easier to support across macOS versions.

## Scope and evidence

We inspected pinned source, relevant tests, benchmark scripts and documentation
for the seven projects below. We did not install or run competitor servers on
this Mac, reproduce their published timings, configure provider accounts or copy
implementation code. A separate experiment used only our own read-only metadata
reader and parameterized SQLite queries. No message bodies or account details
are included in this report.

Revisions inspected:

| Project | Commit | Actual search route |
| --- | --- | --- |
| [sweetrb/apple-mail-mcp](https://github.com/sweetrb/apple-mail-mcp/tree/e1129cae9b1a6e8a0225918b4969cae5e3f9fac4) | `e1129ca` | AppleScript headers; separate IMAP connection for body search |
| [patrickfreyer/apple-mail-mcp](https://github.com/patrickfreyer/apple-mail-mcp/tree/419e8c16073d17a46350544df82534e2a9dd7a3e) | `419e8c1` | AppleScript metadata and bounded per-message body reads |
| [parasxos/apple-mail-mcp](https://github.com/parasxos/apple-mail-mcp/tree/70dfd70a5f43fb770eb796ad585be9067721b91e) | `70dfd70` | Envelope Index metadata/snippets plus owned incremental FTS5 bodies |
| [jasondk/errol-mail](https://github.com/jasondk/errol-mail/tree/bbf96fff284813d570536ad5cf11e630e11fc212) | `bbf96ff` | Envelope Index metadata search; targeted and batched MIME reads |
| [imdinu/apple-mail-mcp](https://github.com/imdinu/apple-mail-mcp/tree/5d7df2dea5a8447d02f4c35b583ef180cb9229dd) | `5d7df2d` | Owned full-body FTS5, disk reconciliation and optional watcher |
| [fledgeling-co/sift-apple-mail-mcp](https://github.com/fledgeling-co/sift-apple-mail-mcp/tree/1f6b7ec9b21e1c8a7a8cdc50b84ff1d2ce4ea226) | `1f6b7ec` | Owned positional FTS5 with published generations and a daemon |
| [mp-consulting/apple-mail-mcp](https://github.com/mp-consulting/apple-mail-mcp/tree/4255bef5da220bcad96f4a0a3ea2df98856b4972) | `4255bef` | Envelope Index plus owned keyed-hash word/bigram FTS5 |

These findings apply to those revisions, not every past or future release.

## What the headline speeds measure

**Parasxos has two fast paths.** Its native-index benchmark fetches one known
message's metadata by ROWID in under 0.1 ms. Its body benchmark queries its own
already-built FTS5 database, returning at most 50 IDs on an open connection.
Neither number includes a complete MCP request with refresh, metadata retrieval,
coverage reporting and body verification. Production search performs bounded
incremental maintenance before querying. The speed is useful; it does not show
that Apple exposes a sub-millisecond full-body API we overlooked.
[Metadata benchmark](https://github.com/parasxos/apple-mail-mcp/blob/70dfd70a5f43fb770eb796ad585be9067721b91e/docs/benchmarks.md#L7-L40),
[body benchmark code](https://github.com/parasxos/apple-mail-mcp/blob/70dfd70a5f43fb770eb796ad585be9067721b91e/tools/bench_search.py#L29-L47),
[production path](https://github.com/parasxos/apple-mail-mcp/blob/70dfd70a5f43fb770eb796ad585be9067721b91e/email_mcp/sources/apple_mail.py#L519-L615).

**Imdinu is the strongest additional performance reference found.** Its published
roughly 28 ms body search on about 73,500 messages is measured through MCP
JSON-RPC/STDIO, after indexing. It stores decoded full bodies in an owned FTS5
index and reconciles additions, moves and deletions. These are author-reported
measurements on another Mac, but the benchmark boundary is much closer to what
a user experiences than a raw SQL microbenchmark.
[Method and caveats](https://github.com/imdinu/apple-mail-mcp/blob/5d7df2dea5a8447d02f4c35b583ef180cb9229dd/docs/benchmarks.md#L103-L140),
[index schema](https://github.com/imdinu/apple-mail-mcp/blob/5d7df2dea5a8447d02f4c35b583ef180cb9229dd/src/apple_mail_mcp/index/schema.py#L177-L229),
[reconciliation](https://github.com/imdinu/apple-mail-mcp/blob/5d7df2dea5a8447d02f4c35b583ef180cb9229dd/src/apple_mail_mcp/index/sync.py#L110-L194).

**Sift's reported 3.76 ms is an in-process search measurement.** Its benchmark
calls model/store methods directly, rather than sending an MCP tool request.
Its contentless positional FTS5 design is worth studying, but comparing that
number directly with Imdinu's protocol measurement would be misleading. Its
published build also takes minutes and reports incomplete body coverage. A
daemon extends cache/build lifetime across connections; a normal STDIO MCP can
already keep a process warm across calls within one connection, as ours does.
[Benchmark call sites](https://github.com/fledgeling-co/sift-apple-mail-mcp/blob/1f6b7ec9b21e1c8a7a8cdc50b84ff1d2ce4ea226/bench/head-to-head.ts#L64-L145),
[FTS schema](https://github.com/fledgeling-co/sift-apple-mail-mcp/blob/1f6b7ec9b21e1c8a7a8cdc50b84ff1d2ce4ea226/src/index/schema.ts#L40-L48),
[published performance discussion](https://github.com/fledgeling-co/sift-apple-mail-mcp/blob/1f6b7ec9b21e1c8a7a8cdc50b84ff1d2ce4ea226/docs/PERFORMANCE.md).

## Why the other routes are not equivalent

- **Sweetrb:** body queries become server-side IMAP `BODY` criteria. Accounts with
  only AppleScript access are skipped/reported or rejected for body search.
  This route needs a provider connection outside our native-only scope.
  [Routing](https://github.com/sweetrb/apple-mail-mcp/blob/e1129cae9b1a6e8a0225918b4969cae5e3f9fac4/src/index.ts#L533-L750),
  [IMAP criteria](https://github.com/sweetrb/apple-mail-mcp/blob/e1129cae9b1a6e8a0225918b4969cae5e3f9fac4/src/services/imapClient.ts#L729-L753).
- **Patrickfreyer:** native body search reads messages through AppleScript. It
  caps large-mailbox body scans at 50 and reports limited scanning; an all-mailbox
  search also excludes some folders. That is not equivalent archive coverage.
  [Caps](https://github.com/patrickfreyer/apple-mail-mcp/blob/419e8c16073d17a46350544df82534e2a9dd7a3e/plugin/apple_mail_mcp/tools/search.py#L24-L55),
  [scan and exclusions](https://github.com/patrickfreyer/apple-mail-mcp/blob/419e8c16073d17a46350544df82534e2a9dd7a3e/plugin/apple_mail_mcp/tools/search.py#L422-L563).
- **Errol:** search filters sender, subject, date and mailbox through SQL. It can
  then read complete local messages, but the search predicate does not cover
  their bodies. Thread and bounded batch reads are useful product ideas.
  [Search SQL](https://github.com/jasondk/errol-mail/blob/bbf96fff284813d570536ad5cf11e630e11fc212/src/messages.py#L388-L484),
  [batch reads](https://github.com/jasondk/errol-mail/blob/bbf96fff284813d570536ad5cf11e630e11fc212/server.py#L685-L796).
- **MP Consulting:** keyed-hash indexing avoids storing plaintext words in its
  extra index. However, intersecting adjacent bigrams does not prove an exact
  phrase of three or more words: “alpha beta ... beta gamma” satisfies the
  bigrams for “alpha beta gamma.” Its indexed path trusts matching IDs. Original
  MIME verification would still be needed to preserve our phrase contract.
  [Phrase implementation](https://github.com/mp-consulting/apple-mail-mcp/blob/4255bef5da220bcad96f4a0a3ea2df98856b4972/Sources/MailStore/BodyIndex.swift#L233-L267),
  [indexed results](https://github.com/mp-consulting/apple-mail-mcp/blob/4255bef5da220bcad96f4a0a3ea2df98856b4972/Sources/MailStore/MailStore.swift#L883-L909).

Parasxos also strips phrase punctuation and ANDs tokens, and caps body IDs before
applying account/date filters. Its optional Graph/IMAP backfill improves missing
body coverage using connections we deliberately exclude. We should learn from
its coverage ledger, without treating its matching semantics or provider-backed
coverage as identical to ours.
[Query normalization](https://github.com/parasxos/apple-mail-mcp/blob/70dfd70a5f43fb770eb796ad585be9067721b91e/email_mcp/fts.py#L120-L140),
[body-ID bound](https://github.com/parasxos/apple-mail-mcp/blob/70dfd70a5f43fb770eb796ad585be9067721b91e/email_mcp/fts.py#L313-L340),
[coverage reference](https://github.com/parasxos/apple-mail-mcp/blob/70dfd70a5f43fb770eb796ad585be9067721b91e/docs/reference.md#L524-L548).

None of these source paths decodes the native term/posting store we use. Negative
`mdfind`/`mdls` observations in another project's research do not invalidate our
observed on-disk decoder. Conversely, decoding that store does not prove complete
Mail UI parity. Our [format research](NATIVE_MAIL_INDEX_FORMAT.md) and
[measured limits](STATUS.md) remain the evidence for our own route.

## What we actually missed or made unnecessarily expensive

**Account/mailbox scope is applied too late.** Our current
[`Catalogue.rows`](../src/macos_personal_mcp/mail_native/catalogue.py) pushes dates
and unread state into SQLite, but loads and validates up to 100,001 rows before
filtering account/mailbox in Python. That both wastes work and can reject a
small selected mailbox because the overall archive exceeds the 100,000-row cap.
Exact mailbox selection should happen before that cap.

A read-only experiment on this Mac compared the existing row loader with a SQL
prototype selecting the exact same mailbox ID before the joins/results are
materialized. It verified identical returned row fields in each iteration.
These are component timings, **not end-to-end MCP or body-search benchmarks**:

| Work | Runs | Median | Observed range |
| --- | --- | --- | --- |
| Current catalogue loader selecting 69 rows from 42,600 active rows | 7 | 379.114 ms | 343.210–585.943 ms |
| SQL-scoped prototype returning those same 69 rows | 7 | 9.142 ms | 8.428–15.065 ms |
| Known-ROWID metadata lookup on an open connection | 7 | 0.017 ms | 0.015–0.059 ms |
| Current archive header search, engine call without MCP transport | 5 | 580.585 ms | 578.682–640.993 ms |

The prototype is not an implemented fix or a promised 41× overall speedup. It
uses an already resolved mailbox ID; production must resolve exact native account
and mailbox selectors safely. The comparison demonstrates avoidable catalogue
work, and why a sub-millisecond known-ID lookup is a different operation from
an archive query. No body reads, native writes or competitor code were used.

**Warm native-index calls still do whole-store work.** The
[metadata reader](../src/macos_personal_mcp/mail_native/identities.py) reuses
decoded blocks, but still reads/hashes metadata pages and rebuilds the inventory;
the [engine](../src/macos_personal_mcp/mail_native/engine.py) remaps active IDs.
An unchanged-checkpoint inventory cache could help. It needs source-change,
truncation and stale-page tests before relaxing any checks.

**Header matching and pagination repeat work.** We normalize and inspect every
scoped header, create row models and hash the snapshot before slicing the page.
SQL preselection, cached normalized lookup values and bounded snapshot-result
reuse deserve profiling. SQLite `LIKE` alone is not a drop-in replacement for
our Unicode, token-boundary and phrase semantics.

**Public portability is limited.** Large body searches currently require the
exact validated macOS 26.5.2 profile. Supporting more machines requires additional
format validation or a different retrieval backend. Deleting the profile gate
would hide uncertainty, not solve compatibility.

## Recommended next work

1. Fix exact account/mailbox SQL scoping first. Add a synthetic regression where
   a small requested mailbox belongs to an archive over 100,000 rows, plus local
   mailbox, encoded path and identity tests. Preserve current matching semantics.
2. Profile and prototype unchanged-checkpoint inventory reuse. Measure cold and
   warm calls, source-change behavior and a second results page separately.
3. Benchmark an incremental owned FTS prototype against the improved native path
   on the same corpus and through the same MCP boundary. Include exact phrases,
   body-only positives, cross-field matches, dates, negatives, moves/deletes and
   partial/unavailable bodies. Measure initial build, incremental maintenance,
   storage, recall and steady query latency separately.
4. Select the backend on those results and support goals. An owned index may be
   better for repeated archive search and macOS portability. Keep one canonical
   search surface; do not simply re-enable the old scoped legacy tool or silently
   mix different search semantics. Preserve the native-only boundary and report
   freshness/coverage whichever backend is selected.
5. Consider bounded thread/batch reading and bulk Apple Events metadata reads
   for everyday usability. These reduce round trips without requiring a new
   full-text architecture.

This review changes documentation and records findings. It does not switch the
runtime backend, add a watcher/daemon, alter approval settings or claim that the
proposed optimizations have shipped.
