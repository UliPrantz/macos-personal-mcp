# Direct Mail storage experiments

> Implementation update, 24 October: the owner authorized execution. Version 0.2.0
> implements the native hybrid as `mail_search_native`; see decision
> [0012](decisions/0012-native-hybrid-mail-search.md) and [STATUS.md](STATUS.md).
> Research/deferred wording below describes the earlier planning checkpoint.
> New-tool desktop discovery/readback is pending connection reload.


> **Corrected by the extended investigation, 24 October:** The subsequent research
> found that the initial dictionary probe omitted Apple's character permutation.
> Its negative literal-token finding below was therefore not a valid semantic
> search result. After correcting the mapping, the original controlled body
> token resolves through native postings to both Mail copies and their attachment.
> Owner-supplied examples, keywords, phrases, date filters and a diverse body-word
> corpus now pass research checks. The recommendation is direct small-scope reads
> plus native indexed candidates for larger scopes; see the extended section below.
> Production implementation remains deferred to a cheaper model.

23 October 2026. These are live measurements on the owner's Mac, not claims for
other macOS versions or complete provider histories. The backend choice is still
under discussion. Implementation stopped at the owner's request; source was
restored to `pre-release revision` and the prototype saved privately. No switch was committed,
pushed or activated in the desktop connection.

## Existing storage is now readable

The previously denied `~/Library/Mail` directory is accessible from both the
task subprocess and the actual desktop MCP's doctor. `V10/MailData/Envelope Index`
was opened with SQLite `mode=ro`, a read transaction and a bounded query deadline.
No native database, schema, journal mode or message flag was deliberately written.
Native Mail may synchronize/download data during authorized reads.

The existing catalogue contains **42,578 message records**, including **one marked
deleted**, across **102 mailbox records**. These are physical cache records, not
42,578 unique RFC messages or a reconciled count of the current Mail sidebar.
Native file enumeration found **42,972 `.emlx` files**, including **13,382 partial
files**; these file counts are not interchangeable with catalogue rows.

Mail's catalogue has no SQLite virtual full-text table. `protected_message_data`
has zero rows. `searchable_messages` reports **42,576 body-indexed records**, but
stores indexing state rather than full searchable bodies. The Core Spotlight
`store.db` files are readable but have a non-SQLite binary format (`8tsd`). Their
contents were not copied, modified or reverse engineered into another index.

## Existing system search index was not exposed

`mdfind` returned zero Mail items for the Mail/email content types. A text-content
query for the controlled self-test ID returned the separate test attachment file,
not a Mail result. This control prevents interpreting a filesystem match as proof
that the Mail body index was searched.

Public `CSSearchQuery` was exercised with default options and `allowMail`, using
an email-type query, a known body-only positive and an invented negative. All
returned zero items without errors. `CSUserQuery` with `allowMail` also returned
zero for the known test ID and controls. The installed Apple SDK header explicitly
associates `CSSearchQuerySourceOptionAllowMail` with the
`com.apple.corespotlight.search.allow.mail` entitlement. No entitlement, identity,
TCC setting or system index was changed. Zero results do not prove absence.

Consequently reuse of Apple's existing body-search index is **not demonstrated**.
It is unavailable to the tested process. This is distinct from readable Mail
metadata and message files. The public Core Spotlight binding used for the
experiment was installed only under ignored `.local/spotlight-probe-deps`;
production dependencies were not changed.

## Direct reads and the no-shadow prototype

The prototype queries the native catalogue and reads original message files.
It constructs no persistent body cache or index. Search accepts optional account,
folder and date filters, including all local records when omitted. It performs
Unicode case-insensitive **literal substring** matching, not the previous FTS5
token/Boolean syntax. Results expose identities, coverage, failure counts and
bounded pagination. A physical message can appear in several native labels;
membership is selected without duplicating that physical record.

