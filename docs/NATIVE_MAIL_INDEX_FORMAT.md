# Native Mail index research handoff

> Implementation update, 24 October: the owner authorized execution. Version 0.2.0
> implements the native hybrid as `mail_search_native`; see decision
> [0012](decisions/0012-native-hybrid-mail-search.md) and [STATUS.md](STATUS.md).
> Research/deferred wording below describes the earlier planning checkpoint.
> New-tool desktop discovery/readback is pending connection reload.


24 October 2026. **Research observations, not a supported Apple format or deployed
MCP backend.** Validated on this Mac, macOS 26.5.2 (25F84), using read-only native
files and isolated Python 3.15.1 probes. Read [the implementation plan](MAIL_SEARCH_V1_PLAN.md)
and [the measurements](EXPERIMENTS_NATIVE_MAIL.md) before using these notes.

## Proven path

Query word → native term dictionary → posting document slots → native object IDs
→ native metadata Mail row IDs → Envelope Index filters → original MIME body.

The catalogue has no full-body SQLite column. Core Spotlight stores the fast term
index separately. The index is compressed and uses a character permutation;
it is not opaque ciphertext on this Mac. Finding plaintext with `strings` or
comparing an encoded trie key to ordinary UTF-8 is not a valid negative query.

The main observed store is below
`~/Library/Metadata/CoreSpotlight/NSFileProtectionCompleteUntilFirstUserAuthentication/index.spotlightV3`.
Other protection stores also exist. Discover and validate stores rather than
assuming every Mac uses only this location. Native Mail is currently V10.

## Persisted checkpoint and current writers

`indexState` is seven little-endian 32-bit words: format version, clean generation,
shadow counter, normal count, live count, shadow normal count, shadow live count.
The shadow counter is independent; do not interpret it as a header generation.
The observed view contains ordinary prefix `0` and `live.0` through `live.30`.
Search every relevant prefix. The newest live file alone is insufficient.

Apple's read-only shadow path provides a better consistency boundary than reading
active files arbitrarily. For each prefix:

- Read `shadowIndexHead`, requiring version 114 and a validated readable state
  (`0xD00D0DD0` or `0xC001D00D`). Version 1 means shadow refresh is in progress.
- Use `shadowIndexGroups`. IDs, postings and positions use their original files.
- Dictionary/directory/term-offset files use originals only if the header's
  read-only-terms bit (`flags & 2`) is set; otherwise use their shadow counterparts.
- Compacted format is `flags & 4`; it can occur under a `live.*` name. Compacted
  dictionaries carry offsets directly and do not require `indexTermIds`.
- Validate original/shadow header generations match, both prefix counts agree,
  and the whole state plus headers and opened-file identities remain unchanged.
  A stable but lagging shadow is not an acceptable current view.

Headers are 4,096 bytes: five little-endian 32-bit fields followed by varints,
with a trailing serialized-length word. Initial varints include last document,
document count and capacity. Validate all bounds against actual file sizes.

Shared posting/position payload arenas are not simple immutable file prefixes.
Their committed regions are `[0, limit)` and `[index, capacity)`; the gap is free
space. Posting bounds occur at varints 14–16, position bounds at 22–24. Normal
writes preserve committed payloads until the next checkpoint; source review and
a live generation transition corroborated this with hashes. Compaction replaces
files. Shadow headers invalidate before ordinary in-place shadow writes.

This supports a guarded checkpoint reader, not a claim of an atomic system-wide
snapshot across every repair path. Observe path device/inode, header bytes,
file size/mtime/ctime and Mail catalogue commits; reopen and retry a bounded
number of times on change. If the deadline expires, return unavailable/partial,
never a successful empty result. Native files must never be recovered, locked
for writing, copied back, truncated or modified by this MCP.

## Term dictionary and normalization

The research reader handles fat nodes, compact bitmap nodes and front-coded flat
buckets. The root fat node is at offset 1,028. Fat nodes contain a terminal word
and 256 children. Compact nodes use a 256-bit bitmap and rank/popcount to locate
child pointers. Child tags distinguish compact, fat and flat representations;
validate pointer alignment, length and cycles before following them.

