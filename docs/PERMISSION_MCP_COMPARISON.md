# Local MCP permissions: existing approaches and measured probes

Reviewed 25 October 2026, including the subsequent direct-host test of the optional
backend in [decision 0017](decisions/0017-selectable-contacts-app-automation.md).
Third-party source was inspected at the revisions below; its servers/installers
were not run. No contacts, events, messages, signatures or privacy settings were
changed. Native consent is distinct from approval of a tool's payload.

## Why Mail files and Calendar work while Contacts does not

macOS makes separate decisions for different services and access paths. A grant
is not a blanket permission for everything a local MCP can do.

| Path | Relevant OS gate | Finding in the affected ChatGPT launch |
| --- | --- | --- |
| Mail's protected files | File privacy / Full Disk Access for the effective reader | Working file reads do not authorize CNContactStore |
| Calendar via EventKit | Calendar resource declarations and Calendar authorization | Host has Calendar entitlement and purpose strings; full access requested/granted |
| Contacts via CNContactStore | Address Book resource declarations and Contacts authorization | Missing host entitlement and purpose string; macOS explicitly refuses before a dialog |
| Contacts.app via Apple Events | Automation consent plus Contacts data authorization checked on behalf of the original caller | Automation granted, but actual list/search refused; native logs again identify ChatGPT's missing Address Book entitlement |

This table records inspected ChatGPT **26.1021.31345**, not all ChatGPT versions.
Native privacy logs established the responsible app for the failing request;
process ancestry alone would not have proved that identity. A worker or signed
bare CLI does not automatically obtain a separate responsible identity.

