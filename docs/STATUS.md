# Current state

Updated: 25 October 2026. Version 0.3.4. The public release starts with one clean
initial commit under AGPL-3.0-only. The previous repository/history remains a
private archive; no old commit objects are pushed to the public repository.

## What works

- Native Mail account/mailbox discovery, scoped metadata/header search, exact
  message and RFC-source reads, combined subject/sender/body search.
- Public EventKit Calendar reads, recurring occurrence identities and selected
  writable-calendar event creation. Exact nonrecurring event opening is available.
- Public Contacts lookup and paged enumeration on compatible hosts; restricted
  notes are excluded. The tested direct ChatGPT host is blocked as detailed below.
- Mail preparation/sending with attachments, selected-calendar creation and
  separate UI-open enablement. Native human review is the default for send/create;
  deliberate owner configuration can delegate consent to the host/model.
- One default search surface. Legacy FTS requires explicit startup opt-in and
  manual exact-scope maintenance; it is not silently mixed with native search.
- Human and agent installation guides, a README copy/paste prompt and an isolated
  installer. New installs expose 16 read tools plus explicit permission setup
  (17 total); guarded profiles expose 20.
- Doctor reports concrete permission-state actions and observed host paths. A
  separate per-domain tool requests Calendar/Contacts access through public APIs;
  ordinary reads and startup remain nonprompting. See PERMISSIONS.md.

## Verification evidence

The release is based on the tested implementation, not a fresh unverified rewrite:

- **238 synthetic/protocol tests passed**, three live reads skipped by default.
  Ruff format/check, strict Pyright, wheel build/inspection, installer shell syntax
  and all three native script compilations passed. CI repeats the required checks.
- Separate opt-in Mail/Calendar/Contacts native read checks passed. Normal CI never
  reads anyone's live apps or sends messages/events.
- Version 0.3.1 actual desktop discovery showed the expected 19-tool guarded catalog, combined
  `native-mail-v2` search, native approval policy and working Mail/Calendar/Contacts
  access. Legacy/native aliases are absent from the default catalog.
- Actual desktop mixed-field search found the known dated message in **0.218 s**,
  searching 47 bodies with zero unavailable and 16 partial. A reversed phrase
  returned no match. A three-day negative searched **185 bodies** in **0.645 s**,
  zero unavailable and 57 partial; flags remained unchanged.
- Direct search-result selectors read the **820-character** message and
  **45,769-character** RFC source through desktop tools with unchanged observed
  flags. A malformed/changed RFC identity is rejected before content reads.
  The bridge accepts exactly one well-formed outer RFC angle-bracket pair; it
  does not strip whitespace, fold case or accept nested brackets.
- Earlier SDK weekly controls searched **401/401 locally readable bodies**, zero
  unavailable, 108 partial. Combined keyword/phrase/date/fuzzy/pagination and
  negative controls passed. These are local-text observations, not complete MIME
  or index recall guarantees.
- The measured archive contained roughly **42,600 physical records**. Native active
  identities covered 42,554; 236 missing/pending/identity exceptions were counted.
  A mixed query read 270/272 candidates, reporting two identity failures, 154
  partial bodies and 394 unsupported metadata records. These remain incomplete.
  Archive sender-only search took **0.632 s** without MIME reads; first indexed
  mixed query **5.394 s**, warm body control **2.459 s**.
- Native approval/cancellation, one specifically authorized controlled self-send,
  recipient/Sent state, delivered attachment bytes and selected-calendar creation
  were verified during pre-release development. No live effects are part of CI,
  normal installation or the public-release checks. No exactly-once delivery claim.

## Installation checks

A clean isolated runtime was installed in a checkout path containing spaces.
Pinned uv 0.13.5, Python 3.15.1 and locked dependencies installed locally. The
source-build toolchain fallback installed Rust 1.99.1 locally under a restricted
PATH; repeat installation reused the environment. No global runtime, shell profile,
MCP registration or privacy setting was changed by the installer.

A fresh official SDK client launched that executable from `/tmp`, discovered 16
read tools, rejected writes/old aliases and invalid input, then shut down cleanly.
The generated TOML parsed and pointed to the exact executable. This verifies a
clean environment on the maintainer's Mac; it is not proof on a pristine Mac
without Apple's Command Line Tools or on every macOS release.

