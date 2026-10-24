# macOS Personal MCP

Give ChatGPT desktop access to your Mac's Mail, Calendar and Contacts. Search
email subjects, senders and full bodies; read messages; look up contacts and
calendars. Optional email sending and event creation use native human confirmation
by default. It uses the accounts already configured in your native apps.

**Apple Silicon macOS · Local data access · [AGPLv3](LICENSE)**

## Let your AI install it (recommended)

Copy this prompt into **ChatGPT desktop with local computer/Terminal access,
Codex, or another agent that can run commands on your Mac**:

```text
Install https://github.com/UliPrantz/macos-personal-mcp on my Mac for ChatGPT
desktop. Follow docs/INSTALL_WITH_AGENT.md and handle setup, configuration and
verification yourself. Inspect any existing checkout, preserve my other MCPs
and approval settings, and start new installs read-only. Ask me only for macOS
permission dialogs or a restart you cannot complete yourself.
```

The agent handles cloning, Python/dependencies and connecting the tools. You may
still need to approve macOS permission dialogs. A cloud-only browser agent cannot
install software on your Mac. The repository is public; cloning needs no GitHub
account. [Full agent instructions](docs/INSTALL_WITH_AGENT.md).

## Install it yourself: three steps

Requires **Apple Silicon macOS**, Git, internet access and ChatGPT desktop with
local MCP support. The installer supplies Python and dependencies inside this
checkout. Full archive body search is currently validated on **macOS 26.5.2**;
other versions have no validated large-scope native-index support.

**1. Install.** For a new checkout, paste into Terminal:

```sh
mkdir -p ~/Developer/Projects
git clone https://github.com/UliPrantz/macos-personal-mcp.git ~/Developer/Projects/macos-personal-mcp
cd ~/Developer/Projects/macos-personal-mcp
sh scripts/install.sh
```