Partial `.emlx` files can omit bodies as well as attachment bytes. One message in
the month test had an empty calendar MIME part with a nonzero native declared
length; silently treating that as an empty body would lose content. The prototype
detects this and can make at most 20 exact, identity-checked native Mail source
reads per body-search request. These fallback reads keep no shadow index. Other
missing, invalid or identity-mismatched content stays explicitly unavailable.

Both existing self-test copies were read from native files, with observed read
flags unchanged. The complete Sent file supplied full RFC source directly. The
recipient's partial file omitted attachment bytes, so complete-source retrieval
used the existing Mail API fallback. No new test email or Calendar item was
created, and the owner-deleted Calendar test event was not recreated.

## Real SDK MCP results

The installed absolute entry/flags were launched by a real SDK STDIO client from
`/tmp`. All 19 tools were discovered; native approval policy remained unchanged.

| Check | Result |
| --- | --- |
| Global header query over 42,577 non-deleted records | Two controlled self-test copies, complete; **0.785 s** MCP call |
| Global header negative | Zero, complete; **0.610 s** |
| 182-message month body scope | 182 searched, complete, one native fallback; positive **166 substring matches**, negative zero |
| Six alternating month body calls | **0.930–1.382 s**, median **0.956 s**; functional measurements, not the earlier 20-query FTS benchmark |
| Recipient-day body-only ID | One match from three records, complete; **0.153 s** |
| Same ID in recipient-day headers | Zero, complete; **0.137 s** |
| Exact self-test body reads | **0.142 / 0.168 s**, flags unchanged |
| Full-source reads | Complete file **0.143 s**; partial-file native fallback **1.215 s** |
| Global body scan | **149.141 s**, 40,745 searched of 42,577 candidates, two controlled matches; **incomplete** |

The global scan had **1,832 unavailable records**:

| Reason | Records |
| --- | ---: |
| Locally incomplete body after bounded fallback budget | 1,583 |
| Catalogue/file RFC identity mismatch | 147 |
| MIME invalid | 55 |
| Body decoding failed | 31 |
| Native fallback failed | 15 |
| Native message file unavailable | 1 |

It attempted 20 native fallback reads. Failure counts are conservative validation
results, not permission diagnoses or proof that the messages are irrecoverable.
The original owned body-index file's SHA-256 was identical before and after the
entire SDK experiment. No new shadow index was built.

## What the results support

Direct metadata search and targeted reads are practical. Replacing the current
body index with on-demand file scans is also implementable, but the measured
all-history query is slow and incomplete. The 182-message scope works quickly;
that does not establish fast complete archive-wide search. Keeping an incremental
body index would be a separate product choice, not reuse of Apple's existing
body-search index.

Private raw evidence remains under ignored `.local/native-mail-*.json` and
`.local/probe-mail-*.py`. No message content, addresses, identifiers or native
database copies are committed.

## Final bounded Spotlight check — 24 October 2026

The existing `mac_apt` Spotlight metadata parser (helper version 1.0.6) was
exercised against the four readable Core Spotlight `store.db` files and their
companion maps. Native files were opened for reading; no native database was
copied or deliberately modified. Parser dependencies were isolated under ignored
`.local/spotlight-final-probe/deps`, outside the production environment.

The largest store yielded **146,292 metadata records in 37.71 seconds**. The other
three yielded 1,009, 29 and 5,913 records. These are decoded Spotlight records,
including other applications and potentially historical items, not a count of
current Mail messages. This was a live-file diagnostic, not an atomic snapshot or
a completeness audit; unsupported records remain a parser limitation.

A focused pass identified the existing controlled body token in two records with
Mail's bundle identifier and email content type, plus one plain-text attachment
record. In all three, the token appeared only in `_kMDItemSnippet`; those values
were 153, 153 and 106 characters long. No `kMDItemTextContent`, `textContent` or
`htmlContentData` values were exposed among the parsed records. This demonstrates
readable Mail-related metadata and previews, not complete body search.