## Known limits

- Account/mailbox scope is currently applied after the catalogue row bound and
  model validation. A small mailbox can therefore hit the 100,000-row global
  bound, and scoped reads do unnecessary work. SQL scope pushdown is recommended
  but not yet implemented; see the comparison below.
- Large native-index searches are validated only for macOS **26.5.2**, header 114
  and the observed LZ4 metadata profile. At most 500 unresolved body rows can be
  scanned directly without Spotlight. Unsupported profiles are not bypassed.
- `exhaustive` remains false. Partial files, absent bodies, unsupported records,
  lagging/changing checkpoints and bounded work can omit matches. A partial zero
  never proves absence. `execution_complete` means selected work finished.
- The universal two-second warm archive-search target is not met. Fuzzy search
  is bounded ASCII spelling similarity, not semantic search; broad distance-two
  expansion may hit a work limit.
- Calendar/Contacts visibility depends on OS grants and configured accounts;
  all-account reconciliation is not established. Event opening is limited to
  exact nonrecurring items. Visual display is separate from native acknowledgment.
- Direct Contacts access from the tested ChatGPT desktop 26.1021.31345 is blocked
  before any consent dialog: macOS identifies ChatGPT as responsible and reports
  its missing Address Book entitlement. Its Contacts usage description is also
  absent. Contacts.app Automation also failed actual reads after Automation was
  granted: native logs show it checks access on behalf of that same responsible
  ChatGPT app. No Settings toggle or backend switch supplies missing declarations.
  Contacts stays supported for compatible hosts and future app updates after a
  grant and read verification. No helper is being built. See decision 0018.
  The separately launched managed Codex connection succeeded; that does not
  establish direct-host support.
- Calendar attendee/invitation creation is intentionally excluded. No provider
  API/OAuth, private attendee setter, screen automation or ICS substitute is added.
- Host approval policy, executor flags and OS privacy grants remain independent.
  Existing Calendar/Contacts grants work in the verified host. Reload the desktop
  MCP connection for the new 0.3.4 catalog/doctor behavior. New installations must
  verify their own actual host process and permission dialogs.

## README usability and Mail MCP review

The README now leads with everyday workflows and the agent installation prompt.
Manual setup and optional writes remain fully available in expandable sections;
low-level contracts and configuration moved to TECHNICAL_DETAILS.md. The supported
OS profile and AI-app data boundary remain visible without expanding anything.

[The source comparison](MAIL_MCP_COMPARISON.md) covers all four requested Mail
MCPs plus Imdinu, Sift and MP Consulting at pinned revisions. None of the inspected
paths provided a simpler native full-body index interface. Several use owned
incremental FTS5 indexes and offer credible faster search designs. Their published
timings were reviewed, not reproduced on this Mac.

A separate read-only metadata experiment verified identical rows for a 69-row
mailbox: current catalogue loading took median 379.114 ms versus 9.142 ms for a
SQL-scoped prototype over 42,600 active rows (seven iterations). Known-ID lookup
was 0.017 ms; current archive header engine calls were 580.585 ms (five calls).
These exclude MCP transport and body search. The prototype is not a shipped
optimization. No competitor server was run, and no native writes were made.

Recommended next work is exact SQL scoping, measured inventory-cache improvements,
then an equivalent-workload FTS comparison before any architecture change. The
That documentation-only revision retained 0.3.1 and one default search surface.
Version 0.3.2 adds the permission/send-diagnostic changes below; search retrieval
and the owner-configured approval policy retain the same behavior.

## Permission setup and draft-send fix

Read-only inspection tied an existing draft to its reviewed payload and uncertain
write record. Mail's live outgoing body had one appended ASCII space; sender,
subject and recipients matched. The old exact body guard rejects that artifact
before calling send. Checked Sent/recipient scopes had no corresponding copy.
Real subjects, addresses, IDs, bodies and raw logs remain private and ignored.

The writer now accepts exact content or precisely one appended ASCII space;
signatures and other whitespace/content changes remain rejected. A structured
`native_message_changed` failure explains that send was not called. Safe failure
codes persist across journal replay, and old-journal migration preserves uncertain
operation IDs. Other native errors retain conservative outcome uncertainty and
actionable Drafts/Outbox/Sent/receipt guidance. No draft deletion or automatic retry.

