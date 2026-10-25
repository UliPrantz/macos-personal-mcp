# Local MCP permissions: existing approaches and measured probes

Reviewed 25 October 2026. This investigation preceded the optional backend in
[decision 0017](decisions/0017-selectable-contacts-app-automation.md).
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
| Contacts.app via Apple Events | Apple Events declarations and Automation consent to control Contacts.app | Host has Apple Events entitlement/purpose string; this target's grant still needs testing in the affected connection |

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
screen scraping or a provider API connection.

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
mapping. A future backend must namespace its IDs and describe record coverage;
it cannot treat those IDs as interchangeable with existing unified-contact IDs.

## Implementation and remaining host check

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
were 2–5 seconds. See STATUS.md for actual bounds and the remaining direct-host
verification. No competitor's published performance was treated as a local result.

The other ChatGPT agent reported another direct-API permission error, not the
requested Contacts.app probe; it did not validate this route. After reloading the
configured server, confirm `doctor.server_version` and
`permissions.contacts_backend`, call explicit `request_permissions` for contacts
if its guidance requires it, approve the actual Automation dialog, then perform
list/get/name/email/phone checks from that same connection. No Terminal test or
separately authorized launcher substitutes for this check.

A helper is unnecessary if this established Automation route works under the
actual host. If it fails, preserve the native error and investigate host Apple
Events declarations/responsibility first. Private AddressBook SQLite adds schema,
linkage, limited-access and synchronization work; FDA is not sufficient reason
to introduce it as an automatic fallback. No helper or private-store adapter was
added.
