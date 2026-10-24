# 0012: On-demand native hybrid Mail search

**Historical version 0.2.0 contract.** [Decision 0013](0013-unified-mail-search.md)
supersedes its tool names, default exposure, matching fields and direct-scan
threshold: version 0.3.0 has one canonical `mail_search`, with legacy FTS opt-in.
The native format, identity, MIME and safety limits below continue to apply unless
explicitly superseded. See STATUS.md for current verification and activation.

Status: implemented, local native and SDK verified, 24 October 2026.
Desktop discovery/read of the new tool requires reloading the existing connection.
Owner explicitly authorized implementation after decision 0011's research phase.

## Contract and rollout

Add `mail_search_native` with versioned `native-body-v1` input/output semantics.
Keep `mail_search` and its explicit scoped FTS5 maintenance unchanged, so old
callers do not silently receive different Boolean/column or diacritic semantics.
The guarded desktop profile will expose 20 tools after reload (17 in read-only).
No registration, permission file, other MCP or native write executor is changed.

Native search defaults to all nondeleted local physical Mail records. Optional
account ID, exact mailbox path, received-date and unread filters narrow that
scope. Dates are aware, lower inclusive and upper exclusive. Tokens are ANDed;
quoted phrases preserve normalized order, punctuation and whitespace. Body
verification uses Unicode NFC/casefold, preserving accents. Native normalization
uses NFD, the observed byte permutation, case branches and validated subtoken /
punctuation aliases; arbitrary language/tokenizer parity is not guaranteed.
FTS operators are rejected. Optional `fuzzy_distance=1|2` accepts one ASCII
alphanumeric word of 4-40 characters and labels matched spellings. Native fuzzy
expansion is bounded; a broad distance-two archive query can exceed the limit.
Spelling is not semantic search. No compatible native semantic encoder is proven.

Use original MIME directly for scopes of at most 500 records, before accessing
Spotlight. For larger scopes resolve candidates through the guarded native term
index and both metadata stores, then current catalogue rows and original bodies.
Choose a selective anchor among up to three query words. Read newest missing,
pending and missing-RFC identities as bounded exceptions. Preserve physical copies.

The undocumented index route is gated to this verified macOS **26.5.2** profile,
header 114 and observed LZ4 metadata framing. Unsupported profiles fail explicitly;
small direct scopes remain available. Updating the gate requires revalidation,
not changing permissions. This is file-format access, not a private API call.

## Safety and lifecycle

A lazy serialized child lives only for the STDIO connection. It retains compressed
block fingerprints, OID/ROWID/update tuples and diagnostics in process memory.
Bodies, snippets and a copied vocabulary are not cached. There is no new body
SQLite database, daemon, scheduler, autonomous refresh or startup scan. Losing
this cache changes latency only. Only legacy FTS maintenance writes its owned DB.
The metadata parser independently implements the narrow permissive format
reference; no GPL helper, decompiled source or experiment import is shipped.
See THIRD_PARTY.md. The only new locked runtime dependency is lz4 4.4.5.

Catalogue reads use parameterized SQLite `mode=ro` with normal WAL semantics.
Check source inode/data_version and captured MIME identities; compare original /
shadow generations and prefix counts, all header bytes and file signatures.
Unknown forms, stale cursors, changing or lagging checkpoints fail explicitly.
Retry a changed checkpoint at most once under the same monotonic deadline.
Persisted observations are not an atomic system-wide snapshot. An mmap truncation
can kill the reader child; its parent returns failure and reaps/restarts it.

The parent deadline is 120 seconds including queueing, creation, pipes and work.
Worker input/output frames are bounded (64 KiB / 2 MB). Limits include 100,000
catalogue rows, 500 exception reads, 2,000 candidate bodies, 20 MB per MIME source
and 100 MB total source bytes. Query/node/posting/decompression work is bounded.
Limits are errors or counted unsearched candidates, never clean successful zeros.
Pagination binds query/scope, catalogue rows, checkpoint and captured file stats;
source changes require restarting from offset zero.

Strict RFC identity requires a nonempty match. Malformed/missing IDs require a
separate account/mailbox/file/remote-UID/date/conversation binding, rechecked
against current native data. No lossy ID normalization is used. Reads never
restore flags; observed catalogue/flag changes invalidate the search.

MIME decoding prunes attachment subtrees and embedded messages. Native alternative
selection prefers the HTML body; related parts use their root. Static HTML text
excludes script/head/style/inline-hidden content and preserves link/table/block
boundaries; it is not a browser renderer. Charset/transfer decoding is strict.
Original native bytes without a charset accept strict UTF-8 (ASCII is a subset);
no replacement decoding is used. A missing header/body separator can yield useful
identity-checked text but is counted partial. Other structural/encoding defects
remain unavailable. `.partial.emlx` bodies are always counted partial, even if
the selected text appears complete. Legacy RFC-source decoding stays strict.

`execution_complete` means every selected candidate was attempted without a work
limit or unavailable body; it does not certify complete body/index coverage.
`exhaustive` remains false. `partial_bodies`, native coverage, exception counts,
unsupported metadata records, unavailable and unsearched counts remain visible.
A partial zero never proves absence. See STATUS.md for measured denominators,
known coverage gaps and performance tradeoffs.

Send/create approval and outcome journals remain unchanged. Invitations remain
intentionally excluded. No live send, invitation or event was used in these tests.