The readable store directories also contain separate full-text structures such
as `*.indexPostings`, `*.indexArrays` and multiple live generations. The tested
parser does not query these. Reusing them remains reverse-engineering work;
metadata decoding does not establish a working native full-text query route.
The successful decoding rules out opaque encryption as an obstacle for the
metadata actually read. It does not establish whether all full-text structures
are usable, encrypted, complete or current, nor demonstrate deliberate
obfuscation by Mail.

The installed WhatsApp MCP was inspected again. Its wrapper explicitly disables
its optional FTS sidecar, and its reader searches existing SQLite message text
with `LOWER(m.ZTEXT) LIKE LOWER('%' || ? || '%')`, using read-only transactions.
It therefore searches a readily available text column without reusing
WhatsApp's search engine. Mail's catalogue has no equivalent full-body column:
its original bodies require MIME/file decoding, with incomplete local parts and
native source fallback already observed above.

Private, content-redacted aggregate outputs and probe scripts remain under
ignored `.local/spotlight-final-probe/`. The upstream parser emitted temporary
diagnostic binary fragments; those probe-created files were removed and its
diagnostic writer disabled in the saved probes. No such fragments or message
contents are included in Git. The separate owner-requested ten-minute
full-text investigation below followed this metadata check.

Parser source: <https://github.com/ydkhatri/mac_apt/blob/master/plugins/helpers/spotlight_parser.py>.
It was used as an investigation tool, not copied into the MCP runtime.

## Superseded ten-minute full-text conclusion — 24 October 2026

The owner authorized a bounded read-only format investigation and web search,
while explicitly deferring product implementation. The investigation began at
00:02:48 UTC with a 00:12:48 UTC deadline. Probes and private identifiers are
isolated under ignored `.local/spotlight-ten-minute/`. Native files were opened
read-only; no new messages, events, permissions or runtime settings were changed.

There is substantive progress beyond metadata parsing:

- `indexHead` contains consistent binary headers (including `0xc001d00d`) and
  variable-length integers matching the sizes/capacities of companion files.
  `indexTermIds` contains 64-bit offsets into `indexPostings`. These are
  interpretable structures, not evidence of opaque ciphertext.
- Metadata IDs for the two existing controlled emails and their attachment
  occur as aligned big-endian 64-bit values in `live.30.indexIds`. Their metadata
  identifiers map back to native Mail catalogue row IDs. Repeated slots exist;
  an ID hit alone does not establish a current search result.
- The companion `indexGroups` has one byte per document slot. The newest
  controlled email slots have group 1 and older occurrences group 0; the
  attachment has group 14. This suggests active/group selection but does not
  prove complete deletion/version semantics.
- A published iOS 26.1 decompilation supplied concrete reader algorithms. A
  limited research decoder followed linked posting records and mapped postings
  to the controlled Mail IDs on this Mac. A 13.1-second scan found 164 candidate
  posting matches; following those candidates took 0.09 seconds. These are
  diagnostic timings, not search latency benchmarks. Unsupported bitmap/range
  or update forms remain explicitly partial.
- The reader code describes a BurstTrie dictionary with prefix nodes and
  front-coded suffix buckets. This explains why finding literal whole terms in
  raw files is not a valid test of whether they are indexed. A scan of roughly
  594 MB found no literal controlled token, despite the structural progress.

The final dictionary pass reconstructed **8,433,244 entries in `live.30` in
about 10–11 seconds**, with zero structural parser errors. All 164 candidate
posting term IDs could be associated with reconstructed dictionary entries.
Those are index entries across applications/properties, not unique Mail words.
The initial probe reported the controlled body token and tested long fragments
absent, but this comparison omitted the character permutation and was invalid;
the extended investigation below corrected it. A separate check of ordinary body-only
words found no corresponding same-message active posting among the 164 candidate
entries; that subset is not an exhaustive body search. The investigation stopped
at **00:12:47 UTC**, within the ten-minute limit.

