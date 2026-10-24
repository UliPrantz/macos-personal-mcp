# 0005: Explicit FTS5 indexing through Mail's public RFC source API

Status: implemented and live verified for declared scopes, 23 October 2026.

## Source decision

Full Disk Access remains denied to the desktop task after background-server
restart. The owner could not add the bare executable and requested a Terminal
alternative. Do not use sudo, alter TCC databases or copy provider credentials.

The controlled self-email revealed a usable authorized alternative: Mail's public
read-only scripting `source` property returns the complete RFC/MIME message,
including attachment bytes. Both Sent and recipient copies were parsed and the
107-byte attachment hashes matched. Mail Automation permission already permits
this API; filesystem access is unnecessary for this ingestion route.

Use a fixed script with JSON data inputs, exact account/folder/local-ID/RFC-ID
selectors and read-flag observations. Source errors, identity mismatch, observed
flag changes, deadlines and excessive size must never become empty successful
bodies. A source request defaults to four million characters and explicitly
permits up to 64 million; indexing uses that upper bound. The source pipe is
bounded at 192 MB and each native child has a 15-second deadline. Large or
unavailable messages keep their scope incomplete. No body/source scan runs at
server startup or inside read-only search.

Native metadata inventories use bulk property getters, native account/folder
predicates, consistent before/after ID enumeration and a 5,000-message cap.
This removes per-message metadata Apple Events without retrieving bodies.

## Index and freshness contract

`index --scope-file ... --max-messages ...` is explicit local cache maintenance,
not an external communication. Each call attempts at most 1-200 missing/changed
sources (default 20); repeated calls resume committed per-message progress.
Separate exact account/folder/date scopes can overlap; caches may duplicate
storage across scopes, but each query selects one scope and preserves physical
message identities. An unindexed date range is an error, even if another
intersecting scope exists. No global all-account coverage is implied.

Store only decoded body text and required metadata in owned SQLite FTS5 storage
`~/Library/Application Support/macos-personal-mcp/mail-body-index.sqlite3` (0600,
parent 0700). Never open or change Mail's database/WAL/schema. Parse MIME using
Python's email package: charset/transfer decoding, plain/HTML alternatives,
nested multiparts and complete long bodies. Strip HTML markup/script/style;
exclude attachment contents, inline media and embedded RFC attachments. Encrypted,
unsupported, malformed or unprovably decoded bodies produce explicit errors.

Only mark a scope complete after every current inventory identity has a decoded
body and the before/after source inventory matches. Refresh tracks pending and
unavailable counts plus error codes; it reconciles additions, changed metadata,
moves/deletions and local-ID rebuilds. Search refuses incomplete scopes. Search
opens the owned database read-only, checks a 30-minute snapshot age, re-enumerates
native metadata, and requires the same identity/metadata fingerprint before
querying. Source read flags do not invalidate body identity; returned flags are
fresh observations. A source change produces an explicit stale-index error.

Mail message bytes are treated as immutable within the same local/RFC identity
and immutable header metadata. A provider replacing bytes without changing those
identifiers is not observable through this metadata watermark. The explicit
`--rebuild-index` flag resets just the selected owned scope and re-fetches its
sources; subsequent calls without that flag resume the rebuild. No search silently
refreshes its cache or extends freshness. The public API is not a database snapshot;
coverage is tied to the reported inventory observation time.

FTS5 `unicode61 remove_diacritics 2` provides token/phrase/Boolean/column queries,
Latin diacritic folding and no stemming. It is not arbitrary substring search.
SQL values are parameterized; invalid FTS syntax is an error. Results include
bounded excerpts, matching metadata, scope, index time and SQL execution time.

## Live evidence and limits

One Inbox, 1-22 October: **182/182 messages**, zero unavailable, **1,105,398**
decoded body characters, largest body **50,604** characters. A separate one-day
11-message scope and the one-message controlled recipient scope also completed.
The controlled body's word had zero header matches and one indexed body match.

Real SDK STDIO client on this Mac, 20 warm positive/negative queries:
**p95 1.892 seconds**, median 1.8642 seconds; SQL p95 **17.7006 ms**. Cold process
startup **0.4294 seconds**, first query **1.9559 seconds** separately. Both declared
warm targets pass on this 182-message scope. This is not proof for every account,
all history, arbitrary large sources or a much larger corpus. Indexing duration
was not benchmarked as query latency. An earlier 2.0969-second p95 motivated
native selector optimization; the stated measurement is the resulting code.

Synthetic tests cover long Unicode/phrase/negative searches, MIME alternatives,
HTML-only bodies, nested attachment exclusion, encrypted/invalid identity/charset,
resume/partial failure, stale/add/delete/local-ID change, explicit rebuild and
read-only query file preservation. Normal tests use isolated synthetic indexes.

The desktop subsequently reloaded the updated Python handlers. Direct tools in
this conversation rejected a stale scope, then passed complete 182-message
positive/negative searches and the one-message body-only test after explicit
cache refresh. The new raw source tool preserved identity/read flags; Calendar
and Contacts remained accessible. No further reload is pending for that revision.
No global registration was changed and no scheduled job was introduced.

## Lifecycle

Keep scope JSON private (account ID, folder path, explicit aware date bounds,
empty query, unread_only=false, offset=0). Refresh the exact scope explicitly
when stale or after 30 minutes. Initial ingestion may download bodies through
Mail and can be slow; item/child/output bounds and per-message commits permit
resumption. A failed/incomplete pass never grants complete query coverage.

To discard the search cache, stop active index/search calls and remove only
`mail-body-index.sqlite3` and its own SQLite sidecars. Rebuild before searching
again. Preserve `write-outcomes.sqlite3` and pending send snapshots; they are
independent no-blind-retry state. Never delete native Mail storage.

References: [SQLite FTS5](https://www.sqlite.org/fts5.html),
[Python email MIME traversal](https://docs.python.org/3/library/email.message.html).
