# Product and implementation contract

## Goal

Give the owner's native ChatGPT desktop client one reliable local MCP for Mail,
Calendar and Contacts. Build the agreed native subset of
[supermemoryai/apple-mcp](https://github.com/supermemoryai/apple-mcp) fresh in Python, and prove the result against this Mac. Do not inherit upstream
placeholders, silent failures or parsing shortcuts.

The owner explicitly requires fast complete email body search. Scoped header
search is an additional useful tool, not a substitute for that requirement.
On 24 October the owner clarified the product bar: prioritize recent mail
(especially the last week) and practical parity with Apple Mail search; a few
missing older messages do not invalidate a useful backend. This does not turn
unknown coverage into a completeness guarantee. See decision 0011.

## Runtime

- One installable Python package/console entry point, launched over STDIO by the
  desktop client. Absolute executable paths must work without an interactive
  shell, current-working-directory assumptions, network downloads, or uv resolving
  dependencies during every client launch. Prefer an installed isolated tool.
- No always-running server, HTTP transport, tunnel, LaunchAgent, scheduled send,
  periodic indexing, or server-managed autonomous jobs.
- A process can remain alive for a connection. Each tool call must have explicit
  inputs and survive disconnect/restart without hidden conversational state.
- Persistent local index, configuration and a minimal write-outcome journal are
  allowed. Store this MCP state in documented application-data locations with
  owner-only permissions. Native applications retain their own account credentials;
  do not copy or read those credentials.
- Native macOS integration only: no direct Google/Microsoft/CalDAV/HTTP provider
  clients, provider SDKs, OAuth login or cloud fallback. Mail/Calendar may fetch,
  send and synchronize using their existing native accounts. This MCP adds no
  independent provider connection. Attendee creation is excluded; see decision 0008.
- Python application/adapters, strict typing, uv lockfile, public native APIs.
  Prefer PyObjC Contacts/EventKit and prove Python Mail access. Avoid new language
  backends. If minimal fixed OS scripting is necessary, explain it in a decision
  record and validate every boundary; no interpolated executable scripts.
- No UI automation. An explicit command to open an event, or an actual human
  approval dialog if chosen, is different from screen-driven data extraction.
- Include a doctor/capabilities command that reports permission status and
  supported routes without writing test objects or requesting broad permissions
  merely to inspect status. Missing one app's permission must not disable others.
  Doctor must distinguish not-determined, denied, restricted, Calendar write-only
  and Contacts limited states and return concrete per-domain next actions. Report
  observed host paths without claiming they prove macOS's responsible identity.
  An explicitly invoked `request_permissions` tool may request one selected
  Calendar/Contacts grant through public APIs; it is separate from ordinary reads
  and startup. It remains available with source writes disabled, with truthful
  non-read-only/non-destructive setup annotations. No grant, executor enablement
  or test event/contact may be fabricated. See decision 0016.

## Required tool behavior

Use distinct tool names for operations with different effects. Proposed names
below may be refined, but the capabilities and approval separation must remain.

### Mail

- `mail_list_accounts`, `mail_list_mailboxes`: enumerate real configured accounts
  and folder hierarchy, stable selectors where possible, unread counts and scope.
  Include nested folders and local folders explicitly; report inaccessible ones.
- `mail_list_messages`: newest messages, optional unread filter, metadata-only
  default, deterministic ordering and pagination. Counts must identify their
  scope and whether exact, cached or incomplete.
- `mail_search_headers`: sender/subject and supported metadata filters, explicit
  account/folder/date scope, pagination, coverage and truncation. Date ranges are
  lower-inclusive/upper-exclusive. Do not retrieve every body for this operation.
- `mail_search`: one canonical native search over subject, sender and body by
  default. `search_fields` selects a nonempty subset; body-only remains supported.
  AND predicates may match across fields; each quoted exact phrase must occur
  within a single field. Unicode NFC/casefold preserves accents. Received-date,
  account, mailbox and unread filters narrow scope. Return newest-first bounded
  pages, supporting `matched_fields`, a bounded normalized excerpt and its field,
  and explicit coverage/error counts. Header-proven matches survive body-read
  limits; header checks must not be counted as searched bodies. Select native
  body candidates using predicates not already satisfied in headers.
  Header-only searches do not require Spotlight or MIME access. At most 500
  messages still requiring body matching use direct MIME; larger unresolved sets
  use the native index. A search fully proven by headers uses only the catalogue,
  regardless of its row count within the catalogue limit. Quote addresses, for
  example `{"query":"\"person@example.com\"","search_fields":["sender"]}`.
  Keywords, exact
  phrases, date ranges and bounded ASCII fuzzy spelling are implemented; Boolean
  operators and semantic search are not. Spelling similarity is not semantics.
  Decision 0013 defines the `native-mail-v2` contract and breaking migration from
  the separate version 0.2.0 tools. Desktop activation is verified for the measured
  scopes in STATUS.md. Search result selectors must work directly in message and
  source reads; one well-formed outer RFC angle-bracket pair is equivalent to
  Mail's public unwrapped identity, with the enclosed value preserved exactly.
- `mail_search_legacy`: explicitly enabled FTS5 compatibility/fallback tool only.
  Omit and reject it unless startup includes `--enable-legacy-mail-search`.
  Preserve exact declared account/folder/date scope, explicit index maintenance,
  complete ingestion and 30-minute/current-inventory freshness guards. Its FTS
  Boolean/column queries, accent folding and plain/HTML alternative handling
  differ from unified search; never silently merge or substitute its results.
  Every decodable full body in a scope declared complete must be searchable,
  not only previews or the newest N messages.
- `mail_get_message`: selected full body, metadata/recipients, RFC Message-ID,
  available In-Reply-To/References and attachment metadata. Validate the expected
  RFC identity when using local numeric IDs. Fail on mismatch instead of reading
  an unrelated message. Bound returned size and clearly report truncation.
- `mail_send`: explicit configured sender, arrays of To/CC/BCC recipients,
  subject, body and local attachment paths. Validate recipients, aliases and
  attachment availability before approval. Support multiple recipients and
  attachments. Verify delivered attachment bytes in a controlled live test.
  Accept Mail's observed single appended ASCII space in an outgoing body, while
  rejecting other content changes. Draft verification failures must explain that
  sending was not attempted; retain a safe diagnostic code without weakening
  the durable no-blind-retry barrier or logging/storing message payloads.
- Preserve read/unread flags during reads. Reading may fetch a remote body;
  expose unavailable, encrypted or slow bodies as such. Do not claim they were
  searched when they were not. Metadata operations should avoid body reads.
- Reply/forward and attachment extraction are useful extensions, but not required
  by the original feature list. Do not let them delay the required operations.

### Full-body index acceptance gate

First establish an authorized, complete-enough data source. Investigate read-only
Mail database/EMLX access with real schema detection, a supported native export
path, or another public native source. Subsequent authorized read-only research
has demonstrated native dictionary/posting retrieval on this Mac; see
EXPERIMENTS_NATIVE_MAIL.md. Reading observed on-disk formats does not authorize
private API invocation or native-store writes. No privacy bypasses, copied
credentials, private APIs, or silent changes to Full Disk Access settings.

If indexing local Mail files, open source databases read-only with parameterized
queries. Never change their schema, flags, WAL settings or journal mode. Do not
use SQLite immutable mode to pretend a live changing database is a snapshot.
Use consistent source access and write only to our own index. Decode MIME,
charset/transfer encoding, multipart alternatives, HTML-only text and long bodies
with synthetic tests. Do not count attachments as body text without documenting
an explicit additional feature.

If an owned index is selected, prefer SQLite FTS5 when benchmarks support it. Initial build
and incremental refresh are explicit bounded/resumable operations. Keep them
outside pure read tool handlers: a read-only search must not secretly mutate its
index. A separate `mail_refresh_index`/CLI command may update only our cache and
must be annotated honestly as a non-destructive local write. The host can grant
this maintenance operation a different policy from sends.

Track corpus/folder coverage, source snapshot/freshness, indexed and missing
counts, errors, exclusions and refresh time. Account for additions, changes,
moves, deletes and source rebuilds; do not duplicate a message just because an ID
changed. Define stale-index behavior. Never call a result complete for the current
mailbox if the source watermark/coverage does not justify it. Offer explicit
partial results only with `complete=false` and the missing scope/reason.

Benchmark goals after an index is built: indexed query execution p95 <= 1 second
and warm end-to-end MCP search p95 <= 2 seconds on a declared representative
corpus on this Mac. Measure cold process startup separately. Do not mix initial
indexing time into a warm benchmark or use tiny synthetic performance as proof
of real-account completeness. Goals are targets until actual measurements exist.

If protected source access or missing bodies block this gate, ship independent
working tools but leave full-body search clearly blocked in STATUS.md. Report
the exact access/backend decision needed. Do not declare the overall project
complete by quietly substituting bounded body scans or header-only search.
Known small historical gaps may be reported as partial coverage while useful
native-index results ship. Distinguish catalogue/identity coverage, sampled
retrieval recall, current Mail parity and exhaustive body coverage. Native
checkpoint membership alone is not proof of every word's presence. A recent
message known to be pending or absent needs a bounded fallback or an explicit
unavailable reason. The native-first route is exposed through unified
`mail_search`; `mail_search_native` is removed. See STATUS.md for current native
and SDK/actual-desktop verification.
Decisions 0012 and 0013 record native limits and current unified semantics;
execution completion is distinct from exhaustive body coverage, which is never
claimed. Header matches provide useful evidence without certifying body coverage.

### Calendar

- `calendar_list_calendars`: real calendars, identifiers, source/account,
  read/write capability and shared/subscription status where available.
- `calendar_list_events`, `calendar_get_event`: bounded date range, recurring
  occurrences, title, start/end with timezone, all-day dates, location, notes,
  URL, calendar ID, attendees and identifiers where available.
- `calendar_search_events`: text search in title, location and notes, within an
  explicit date/calendar scope, with deterministic ordering and coverage.
- `calendar_create_event`: title, start/end/timezone or all-day dates, location,
  notes, optional URL and explicit writable calendar. No fallback to a different
  calendar if the requested one is absent or read-only.
- `calendar_open_event`: show the exact selected event using a native command;
  merely launching Calendar is not success.

Attendee/invitation creation is intentionally outside scope. Public EventKit
cannot add participants and Calendar's scripting attendee properties are read-only.
The owner chose to omit this feature rather than add a provider API connection.
Do not implement or expose `calendar_create_invitation`, request provider login,
use private setters/screen automation, or substitute an ICS email. Existing
attendees may still be read from native events without notifying anyone. See
[the native-only scope decision](decisions/0008-native-only-scope-without-invitations.md).

Use public APIs. Do not set private attendee properties through Objective-C KVC
or private classes. Calendar update/delete, contact mutation and broad invitation
lifecycle management are outside the initial advertised feature set.

### Contacts

- `contacts_search`, `contacts_get`, `contacts_list`: support name/phone/email
  lookup and paginated enumeration; retrieve labeled phone numbers and email
  addresses plus available useful name, organization and address fields.
- Preserve contact identity and duplicate-name candidates. Do not key contacts
  solely by display name or guess which same-name person the owner means.
- Search/reading must work without contact mutation permission where the public
  APIs and granted access allow it. Respect partial/limited access and report
  it instead of promising the complete address book.
- Avoid requesting restricted fields, such as notes requiring extra entitlement,
  merely to satisfy generic full-detail fetching. Report field availability.

## Approval contract

Publish actual input/output schemas and separate these effect classes:

| Class | MCP annotation policy | Approval requirement |
| --- | --- | --- |
| Pure data read | readOnlyHint=true, destructiveHint=false, idempotentHint=true | Eligible for host auto-approval |
| Local index maintenance | readOnlyHint=false, destructiveHint=false; document cache effects | Can have a separate host maintenance policy |
| Open event in local UI | readOnlyHint=false, destructiveHint=false, idempotentHint=true | Describe the visible UI effect |
| Send email | readOnlyHint=false, destructiveHint=true conservatively, idempotentHint=false, openWorldHint=true | Native human review by default; explicit owner config may delegate to host/model |
| Other calendar creation | readOnlyHint=false; treat conservatively as high-risk until calendar visibility is established | Native human review by default; explicit owner config may delegate to host/model |

Set openWorldHint truthfully for read tools too: native apps may synchronize with
external providers. Add human-readable risk/effect descriptions; any additional
risk-level metadata is project-specific and cannot be advertised as standard MCP
enforcement. Annotation idempotency claims do not implement deduplication.

Implement a read-only mode that omits/rejects all source-mutating tools at both
tool discovery and dispatch. Write mode is an explicit local launch/config choice,
never a tool the model can enable for itself. Pure read access should be usable
without enabling writes.

For enabled high-risk tools, verify whether the real host can enforce per-tool
"ask every time". Include all sender/recipient addresses (including CC/BCC),
calendar, subject/title, times/timezone, content and attachment identity
in the reviewed payload. Do not resolve aliases differently after approval.

Native exact human confirmation is the default. A model-generated `approved=true`,
arbitrary token or prepare/commit pair is not independent human approval. In
native mode, denial/timeout/missing UI/changed payload or attachment bytes prevents
dispatch. Review is bound to the exact payload.

The owner also requires an opt-in mode that delegates HITL/consent responsibility
to the host/model, without a server dialog. A startup-only `permissions.toml`
selects `native` or `host` globally, by mail/calendar/contacts domain and by exact
tool (tool > domain > default). No MCP argument changes this policy. Host-mode
execution must be labeled as delegated, not falsely called human approval.
Read tools/Contacts already have no server dialog. Read-only launch mode, enabled
executor flags, native OS permissions, conservative annotations, input/identity
validation, snapshots and outcome/retry guards remain effective in both modes.
Invalid configuration fails closed. See [decision 0010](decisions/0010-owner-configurable-server-approval.md).

Keep external writes separate from reads and index refresh. Use a client-supplied
operation ID and a minimal local outcome journal to prevent blind repeat effects
across restarts. No automatic retry after an uncertain native write timeout. Report
"outcome unknown" distinctly from failure-before-dispatch and verified success.
Mail accepting a send command is not proof of delivery; a live test must verify
receipt/Sent state and attachment contents without promising exactly-once delivery.

## Quality and verification

- Enforce strict typing and linting in CI; preserve the initial settings. Add
  package/build metadata, locked stable SDK/native dependencies and a typed
  versioned structured result/error model. No fabricated successful placeholders.
- Synthetic tests: MIME/Unicode/long-body search, negative and pagination cases,
  coverage/truncation/staleness, identity validation, timezone/DST/all-day/recurrence,
  ambiguous recipients, attachment substitution, approvals, read-only dispatch,
  cancellation, startup/shutdown and uncertain write deduplication.
- MCP subprocess integration: real SDK client, initialize/discovery as supported
  by the negotiated protocol, exact tool set/annotations, schemas, invalid inputs,
  representative read, error behavior, EOF exit, timeout and child cleanup.
- macOS live reads: repeat the known Mail tests, verify a truly unread message
  remains unread, inspect Calendar and Contacts with declared scope and no
  writes. Read live data only as needed for the authorized verification.
- Controlled live effects need separately concrete approved test recipients and
  payloads. Stage previews first. Private test events should use an explicitly
  chosen test calendar; cleanup operations need their own authorization/scope.
- Final desktop verification: register a stable absolute Python entry point via
  the existing native STDIO route. Modify only this project's MCP registration,
  preserve WhatsApp/other entries, verify native permissions under the actual
  launching process, call real read tools here, and demonstrate approval denial
  prevents writes. Never infer this from a working Terminal process.

Normal CI contains no credentials and never reads the owner's apps. Marked live
tests are separate, opt-in and accurately reported as passed/skipped/blocked.
The finished README must contain tested install, recovery, index management,
approval configuration and uninstall instructions. Update STATUS.md with measured
capability evidence and pushed commits.

Provide a short human installation guide and a copyable prompt/runbook allowing
an agent with local computer/Terminal access to install and register this MCP.
Keep bootstrap runtimes local, preserve other host configuration, start new
installs read-only, and verify actual desktop tools after registration. An install
prompt does not bypass OS permission dialogs or host restrictions.