If prompted to install Apple's Command Line Tools, finish that installation and
rerun the script. The first install can take several minutes. Keep the checkout
at this location. If it already exists, inspect it first; see [updating](INSTALL.md#updating).

**2. Connect.** Open **ChatGPT → Settings → MCP servers → Add server**:

| Setting | Enter |
| --- | --- |
| Name | `macos-personal` |
| Transport | `STDIO` (local process) |
| Command | The absolute executable path printed by the installer |
| Arguments | `serve` and `--read-only` as two arguments |
| Tool timeout, if offered | `240` seconds |

Save and **Restart** that connection. For config-file users, the installer also
prepares `.local/chatgpt-mcp.toml`; merge only its server table into your host
configuration, preserving other settings. It does not edit your host config.

**3. Allow access and try it.** Allow the Mail Automation, Calendar and Contacts
permission dialogs for the features you use. If Mail-file search is denied,
check **System Settings → Privacy & Security → Full Disk Access** for the app or
helper running the MCP, then restart it if macOS requests that. Ask ChatGPT:

```text
Check macos-personal with doctor, then find emails about the project deadline
from the past three days and read the most relevant result. Report incomplete
search coverage.
```

You should see the combined `mail_search` tool and be able to read a result.
New installs expose 16 read tools. No manual body indexing or separate mail-provider
login is needed. [Troubleshooting and removal](INSTALL.md#troubleshooting-and-removal).

**Want sending and event creation?** Replace the server arguments with:

```text
serve --enable-mail-send --enable-calendar-create --enable-calendar-open
```

Restart the connection. Sends and event creation require native human confirmation
by default. [Approval options](#approval-and-writes) include deliberate owner
configuration to delegate consent handling to the host/model.

[Detailed installation](INSTALL.md) · [Usage examples](docs/USAGE.md) · [Measured status](docs/STATUS.md)

## Current capability

The combined `mail_search` and search-to-message-read workflow are verified
through the actual desktop tools, alongside Calendar and Contacts. Native search
reports coverage and missing/partial bodies explicitly. Recent scopes are fast;
archive searches can exceed two seconds and do not certify exhaustive coverage.
See [measured status](docs/STATUS.md) for exact checks, OS limits and gaps.

New installations expose **16 read tools**. Optional send/create/open flags expose
**19 tools**; the legacy FTS cache is hidden unless explicitly enabled. Invitations
are outside this native-only version. The client owns the STDIO process lifetime;
there is no listener, scheduler or autonomous background indexing service.

A process reload is needed after Python/backend or approval configuration changes.
Keep the checkout at its registered path. No interactive shell, dependency
resolution or network download is needed when the MCP normally starts.

## Implemented surfaces and limits

- Mail: account discovery; nested mailbox paths and unread counts; explicit
  account/folder/date metadata listing and sender/subject search; targeted body,
  raw recipient/reply headers and attachment metadata with RFC identity checks.
- Calendar: public EventKit calendars/source/subscription/writability; bounded
  recurring occurrences, exact occurrence reads, title/location/notes search,
  timezone provenance and all-day civil dates. Eighteen calendars are visible;
  Calendar.app reports 20, so all-account reconciliation remains incomplete.
- Contacts: public unified identities, name/organization/phone/email search,
  labeled phones/emails, postal addresses and deterministic pagination. Limited
  access is reported; restricted notes are deliberately unavailable.
- Mail preparation: exact configured sender, literal To/CC/BCC, content and local
  regular-file attachment hashes. A preview is never permission to send.

Mail account/header/targeted API reads use public Apple Events through a fixed
bundled script; native body search reads the local catalogue, MIME and Spotlight
formats. Calendar/Contacts
use public PyObjC APIs in bounded disposable Python workers. No executable script
is constructed from tool inputs. See [the worker decision](docs/decisions/0003-public-native-read-workers.md)
and STATUS for real scopes, timings and permission evidence.

Every tool publishes strict input/output JSON schemas. Unknown fields, coercions,
naive instants and invalid ranges fail. Mail ranges are lower inclusive/upper
exclusive. Pages use deterministic ordering over a fresh bounded enumeration;
concurrent changes can shift offsets. Mail/event scopes over 5,000 candidates and Contacts over 50,000 fail rather
than silently dropping rows. Targeted reads observe unread state and never
speculatively restore flags. Bodies are bounded by Unicode code points.

## Full-body search and local state

Use **`mail_search`** for on-demand search across locally stored accounts/history.
It searches subject, sender and body by default, with optional `account_id`,
`mailbox_path`, aware `since`/`before` and `unread_only` filters. No manual indexing
step or body shadow database is required. For example:

```json
{"query":"budget \"next week\"","since":"2026-10-21T00:00:00+01:00","before":"2026-10-24T00:00:00+01:00"}
```

Unquoted tokens are ANDed across selected fields: one token may occur in the
subject and another in the body. Each quoted exact phrase must occur within one
field; it cannot span a subject/body boundary. Phrases preserve normalized spacing,
order and punctuation. Matching uses Unicode NFC/casefold and preserves accents.
Set `"search_fields":["body"]` for body-only search, or choose any nonempty subset
of `subject`, `sender` and `body`. Quote addresses and other punctuation-bearing
text, for example:

```json
{"query":"\"person@example.com\"","search_fields":["sender"]}
```

FTS5 Boolean/column syntax is unsupported in this tool.
Optional `fuzzy_distance: 1` or `2` accepts one ASCII alphanumeric word of 4-40
characters and reports matched spellings. Native expansion can hit a work limit,
especially at distance two. Semantic search is not implemented.

Headers are checked first. Header-proven matches do not require a body read;
queries selecting only subject/sender need neither MIME nor Spotlight access.
If at most 500 messages still need body matching after the header checks, read
their original MIME directly. Larger unresolved sets reuse Apple's existing
term/posting/metadata index, selecting candidates
for query predicates still unmatched in the headers, plus bounded missing/pending
exceptions. If headers already match every scoped message, even a larger search
uses only the catalogue. A header match must not become an unnecessary body-index requirement.
The indexed route currently requires the
verified macOS 26.5.2 profile. Native stores are read-only. No provider connection,
permission bypass, index scan at startup or independent background service is used.
A lazy reader child keeps identity/fingerprint caches only until disconnection.

Results use the `native-mail-v2` contract. Each hit includes `matched_fields`, a
bounded normalized text `excerpt` and its `excerpt_field`; these identify observed
matching evidence, not every field that might match. Results remain newest-first.
`searched_headers` and `header_matches` separate header checks and header-proven
matches from actual body reads. Results also expose `execution_complete`, `exhaustive`, native coverage, partial and
unavailable bodies, unsearched candidates and errors. Finished execution does
**not** mean complete archive coverage; `exhaustive` stays false. Partial Mail
files and recoverable malformed messages can yield useful positives but remain
counted partial. HTML extraction is a static heuristic, not Mail rendering parity.
Pagination requires the previous `snapshot` when `offset>0`; changed sources
invalidate it. Current limits are 100,000 catalogue rows, 500 exceptions, 2,000
candidate bodies, 20 MB/source, 100 MB source bytes/query and 120 seconds total.
A limit or incomplete zero never proves absence.

The earlier version 0.2.0 body-only implementation on this Mac searched a fixed
week of **401/401 local bodies**, with zero unavailable
and 108 partial, at warm SDK p95 **1.16 s** across seven queries. A three-day
185-message query took **0.54 s**. Archive queries resolved native identities for
42,549 of 42,595 catalogue rows, with 239 bounded exceptions: first indexed query
**4.02 s**, representative warm queries **1.96–3.05 s**. Some broad queries hit
explicit limits. Those archive timings do not meet the universal 2-second warm
target. These are historical body-only measurements, not benchmarks of the new
combined semantics. See [status](docs/STATUS.md) for current evidence and the
[unified search contract](docs/decisions/0013-unified-mail-search.md).

The **legacy explicit-scope FTS5 fallback** is omitted and rejected by default.
Add `--enable-legacy-mail-search` to the server's startup arguments only when you
need it; this exposes the distinct `mail_search_legacy` tool (17 read-only tools,
or 20 with writes). It searches
complete decoded bodies plus subject/sender, supports FTS5 token/phrase/Boolean/
column syntax and Latin diacritic folding. Its older verified Inbox scope covered
182 messages; it does not imply that all accounts have been indexed. The following
maintenance steps apply only to that fallback. It is never automatically merged
with unified search or refreshed during a search call:

Create a private JSON file with explicit `account_id`, `mailbox_path`, aware
`since`/`before`, empty `query`, `unread_only=false`, and `offset=0`. IDs and folder
paths come from Mail discovery tools. Refresh only your owned cache explicitly:

```sh
.venv/bin/macos-personal-mcp index --scope-file /absolute/private/scope.json --max-messages 20
```

Repeat until `complete=true`; each call resumes at most 1-200 missing/changed
sources. Indexing can download bodies and is separate from query latency. Source
errors expose pending/unavailable counts and error codes. Attachments, inline
media and embedded RFC attachments are excluded from body text.

`mail_search_legacy` requires the exact indexed account/folder/date bounds. It refuses missing,
incomplete, older-than-30-minute or changed-inventory scopes. Every query checks
current native identity/metadata; it never refreshes the cache or substitutes
headers. Refresh explicitly when stale. To re-fetch same-identity source bytes,
use `--rebuild-index` on the first maintenance call, then omit it while resuming.
See [index semantics, measured limits and lifecycle](docs/decisions/0005-public-mail-source-and-explicit-fts-index.md).

**Upgrade from 0.2.0:** rediscover tools after reload. Calls that used
`mail_search_native` now use `mail_search`; add `"search_fields":["body"]` to retain
body-only matching. Old FTS callers must explicitly enable and call
`mail_search_legacy`. The new `mail_search` schema and versioned result are a
breaking contract change, not an alias for FTS. No stored cache is deleted.

Owned state lives under `~/Library/Application Support/macos-personal-mcp` (0700):
`mail-body-index.sqlite3` (0600), a separate minimal write-outcome journal and
frozen send attachments. To discard only search data, stop active index/search
calls and remove only the body-index file and its own SQLite sidecars. Preserve
`write-outcomes.sqlite3` and unresolved send snapshots. Never delete native Mail
storage. Private test evidence remains ignored under `.local/`.

## Approval and writes

Read-only mode is the default and omits **and rejects** source/UI-mutating tools.
Enable the optional native executors explicitly when you want writes. The guarded
profile has been verified through actual desktop discovery and native review.
Read annotations do not imply that native applications stop synchronizing.

`serve --enable-writes` exposes schemas but keeps execution disabled.
`serve --enable-mail-send` explicitly enables the native Mail executor. Under the
default native approval policy, each send opens a human review dialog containing
all addresses, the full body and attachment identities. Cancel/timeout/missing UI/changed attachments dispatch
nothing in native mode; no model `approved` flag or confirmation token is
accepted in either mode. Native approval/cancellation and one controlled real STDIO send passed. Sent/recipient
RFC identity and delivered attachment bytes matched; the received message was
read through this desktop MCP with unchanged flags. Allow at least 240 seconds
for host tool timeout in this optional mode.

The local policy file is:

`~/Library/Application Support/macos-personal-mcp/permissions.toml`

An absent policy file defaults to `native`. To remove **all MCP-server approval
popups** and delegate consent handling to the host/model, use:

```toml
[approval]
default = "host"
```

Or choose different defaults by domain and override individual tools:

```toml
[approval]
default = "native"
mail = "host"
calendar = "native"
contacts = "host"

[approval.tools]
mail_send = "native"
calendar_create_event = "host"
```

Tool overrides win over domain and global defaults. `native` means independent
human review for send/create; `host` means no server confirmation dialog and no
claim that the server verified human consent. Contacts/read tools and event
opening already have no server dialog in either mode. Contacts remains read-only.
The file cannot enable missing executors or override `--read-only`. Native OS
permissions, validation, identity checks, snapshots and retry protection remain.

The host may still prompt under its own policy. The generated host snippet uses
`default_tools_approval_mode = "writes"`; host auto-approval/per-tool settings are
separate from this file and are not changed automatically. See the
[official host configuration](https://learn.chatgpt.com/docs/extend/mcp).

The policy is loaded once at startup; reload the connection after changing it.
An absent default file retains native review; invalid/unsafe config and a missing
explicit `--config /absolute/path.toml` fail startup before any native request.
Inspect effective policy without reading native apps:

```sh
.venv/bin/macos-personal-mcp policy --enable-mail-send --enable-calendar-create --enable-calendar-open
```

[Native defaults](examples/permissions.toml), [host delegation](examples/permissions-host.toml)
and [policy contract](docs/decisions/0010-owner-configurable-server-approval.md).

A durable operation-ID/digest journal prevents blind retries, including after a
crash or timeout. Mail accepting a send command is not delivery proof. Inspect
Mail and the recorded outcome before any further action; do not change operation
IDs to bypass uncertainty. Frozen attachment folders remain after dispatch until
Mail no longer needs them and the outcome is resolved. Denied/preparation-only
snapshots are removed. See [approval and lifecycle](docs/decisions/0004-native-mail-approval-and-outcome-journal.md).

`serve --enable-calendar-create` independently enables Calendar creation with the
same configurable native/host review and durable outcome journal. Supply an
exact writable `calendar_id`, operation ID, title and either aware `start`/`end` instants or
`all_day_start`/`all_day_end_exclusive` civil dates, plus an IANA `timezone`
(default Europe/London). Optional location, notes and URL are shown in full.
No attendees are accepted. Calendar/source identity is rechecked after approval;
there is no fallback calendar. Cancel performs no write, and uncertain outcomes
must not be retried. The native result is compared to the reviewed payload;
provider synchronization is outside that acknowledgment. Both explicit executor
flags may be combined, with a host timeout of at least 240 seconds. Neither flag
can be combined with `--read-only`. The optional guarded profile combines all
three explicit executor flags; the server default remains read-only.
See [Calendar approval and limits](docs/decisions/0006-reviewed-calendar-creation.md).

`serve --enable-calendar-open` independently enables Calendar's visible native
`show` command for an exact current nonrecurring event. It validates the selected
EventKit calendar/event, resolves the public item identifier and checks Calendar's
exact UID/content/dates before showing it. Native acknowledgment is returned;
visual display requires human observation. Recurring occurrence opening fails
before any UI command because exact occurrence selection is not proved. This
flag conflicts with `--read-only`; it does not enable sends or event creation.
See [native opening and identity mapping](docs/decisions/0007-exact-native-event-opening.md).

Attendee/invitation creation and direct provider API integrations are deliberately
outside scope. No invitation tool, provider login, private attendee setter or ICS
substitute is provided. Reading existing event attendees remains supported.
See [native-only scope](docs/decisions/0008-native-only-scope-without-invitations.md)
and [guarded desktop activation](docs/decisions/0009-guarded-native-desktop-profile.md).

## Development and verification

Normal CI/tests use only synthetic data and never call native data getters or
send messages. The workflow targets the pinned interpreter, runs Ruff, strict
Pyright, functional tests, wheel build and script compilation. It has now passed
remotely on Python 3.15.1; see STATUS.md for the run and remaining native gates.

The production-target `.venv` now uses Python **3.15.1**. Tested local checks:

```sh
.venv/bin/python -m pytest
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/pyright --pythonpath .venv/bin/python
```

Live reads are separately opt-in and must fail when apps are inaccessible:

```sh
MACOS_PERSONAL_MCP_LIVE_READ=1 .venv/bin/python -m pytest tests/test_live.py
```

Native approval/cancellation, a specifically authorized controlled self-send,
recipient/Sent state and delivered attachment-byte checks passed during
pre-release verification. General implementation or installation authorization
does not authorize arbitrary messages or invitations.

For upgrades, sync the locked target environment and repeat protocol/native/
desktop checks before enabling its entry. To uninstall a future registration,
remove only this project's MCP table, then its isolated `.venv`; do not remove
other tools or native application data. The configured entry is `macos-personal`;
preserve all unrelated MCPs.

Read [AGENTS.md](AGENTS.md), [contract](docs/PROJECT_SPEC.md),
[prior evidence](docs/LOCAL_EVIDENCE.md) and [handoff](docs/CODEX_HANDOFF.md).

## License and credit

Copyright © 2026 Uli Prantz. Licensed under **GNU AGPLv3 only**
([AGPL-3.0-only](LICENSE)). Preserve copyright and license notices. Distributed
derivatives must comply with AGPL's corresponding-source and copyleft rules;
modified versions offered over a network must offer source to their users.
The full license controls. Third-party notices remain in [THIRD_PARTY.md](THIRD_PARTY.md).

Commercial use is allowed without a royalty or mandatory notification. If you
use this commercially, I'd love to hear about it: [get in touch on GitHub](https://github.com/UliPrantz/macos-personal-mcp/issues).
That is a voluntary request, not an additional license condition.