Doctor distinguishes first requests from refusal/restriction and supplies
`next_actions` plus observed executable/parent context. `request_permissions`
requests one Calendar or Contacts grant; existing grants are no-ops, and denied/
restricted states direct Settings/admin action. Callback completion alone cannot
claim a grant. Timeouts/undecided results direct host diagnosis rather than loops.
Host privacy metadata and macOS attribution can still block a first request.

Verification: 187 tests, Ruff, strict Pyright, wheel build, installer shell syntax
and Mail writer compilation passed. A read-only synthetic replay of captured
draft properties reaches the corrected send branch without any native dispatch.
A fresh SDK STDIO connection from `/tmp` discovered 17 tools with source writes
absent, actionable doctor output and both existing-grant setup no-ops. The public
Calendar/Contacts request callbacks also completed on already authorized domains,
with unchanged authorization. These do not prove a first-time OS dialog on a new
host. No live send/event or permission reset occurred. Actual desktop discovery
of the new 20-tool guarded profile awaits connection reload; controlled delivery
of a new approved send remains a separate gate. See decision 0016.

## Contacts host block and stale-catalog guidance

An actual direct ChatGPT request on 25 October granted Calendar full access, while
Contacts went from not-determined to denied/error 100 without a user dialog.
The native privacy log attributed the request to ChatGPT and named its missing
hardened-runtime Address Book entitlement. Code-signing/Info.plist inspection
confirmed missing Contacts entitlement and purpose text in ChatGPT 26.1021.31345;
Calendar declarations were present. The Contacts Settings list had no ChatGPT entry.
This is a host-packaging blocker, not evidence that the user refused access.
No app signature, TCC database or privacy grant was modified during investigation.

Version 0.3.3 directs that first-request error pattern to host diagnosis, preserves
the Settings route for a real user refusal, and avoids assuming every denied
state has an app entry. Error guidance covers an old loaded catalog referencing
a new setup tool; doctor now reports its loaded `server_version`. Existing server
registrations/checkout paths are reused. Calendar is working in the tested direct
host; Contacts through this MCP's direct framework route remains blocked there.
See PERMISSIONS.md. Raw native logs and process-specific evidence stay outside Git.

The owner requested existing-solution research before a helper/backend change.
PERMISSION_MCP_COMPARISON.md compares five pinned MCP implementations. Several
use Contacts.app Automation. Own read-only local probes returned 619 IDs in
0.677 s, a negative name search in 0.885 s and bulk email/phone arrays in
1.040/1.484 s. One full selected record took 4.067 s. Native unified enumeration
returned 617 contacts versus 619 non-unified records, so identity semantics must
be explicit. The current ChatGPT build has Apple Events declarations, making
this an established route to test before inventing a helper. These probes ran
under an authorized launch context. The later affected-host Automation test
failed despite consent, while the managed-launcher test passed; details below.
Version 0.3.3 now implements an explicit Contacts.app backend, without automatic
fallback. See the implementation evidence below.

The owner's explicit approval changed the local review policy to host mode;
distribution still defaults to native review. A fresh process verified host mode
for enabled send/create tools, while ChatGPT's host write-review setting remained
enabled. Existing running servers need reload to adopt that startup policy.
This change did not grant Contacts access or trigger a send/event.

## Selectable Contacts.app backend (0.3.3)

After source research, the owner accepted native programmatic automation and
rejected screen-driven computer use. `--contacts-backend contacts-app` selects
public Foundation Apple Events instead of CNContactStore, retaining the same
three Contacts tools. The distributed default stays `framework`. No second
Contacts index, provider connection, UI automation, helper or private-store
adapter was added. Columns are fetched in batches and discarded after each call.

Public authorization preflight never prompts. Every read event also sets Apple's
no-consent-prompt and never-interact flags. Explicit setup alone may open
Contacts.app in the background and request Automation consent. The doctor reports
that selected route; it never pretends the direct Contacts API became authorized.
Record IDs use `contacts-app:` and are not unified across sources. Changed
identity/order/count, malformed nested fields, native errors and deadlines fail
instead of returning incomplete data as a successful empty result.