Apple documents the separate [hardened-runtime resource entitlements](https://developer.apple.com/documentation/security/hardened-runtime),
[Address Book entitlement](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.security.personal-information.addressbook),
[Contacts purpose string](https://developer.apple.com/documentation/bundleresources/information-property-list/nscontactsusagedescription)
and [Apple Events entitlement](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.security.automation.apple-events).
An entitlement permits an app to participate in the relevant authorization flow;
it is not the user's grant. The MCP's native/host review setting supplies neither.

## What other MCPs do

| Inspected implementation | Concrete approach | What to reuse or avoid |
| --- | --- | --- |
| [supermemoryai/apple-mcp](https://github.com/supermemoryai/apple-mcp/blob/08e2c5315683c00fc9567dfefd70a477caccc60d/utils/contacts.ts) | AppleScript to Contacts.app | Established public Automation route. Its readiness probe only gets app name; name-keyed output and per-record skipping do not meet our identity/error contract |
| [boutquin/apple-bridge](https://github.com/boutquin/apple-bridge/blob/951c11af2b621fc34debd2d57432b9ea856c7198/Sources/Adapters/ContactsAdapter/AppleScriptContactsAdapter.swift) | Default MCP Contacts adapter uses AppleScript; library also has CNContactStore | Explicitly chosen to avoid CLI Contacts authorization trouble. Its [signing notes](https://github.com/boutquin/apple-bridge/blob/951c11af2b621fc34debd2d57432b9ea856c7198/docs/code-signing.md) distinguish signing from parent-host permissions. We must retain JSON boundaries, exclude notes and preserve error categories |
| [griches/apple-mcp](https://github.com/griches/apple-mcp/blob/461524625402548f7729db9f7a3758264b7644be/contacts/src/applescript.ts) | Contacts via AppleScript; Calendar via EventKit | Shows the mixed public-API strategy is established. Delimiter parsing, name selection and absent subprocess deadline should not be copied |
| [krmj22/macos-mcp](https://github.com/krmj22/macos-mcp/blob/ab3922ae08f28699c9685d1bd6df3ff776b8d9db/DECISION.md) | Targeted JXA `whose()` search; private SQLite store for bulk enrichment | Records the same 15-second bulk-iteration problem at 600+ contacts. Unix ownership/mode bits alone do not establish TCC access; negative caching must not disguise denial as an empty address book |
| [gheydon/apple-mcp](https://github.com/gheydon/apple-mcp/blob/04a05f12bc017c1845d5fa8efba40b20563134f1/Sources/AppleMCP/Contacts/ContactsService.swift) | Swift CNContactStore with explicit access request; signed distribution | Same native framework gate as ours. Its [release signing](https://github.com/gheydon/apple-mcp/blob/04a05f12bc017c1845d5fa8efba40b20563134f1/scripts/release.sh) is not evidence of success under our affected host |

No reviewed source establishes that a subprocess can simply request its way past
a hardened responsible host's missing Contacts entitlement. Several instead use
Contacts.app's scripting interface. That is programmatic native automation, not
screen scraping or a provider API connection. The subsequent direct-host test
showed that it does not bypass the original caller's Contacts data authorization.
Those implementations remain useful references, not evidence that a different
permission boundary applies under this host.

## Read-only experiments on this Mac

Own fixed scripts ran through the project's bounded subprocess runner, with
15-second deadlines. They did not activate the UI, request notes or write native
records. This launch context already has working native Contacts access, so these
measurements **do not prove** the affected embedded ChatGPT connection works.
Individual elapsed measurements include script process startup, not percentile
benchmarks:

| Probe | Result | Elapsed |
| --- | --- | --- |
| Contacts.app people count | 619 | 0.334 s |
| Bulk persistent record IDs | 619 | 0.677 s |
| Targeted name lookup with deliberately absent token | 0 matches, successful execution | 0.885 s |
| Bulk display names | 619 entries | 0.656 s |
| Bulk email values | 619 per-record arrays | 1.040 s |
| Bulk phone values | 619 per-record arrays | 1.484 s |
| One bounded record, names/organization/job/emails/phones/postal addresses | Retrieved without notes | 4.067 s |

The first postal-address projection failed with native -10002. Fetching each
selected address's public properties fixed that probe. The failure was recorded
as a failure, not an empty address list. The per-record latency also means we
cannot promise fast full-detail pages just from fast bulk IDs.

CNContactStore in the same launch returned **617 unified contacts** and **619
non-unified contacts**. Contacts.app's matching non-unified count is useful
evidence of different record semantics, not proof of exact cross-route identity
mapping. The implemented backend namespaces its IDs and describes record coverage;
those IDs are not interchangeable with existing unified-contact IDs.

## Implementation and actual host results

Version 0.3.3 implements an explicit `--contacts-backend contacts-app` selection,
keeping one Contacts tool surface. It uses public Foundation Apple Events to
batch the fixed fields, with no second index, no native-store writes and no code
constructed from user data. Every read sets `kAEDoNotPromptForUserConsent` and
`kAENeverInteract`, in addition to nonprompting preflight. Setup alone may open
Contacts.app in the background and request its Automation grant.

An initial ScriptingBridge nested-KVC probe exceeded its 25-second deadline.
Direct public core/getd column probes returned 619 IDs in 0.129 s and nested email
lists in 0.081 s. Those are individual field timings, not full MCP timings.
Full local SDK checks subsequently verified list/pagination/get/name/email/phone
and negative searches. Full reads initially took 13–15 seconds; later queries
were 2–5 seconds. Later concurrent actual desktop reads through the managed
launcher took about 35–36 seconds, so the faster examples are not a general latency
promise. See STATUS.md for actual scopes and bounds. No competitor's published
performance was treated as a local result.

The direct ChatGPT connection subsequently granted Automation, then failed both
Contacts list and search. Native privacy logs identified Contacts.app as the
requesting process, the MCP worker as the accessing process and ChatGPT as the
responsible original caller. Address Book access was refused because ChatGPT
lacked the entitlement, with prompting disallowed. Automation consent permits
event delivery; it does not establish the target's permission to disclose data.

The managed launcher in this desktop conversation did pass real list/get/negative
search calls. These outcomes are consistent: macOS authorization is specific to
the responsible launch context. Process ancestry by itself does not prove the
TCC identity for a successful request.

The owner chose to retain Contacts for compatible hosts and possible future
ChatGPT builds with the required declarations. No helper, private-store adapter,
re-signing or new workaround is planned. On a hardened-runtime host, proper
Contacts declarations and a user grant remain necessary; Settings cannot add a
missing signed entitlement. A future host update should be checked with doctor,
explicit setup if needed, and an actual bounded read before claiming support.
