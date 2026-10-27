# Current state

Updated: 27 October 2026. Package version **0.3.4**.

## Capabilities

| Area | Current support |
| --- | --- |
| Mail | Account/mailbox discovery, metadata listing, header and combined subject/sender/body search, exact message and RFC-source reads |
| Calendar | EventKit calendar discovery, bounded event reads/search, recurring occurrence identities, optional selected-calendar creation and exact nonrecurring event opening |
| Contacts | Read-only lookup and pagination on compatible hosts; the tested direct ChatGPT build is blocked as described below |
| Writes | Optional Mail sending with attachments and exact native replies, plus Calendar creation; native human review by default, with explicit owner-controlled host delegation |
| Permissions | Nonprompting doctor, explicit per-domain setup, host context and actionable errors |
| Installation | Isolated installer, manual instructions and an agent installation prompt; 17 default tools, 20 with all optional executors enabled |

One canonical `mail_search` reuses native Mail storage and Apple's index without
building a second body database. Legacy FTS is hidden unless explicitly enabled
and maintained; it is never silently substituted. Contacts creation, editing and
deletion, Calendar invitations and semantic search are not implemented.

## Verification

**259 synthetic/protocol tests passed; three opt-in live tests were skipped.**
Ruff format/check, strict Pyright, wheel build/inspection, installer shell syntax
and all three JXA compilations passed. [CI](https://github.com/UliPrantz/macos-personal-mcp/actions/workflows/ci.yml)
repeats these checks. SDK STDIO discovery covers both Contacts backends and
protocol modes without reading native data. Normal tests never read personal
apps or send messages/events.

The following are earlier live measurements on the development Mac, not tests
repeated during documentation cleanup or guarantees for another installation:

| Check | Observed result |
| --- | --- |
| Desktop mixed-field Mail search | 0.218 s; 47 bodies searched, zero unavailable, 16 partial; reversed phrase returned no match |
| Desktop three-day negative | 0.645 s; 185 bodies searched, zero unavailable, 57 partial; observed flags unchanged |
| Search-result identity readback | Exact message and RFC source read successfully; malformed/changed identities rejected |
| SDK weekly Mail controls | 401 locally readable bodies searched, zero unavailable, 108 partial; keyword, phrase, date, fuzzy, pagination and negative controls passed |
| Archive search | About 42,600 physical records; sender-only query 0.632 s, first indexed mixed query 5.394 s, warm body control 2.459 s; coverage remained incomplete |
| Contacts via managed launcher | List, exact-ID get and negative search passed across 619 exposed records; initial list about 12 s, concurrent get/negative calls about 35–36 s |
| Direct ChatGPT Contacts | Framework and Contacts.app reads blocked by the host's missing Address Book entitlement, including after Automation consent |
| Controlled native effects | Approval/cancellation, one explicitly authorized self-send, delivered attachment bytes and selected-calendar creation verified during pre-release development |

An isolated installation in a checkout path containing spaces also passed,
including locked dependencies, generated configuration and SDK startup from an
unrelated working directory. This is not proof on every Mac or of a first-time
permission dialog under every host. No exactly-once email delivery is claimed.
The existing one-trailing-space draft guard was exercised by approved native
self-sends observed in Sent and at the recipient. Separately, delivered MIME
confirmed Mail adds a leading empty paragraph and quote wrapper to scripted
bodies. Changing content assignment order did not fix that. A mailto candidate
opened a compose window without an accessible new outgoing object and stopped
before sending; its uncertain operation was not retried. Neither failed candidate
is shipped. [Evidence and decision](decisions/0019-mail-scripted-body-formatting.md).

An approved controlled native reply was observed in Sent and Yahoo Inbox with
`In-Reply-To` and `References` pointing to the exact original message; the received
body contained the approved text and reading the source preserved its unread flag.
An earlier subject-only send grouped visually in Apple Mail but had neither header. Scripted-body MIME still
has Mail's added empty paragraph and quote indentation; native reply support
does not fix that formatting limitation. The one-trailing-space draft allowance
and old-journal digests are preserved. [Reply decision](decisions/0020-exact-native-mail-replies.md).

## Current limits

- Mail can add a leading blank line and quote wrapper to scripted new messages
  and replies after draft readback. Sending acknowledgment does not prove final
  MIME formatting or recipient receipt; the controlled native reply's headers
  were checked in both Sent and received source, not inferred from its subject.

- Large native-index searches are validated only on **macOS 26.5.2**, header 114
  and the observed LZ4 metadata profile. Unsupported formats fail explicitly;
  scopes with at most 500 unresolved bodies can use direct MIME reads.
- Search `exhaustive` remains false. Partial or absent bodies, unsupported
  metadata, identity failures, changing/lagging checkpoints and work limits can
  omit matches. `execution_complete` does not establish exhaustive coverage;
  an incomplete zero never proves absence. A measured archive query read 270/272
  candidates with two identity failures, 154 partial bodies and 394 unsupported
  metadata records.
- Account/mailbox filtering follows the 100,000-row global catalogue bound.
  Small scopes can therefore hit that bound and perform unnecessary work.
  SQL scope pushdown is a possible optimization; it is not implemented.
- The universal two-second warm archive-search target is not met. Fuzzy search
  is bounded ASCII spelling similarity; semantic search is absent. Contacts
  full-detail reads can also be slow.
- The tested direct **ChatGPT Desktop 26.1021.31345** lacks
  `com.apple.security.personal-information.addressbook` and
  `NSContactsUsageDescription`. Automation consent cannot supply those
  declarations. Contacts remains available for compatible hosts and future app
  updates after a grant and actual read verification; no helper is provided.
  [Permission details](PERMISSIONS.md#contacts-refused-without-a-dialog-in-chatgpt).
- Calendar/Contacts visibility depends on grants and configured sources;
  all-account reconciliation is not established. Contact IDs differ between
  unified framework records and non-unified Contacts.app records.
- Calendar attendee/invitation creation is deliberately excluded. Event opening
  supports exact nonrecurring items; native acknowledgment does not establish
  that an event was visibly displayed.
- OS grants, executor flags and per-action approval policy are independent.
  Running connections need reload after code or configuration changes. Success
  under one launcher does not establish another host's access.

## Maintenance references

- [Technical details and development checks](TECHNICAL_DETAILS.md)
- [Behavior contract](PROJECT_SPEC.md) and [design decisions](decisions/)
- [Native index format](NATIVE_MAIL_INDEX_FORMAT.md)
- [Mail implementation comparison](MAIL_MCP_COMPARISON.md)
- [Permission implementation comparison](PERMISSION_MCP_COMPARISON.md)

The public repository uses AGPL-3.0-only and begins with a clean initial release.
Private native-data evidence, credentials and pre-release history are excluded.
Raw diagnostics belong outside Git; publish only scoped, anonymized results.