A fresh official SDK STDIO connection from `/tmp` verified the 17-tool read-only
profile and loaded 0.3.3. Existing Automation consent made setup a no-op. It listed
619 records, returned two disjoint 25-record pages, read an exact contact equal to
its listed data, found matches by name/email/phone and returned a complete
negative in that visible record scope. List/get/name calls initially took
13.002–15.080 seconds; later email/phone/negative queries took 4.622/2.495/2.123
seconds. These are individual end-to-end measurements, not percentile targets.
No native records or OS privacy settings were changed.

The existing local registration explicitly selects `contacts-app`, preserving
its other flags, other MCPs and host write-review setting. Subsequent direct
ChatGPT tests granted Automation but failed list/search on this implementation;
the native privacy logs confirmed the host entitlement block. A separately
launched managed Codex connection successfully listed a record, read the same
ID with equal fields, and returned a complete negative across 619 exposed records.
The first list took about 12 seconds; concurrently issued get/negative calls took
36.011/35.461 seconds. This is useful verification, not a universal performance
claim or proof for the blocked direct host. No native records were changed.

Verification: **211 tests passed, three opt-in live tests skipped**; Ruff and
strict Pyright passed. Separate SDK live reads above are not default CI tests.

## Contacts compatibility guidance (0.3.4)

Contacts remains available by owner decision. Every Contacts tool description and
the setup tool now explain required host declarations, the tested direct ChatGPT
build's limitation, and support for compatible hosts or future compatible builds.
Read errors preserve safe numeric native error codes and distinguish Automation
from data access. Doctor performs a separate nonprompting Contacts status check
for the Automation backend; an Automation grant with unestablished framework
access reports unverified readiness and host diagnosis, not another setup loop.
The framework status is diagnostic context, not a new gate or backend fallback.
Existing worker reply schemas remain compatible with loaded 0.3.3 parents.

Mail/Calendar behavior, the host review policy and startup flags are unchanged.
Reload is needed to see the 0.3.4 tool descriptions and doctor behavior; it does
not fix the direct ChatGPT app's missing entitlement. No additional live data
reads, permission prompts or test writes are needed for this documentation and
diagnostics update.

Verification: 238 tests passed, three opt-in live tests skipped. Ruff format/check,
strict Pyright, wheel build/inspection, installer shell syntax and all three JXA
compilations passed. Real SDK STDIO discovery verifies the guidance for both
Contacts backends and both protocol modes without reading native data. The live
per-host Contacts evidence above predates this diagnostics-only update.

## Public release boundary

The owner explicitly approved public visibility, a single clean initial commit
and standard AGPLv3. The public tree includes source, synthetic tests, format
research and documentation; local native-data evidence, runtime environments,
credentials and old history are excluded. The pre-release 25-commit history was
scanned across 247 unique blobs: no credential-pattern findings, binary data or
Mail/Calendar/Contacts export files were found. This is an audit result, not a
claim of zero risk. A clean repository is used so old objects and Actions history
never become part of the public repository.

A fresh unauthenticated mirror and GitHub checks on 25 October reconfirmed the
clean public root and absence of pre-release commits. At recheck, the public
history contained the initial release and the later documentation update; only
`main` existed, with no tags or pull-request refs. The old archive remained
private and inaccessible anonymously. It is retained privately, not erased.
All 105 reachable public blob versions and both public Actions logs were scanned:
no credential-pattern findings, owner email addresses, personal home paths,
private-topic controls, binary blobs or native data exports were found. Email
literals were synthetic examples, the agent identity and public third-party
license attribution. Public copyright/GitHub identity and anonymized benchmark
statistics are intentionally retained. No issues, pull requests, releases,
deployments or Actions artifacts existed at recheck. This records the audit
scope and findings rather than promising absolute absence of every possible
privacy issue. Raw audit evidence stays outside Git. README feature examples
now include emoji while keeping installation and technical details expandable.

Commercial use is permitted under AGPLv3; it does not require royalties or a
usage report. The README's invitation to get in touch is voluntary. See LICENSE,
NOTICE, THIRD_PARTY.md and decision 0015. Maintain this file as behavior and
verification change; keep raw user data outside Git.