Flat buckets are addressed in 64-byte units and contain an eight-byte header,
used length, front-coded suffixes and variable-length values. Ordinary values are
term IDs. Compacted values accumulate posting/position offsets. A zero position
delta means no positions for that term, not an offset-zero usable position list.

Apply Unicode NFD before UTF-8 byte encoding and Apple's full 256-byte character
permutation. The current mapping was read from this Mac's SpotlightIndex image
inside the dyld shared cache and checked against the actual dictionary. Merely
mapping ASCII letters is insufficient for umlauts and punctuation. Preserve
accents; case handling and diacritic folding are separate choices.

Bare exact-term lookup is insufficient for ordinary Mail words. Validated mode-2
subtoken aliases use `\x01\x02`; bounded prefix traversal also finds aliases of
hyphenated compounds. Ordinary terms with trailing punctuation can need matching
boundary variants. These explain the owner-confirmed Mail hit missed by the
initial reader. Mode-1/control forms are outside the validated V1 keyword route.

Implement explicit node/entry/variant/time bounds and report exhausted expansion
as partial. Do not broaden a partial expansion into a definitive negative. The
isolated `word_lookup.py` contains the validated traversal and normalization
experiments; build synthetic equivalents before translating to production.

## Postings and identity

Ordinary `indexTermIds` entries select posting offsets. Compacted dictionaries
supply offsets themselves. Linked posting records use LEB128 controls with a
next pointer and chunk bit. Tested forms include singleton entries, descending
deltas, reversed bitmaps, complementary gaps and typed update records.

Keep update handling conservative and verify returned bodies. A posting hit may
be a header, attachment, other application or stale slot. Decode IDs as
big-endian 64-bit values from `indexIds`; group 0 and group 0x20 are inactive
(`group & 0xDF == 0`). Exclude reserved document slot zero. Respect checkpoint
document count rather than the larger allocated mmap length.

Native metadata resolves OIDs to `_kMDItemExternalID` (the Mail catalogue row ID),
`_kMDItemBundleID == com.apple.mail` and `kMDItemContentType == public.email-message`.
Read both `store.db` and hidden `.store.db`, select the newest record version and
reject conflicting equal-version identities. Main-store-only lookup missed two
recent rows which the hidden store supplied.

Use block-directory OID bounds to read only relevant compressed blocks; account
for OID byte order in comparisons. Read referenced `dbStr` map entries lazily.
Decode only the required identity fields, then stop. Generic embedding/list
fields add irrelevant complexity. The observed 6,027 metadata pages all used
supported LZ4 framing. Unknown framing remains an explicit capability limitation.

A metadata coverage inventory can keep compressed-block fingerprints and identity
tuples in process memory. Hash actual captured bytes, bind auxiliary-map hashes
to the bytes used for decoding, retain diagnostics on cache hits, and discard
blocks no longer referenced. Reconcile active checkpoint IDs with current SQL
rows and body-indexing state. Do not mistake `message_body_indexed=1` alone for
proof that our reader can retrieve every word.

## Queries and source verification

Open Envelope Index with SQLite `mode=ro`, normal WAL behavior and parameterized
SQL. Scope by date/account/mailbox before expensive body reads. Revalidate file
identity and SQLite `data_version`; native path replacement requires reopening.

Native candidates can include false positives. Verify the final keyword/phrase in the original
MIME body, excluding headers and attachments. HTML text extraction is a heuristic,
not Mail/WebKit rendering parity; stylesheet/layout visibility remains unproven.
Match catalogue and file identity;
use the existing hardened MIME decoder for production, including incomplete
`.partial.emlx` rules. A readable positive is not proof that every omitted part
was searched. Keep unavailable counts visible. Never restore observed flags
speculatively.