**At that point the word-to-current-Mail-body-result test did not pass.** This is
neither proof the word is absent from all native indexes nor proof encryption is
responsible. Field selection, tokenization, coverage across generations and
unsupported posting forms remain unresolved. No further research was started
after the deadline.

The source is decompiled iOS code, not an Apple-supported macOS file-format
contract. Matching parts of its layout locally is useful evidence, but neither
full cross-version compatibility nor complete query semantics has been proved.
No complete native full-text backend has been implemented or activated.

Apple's WWDC26 description independently explains that text/HTML are indexed in
a compact searchable representation; a delegate supplies full readable items.
This supports the distinction between search postings and recoverable original
bodies. It does not establish that third-party access to Mail's search index is
available. The existing tested metadata parsers do not cover full-text postings.

Sources checked:

- [Apple: LLM search using Core Spotlight](https://developer.apple.com/videos/play/wwdc2026/246/),
  text-content representation and delegate hydration.
- [Sootmark Spotlight parser scope](https://docs.rs/crate/sootmark-spotlight/latest),
  explicitly excludes full-text index files.
- [Decompiled TermIndex reader](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/blob/main/System/Library/Frameworks/CoreSpotlight.framework/Support/CoreSpotlight/TermIndex.mm),
  mappings and document-ID tables.
- [Decompiled posting reader](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/blob/main/System/Library/PrivateFrameworks/MobileSpotlightIndex.framework/MobileSpotlightIndex/MobileSpotlightIndex_09.mm),
  compressed posting chunks.
- [Decompiled dictionary reader](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/blob/main/System/Library/PrivateFrameworks/MobileSpotlightIndex.framework/MobileSpotlightIndex/MobileSpotlightIndex_37.mm),
  trie traversal, with related `_38`, `_39` and `_40` units for iteration/buckets.

The practical limitation is unfinished format reconstruction and correctness
validation, not demonstrated deliberate obfuscation or a proven encryption
barrier. The former incremental-first recommendation was superseded by the
extended investigation and revised [V1 implementation plan](MAIL_SEARCH_V1_PLAN.md). Source and
tests remain at `pre-release revision`; saved implementation drafts are unverified and private.

## Extended native-index investigation — 24 October 2026

The owner authorized approximately two hours, subsequently allowing two to three,
for deeper read-only research and a cheaper-model implementation handoff. Work
began at 12:44 UTC. Production code, tool registration and runtime policy remain
unchanged. This section supersedes the earlier semantic-negative conclusion and
incremental-cache-first recommendation; historical measurements above remain
useful evidence of the approaches actually tested.

### Correction: the first decoder compared the wrong alphabet

The ten-minute dictionary reconstruction was structurally plausible but compared
encoded trie keys to ordinary UTF-8. Apple's character permutation was missing.
After recovering the full 256-byte permutation from the current Mac's read-only
dyld shared cache, the original controlled full-body token resolved through
native postings to both Mail copies and their attachment record. Mail/content
identity and body verification distinguish those records. The earlier absence
claim was a decoder error, not evidence that the term was absent or encrypted.

The demonstrated route is native dictionary → postings → active document slots
→ native metadata → Mail catalogue row → original MIME body. It does not build
an owned full-body index. The current observed format is documented in
[NATIVE_MAIL_INDEX_FORMAT.md](NATIVE_MAIL_INDEX_FORMAT.md).

REA 6.7.0 was actually exercised, using an isolated npm cache and its native
static-reader provider against Mail's Mach-O. It exposed dispatch metadata, but
the relevant engine lives separately in the shared cache. Published reader code,
current-binary constants and empirical file validation were decisive. No private
API invocation, decompiler injection, entitlement change or native recovery/write
was used. No provider API connection or extra permission was required.

### Body words, phrases, dates and spelling

Both owner-supplied dated emails were identified in native metadata and their
original files. Body words beyond previews, including long-message prose, were
found through postings. Exact phrase verification used selective native word
candidates and original MIME, rather than waiting for a complete native position
reader. The dated positive, wrong-day negative, same-word/wrong-order negative
and invented-word negative all behaved as expected.

A diverse fixture contains 35 messages across 12 account roots and 2019–2026;
33 supplied meaningful visible-prose words. **223/223 sampled word targets** were
retrieved with no parser errors, unsupported forms or exhausted expansion bounds.
The checkpoint-backed membership batch took 1.30 seconds. This is a recall probe,
not 223 complete MCP queries and not exhaustive testing of those bodies.

The initial misses taught concrete normalization rules:

- Native dictionary keys use Unicode NFD; applying it recovered the tested
  accented words without stripping accents.
- Mode-2 subtoken aliases and bounded prefix traversal recover compound words.
  This fixed the earlier owner-confirmed Mail hit that our bare-term reader missed.
- Punctuation-boundary variants account for a trailing curly apostrophe.
- Unvalidated mode-1/control aliases are excluded from the ordinary keyword path;
  their failures must not be disguised as supported behavior.

ASCII alphanumeric fuzzy spelling also works against the existing trie: one- and two-edit
misspellings recovered the intended term and known message, approximately
0.12–0.16 seconds in focused experiments. This uses bounded dictionary traversal,
not a copied vocabulary. Semantic-vector reuse remains unproved: readable vector
files and a matching dimension do not supply the matching query encoder/model.
Public Core Spotlight access did not expose Mail's app-private search results.
Semantic search is therefore a separate extension, not a V1 delivery gate.

### Metadata coverage, exceptions and incremental reuse

A full catalogue observation contained 42,593 nondeleted physical Mail rows.
Reading both `store.db` and hidden `.store.db` recovered 42,548 Mail metadata
identities, 42,547 joining current catalogue rows. The 46 missing metadata rows
were older messages from 2016–2022. Two recent main-store misses were recovered
from the hidden store. All historical missing-metadata bodies were locally
readable; a focused exception scan took approximately 0.17 seconds. This is a
small fallback set, not a reason to reject native indexed search.

The fixed recent-week scope is **17 October 2026 13:32:30 UTC through
24 October 2026 13:32:30 UTC**, upper bound exclusive: **401 rows**. All 401 have
native metadata identities and active committed-checkpoint slots. One row reports
body indexing pending and is included explicitly in direct-body fallback.
`message_body_indexed=1` alone is not proof of external query completeness.

A process-only inventory retains compressed-block fingerprints and identity
pairs, not body text, snippets or an owned database. Cold coverage took about
2.4 seconds; warm unchanged refresh about 0.4 seconds. During ordinary Mail
activity exactly one compressed metadata block changed: 12,053 block references
were reused, one block decoded, and the refresh took 0.432 seconds. No native
change was induced for this test. Auxiliary-map changes invalidate dependent
cached decoding, and diagnostics survive cache hits.

The main forensic metadata helper used during research is GPL-3.0-or-later,
despite its repository's MIT root license. A separate Apache-2.0 dtformats-based
identity adapter matched **401/401** recent OIDs with zero errors in about
0.10 seconds, reading selected pages only. All 6,027 observed metadata pages
used supported LZ4 framing. Production does not need a generic embedding/list
metadata parser or silent incorporation of GPL code.

### Concurrency, verification and practical limits

The reader now follows Apple's persisted shadow-file mapping, searches every
relevant generation and filters deleted/inactive slots. A shadow may be stable
but lag the current committed generation; the acquisition guard rejects that
case. Five synthetic guard tests cover generation/count mismatch and concurrent
header change. Posting decoder probes include 1,500 randomized roundtrips.

Source review found the normal checkpoint invalidation/commit order. Hashes of
committed posting/position/ID regions remained identical across an observed live
commit. This supports the guarded reader for the tested writer path; it is not a
formal atomic-snapshot proof for every repair operation. Changed observations
were actually detected during live query tests and must invalidate an attempt.
A production retry shares the original deadline and discards the prior matches.

Original MIME verification matters: native postings can also describe headers,
attachments or stale records. Research MIME review added attachment-subtree
pruning, including attached RFC messages, deliberate multipart selection, and
bounded single-file-descriptor source reads. Eight synthetic body tests passed.
HTML extraction remains a text heuristic, not pixel-identical Mail rendering;
stylesheet-hidden content and incomplete partial files require explicit limits.
The existing hardened production MIME validator should be reused and extended.

Fresh direct-file query checks preserved read flags and source observations.
Across an earlier long observation interval, four raw native flag values changed
while Mail/user activity and some public content reads overlapped; read/deleted
state remained unchanged and causality was not established. Nothing was restored
speculatively. Later filesystem-only fallback scans observed no flag changes.

The owner's clarified product bar accepts small historical gaps and prioritizes
recent mail and parity with Mail. On one recent message, a sampled body word was
absent from our postings; the owner independently confirmed that Apple Mail's
search, including Deleted Items, did not find that message either. That is an
observed shared miss for that word, not proof of an additional decoder defect or
proof that every possible query matches Mail exactly.

### Recommendation and remaining delivery work

The investigation has moved native reuse from speculation to a working research
query pipeline. Recommend native indexed candidates, current SQL filters,
original-body verification and a bounded missing/pending exception scan. Keep the
existing scoped FTS backend available and an incremental archive cache as a
fallback if future native compatibility makes maintenance disproportionate.

No production backend switch has been made. Typed adapters, strict failure and
cancellation behavior, complete synthetic fixtures, licensing/dependency choices,
real SDK benchmarks and actual desktop activation remain implementation work.
The current worker-per-call design also needs an explicit cache-lifetime decision:
process-memory warm timings cannot be claimed if a new worker rebuilds coverage
on every call. See [the concrete implementation plan](MAIL_SEARCH_V1_PLAN.md).

Private evidence stays under `.local/native-index-two-hour-20261024/` and
`.local/known-mail-examples-20261024/`. Only aggregate findings, format notes and
the plan belong in Git. No new mail, calendar item or invitation was sent/created.

### Final recent-week recall, query results and hybrid choice

The final independent identity split is **394 nonempty RFC-ID matches plus seven
exact native UID bindings**. Six of the latter have malformed Message-ID encoding;
one has no Message-ID. Empty-equals-empty was initially misclassified as strict
identity and was corrected. The separate binding checks account, mailbox, local
row/file identity, remote UID, received timestamp and conversation ID against
stable catalogue/trailer data; no lossy RFC normalization establishes identity.

All 401 local bodies were readable under those checks. **392 contain text; nine
have empty text bodies** (seven ZIP-only messages and two calendar messages with
empty text alternatives). The strict cohort includes 107 partial files. This is
readable decoded local-body evidence, not a claim that every partial MIME/attachment
part exists or that HTML extraction exactly reproduces Mail/WebKit rendering.

The final broader sweep selected words throughout each body, including middle/end
prose and Unicode. It contained **7,676 probes**. Seven were invalid sampling
artifacts: four contraction fragments and three merged adjacent HTML labels.
After excluding those explicitly, **7,629/7,669 valid probes hit native postings**.
All 40 misses belonged to exactly two messages: 20 words from the pending-index
message and 20 from the message without an RFC ID. Every valid probe outside
those two exceptions passed, with no decoder errors, unsupported forms, exhausted
limits or failed checkpoint guards. This is a finite corpus validation, not a
universal recall percentage for every query, language or historical message.

The missing-RFC signal is bounded: 190 catalogue rows across the observed archive,
but exactly one in the fixed week. Including it alongside pending-index rows gives
two recent fallback messages. The owner independently confirmed one word from the
missing-ID message also fails in Mail's own search, including Deleted Items.
Direct verified source scanning nevertheless finds it. Three pending-message
words also passed end-to-end exception fallback despite absent native postings.

Eight complete query-result comparisons over the **394 strict-RFC bodies**
returned **287/287 expected query/message pairs**, with zero false positives or
false negatives. These include ordinary English/German words, two exact phrases
and a literal negative. The seven separately bound messages exposed four expected
exclusions in the strict-only prototype; they were reported as identity/native
candidate limitations rather than hidden. An observed checkpoint change caused
one attempt to be discarded and retried, rather than accepting its results.

| Research measurement | Result and scope |
| --- | --- |
| Full recent-week body scan | **401 messages, 1.45 s warm**, identity verification + MIME text extraction + word filter; zero failures, unchanged catalogue/read flags |
| Last-three-day body scan | **185 messages, 0.63 s warm**, same checks |
| Diverse dated keyword pipeline | **33/33 targets**, median **0.412 s**, p95 **1.149 s**, maximum **1.492 s**; index-stage p95 **0.130 s**, no full coverage inventory |
| Six owner-example/negative checks | Correct body word, phrase, date and wrong-order outcomes; **0.017–0.739 s** with permissive targeted identity lookup |
| Recent indexed pipeline with coverage | 21 accepted queries; first **2.733 s**, subsequent median **0.641 s**, maximum **1.150 s**; this version uses the GPL research inventory |
| All-history indexed pipeline with exceptions | Four representative calls **0.666–2.936 s**, including zero negative and a recovered old missing-metadata message; 47 exceptions at that observation, before adding missing-RFC fallback |
| Apache-only full identity inventory | Exact **42,548/42,548** OID/ROWID and native-version parity; stable cached pass **11.07 s cold**, **0.973 / 1.070 s warm**, zero decoded blocks on warm passes |
| Research process peak RSS | About **198 MiB** after a cold coverage/query probe, versus 32 MiB before; this uses the GPL inventory, not a production memory bound |

All timings are research Python measurements on this Mac. The filesystem body
scan is warm, not a cold disk benchmark. Concurrent research load varied.
The Apache-only full inventory is slower than the earlier GPL helper's ~2.4-second
cold / ~0.4-second warm pass; do not promise the faster figures for that replacement.
Neither set is a measurement of the final MCP SDK or desktop request path.

**Final recommendation: native hybrid.** Read and verify every body for a bounded
small scope, so recent mail is independent of native indexing/tokenization gaps.
Use the existing native term index for larger/all-history scopes, with targeted
MIME checks and bounded exceptions. This avoids a separate full-body database and
makes the recent-use case useful without first warming a global identity inventory.
Keep a strict deadline/byte limit and explicit unavailable counts; an unrestricted
42,000-message query must not silently become a full scan.

Production HTML extraction must preserve meaningful text boundaries and avoid
manufacturing concatenated link labels or splitting contractions into misleading
test words. Native UID fallback remains an explicit validated identity path.
These are concrete implementation tasks, not reasons to abandon the approach.

A final research integration enabled the independent native-UID body path and
both recent fallback signals. It returned all three expected matches for the
previously shared missing-ID word, all 78 expected matches for another query
including three malformed-ID messages, the expected 14 phrase matches, and zero
for the negative. No body failures or flag changes occurred. First call was
2.95 seconds, subsequent calls 0.43–0.89 seconds, using the GPL research coverage
inventory. An earlier attempt encountered a native shadow refresh and rejected
every query before execution; the later stable checkpoint succeeded. Neither
attempt was treated as a complete empty archive result.

Read-only experiments concluded at approximately 15:07 UTC, within the owner's
extended two-to-three-hour window. The next work is implementation, not another
open-ended format investigation.