Exact phrases need not await a complete native position decoder: obtain a bounded
candidate set from one or more indexed anchor words, then verify normalized word
order/spacing in each original body. Choose selective anchors; a ubiquitous word
must not trigger an unbounded archive scan. Test wrong-order phrases and date
boundaries as negatives. Preserve the distinction between token, phrase and
arbitrary substring semantics.

The demonstrated fuzzy prototype accepts ASCII alphanumeric words only. Fuzzy
spelling can traverse the existing trie with edit-distance pruning and
explicit work limits. It was demonstrated for misspellings without creating a
second vocabulary. This is not semantic search. Existing vector files do not
provide a supported matching query encoder; reuse of those vectors is unproven.

## Research files, provenance and licensing

Ignored local files are under `.local/native-index-two-hour-20261024/`:

| File | Purpose |
| --- | --- |
| `dictionary_compact.py`, `word_lookup.py` | Trie, current alphabet, normalized token/alias lookup |
| `postings_reader.py`, `test_postings_formats.py` | Linked posting decoder and randomized synthetic roundtrips |
| `shadow_view.py`, `test_shadow_guard.py` | Persisted view and change/lag guards |
| `permissive_identity.py` | Apache-based narrow OID-to-Mail identity adapter |
| `coverage_inventory.py` | GPL-backed research coverage inventory; do not adopt silently |
| `permissive_inventory_probe.py`, `permissive_cached_inventory_probe.py` | Apache-only full identity inventory, block fingerprints and warm-cache evidence |
| `native_bound_body.py` | Explicit exact native binding for malformed/missing RFC IDs |
| `query_pipeline.py`, `body_reader.py` | Research end-to-end body verification; not production-hardened |
| `fuzzy_dictionary_probe.py` | Bounded native-vocabulary spelling experiment |
| `checkpoint-format-evidence.md`, `semantic-and-license-notes.md` | Detailed source review and limits |

These private files are available on the investigation Mac, not in Git. They may
contain private fixtures/identifiers. Do not commit them wholesale or promote
untyped research code directly. No package installation or experiment dependency
should occur during production startup.

Primary references:

- [Apple's published legacy CFBurstTrie implementation](https://github.com/apple-oss-distributions/CF/blob/dc54c6bb1c1e5e0b9486c1d26dd5bef110b20bf3/CFBurstTrie.c).
  Useful background; it is not the current full format.
- [MobileSpotlightIndex decompilation](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/tree/90aa0cfe59d9682b4265e1354c8b19ec3c7823ab/System/Library/PrivateFrameworks/MobileSpotlightIndex.framework/MobileSpotlightIndex),
  units `_09`, `_12`, `_14`, `_15`, `_37`–`_41`, `_65`, `_68` informed format and
  writer-path experiments. This is iOS reference code, not an Apple-supported
  macOS contract. No standard project license was found; do not copy decompiled
  source into this project. Implement observed format facts independently.
- [dtformats Spotlight parser](https://github.com/libyal/dtformats/blob/308ce8c38df2eb95a71b6e832b3f9803f0c4b169/dtformats/spotlight_storedb.py),
  Apache-2.0, is the demonstrated permissive metadata reference. Retain notices.
- [mac_apt's actual helper](https://github.com/ydkhatri/mac_apt/blob/70eb9717095acfded8c29a4b1ccbb933f2db5b41/plugins/helpers/spotlight_parser.py)
  is GPL-3.0-or-later even though the repository root has an MIT license. Earlier
  research inventory helpers import it. Do not silently vendor it under MIT;
  use the demonstrated permissive identity route or make an explicit compatible
  dependency/distribution choice.
- [REA](https://github.com/morluto/rea) 6.7.0 was actually run against Mail's current
  Mach-O. It exposed native dispatch metadata, but not the separate shared-cache
  search implementation. It was useful tooling, not the decisive decoder.
- [Apple's app-private search description](https://developer.apple.com/videos/play/wwdc2024/10131/)
  and [compact content/delegate hydration](https://developer.apple.com/videos/play/wwdc2026/246/)
  explain why readable metadata, full-text search and original bodies are separate.
