# 0017: Explicit Contacts.app Automation backend

Status: accepted, 25 October 2026.

## Context

The direct ChatGPT host can grant Calendar access but lacks the hardened-runtime
Address Book entitlement and Contacts purpose string. The native privacy log
confirms refusal before any Contacts dialog. Repeating requests or granting Mail
file access does not repair that declaration. See decision 0016.

The owner requested review of existing MCPs before building a helper, and accepted
native programmatic automation while rejecting screen-driven computer use.
PERMISSION_MCP_COMPARISON.md records five pinned sources. Several already use
Contacts.app through Apple Events. Local probes confirmed batched reads are
practical; per-record scripting and ScriptingBridge nested KVC were much slower.

## Decision

Add an owner-selected `--contacts-backend contacts-app` startup flag. Keep
`framework` as the default, retain the same three Contacts tools and never choose
a route based on a failed/denied request. There is no provider connection,
screen automation, private database access, app re-signing or new helper.

Use public `NSAppleEventDescriptor` core/getd requests with the property/element
codes from Contacts.app's public scripting dictionary. These are equivalent to
scripted property reads, not a reverse-engineered private protocol. User data is
never executable code. Fetch fixed columns in batches; exclude notes, vCards and
photos. Decode only expected text/list/missing-value shapes, check column and
nested lengths and bracket enumeration with ordered-ID checks. Changed identities,
native errors, output bounds and deadlines are failures, never empty success.

Every read event sets Apple's `kAEDoNotPromptForUserConsent` and `kAENeverInteract`
flags, including after authorization preflight. This matters when a grant is
revoked between preflight and dispatch. Doctor and reads use public
`AEDeterminePermissionToAutomateTarget(..., false)` only. They do not launch the
target. A stopped Contacts.app reports `not_running` rather than denied access.

Only explicit `request_permissions(domain="contacts")` may open Contacts.app in
the background and request Automation consent. The potentially blocking request
runs off the main thread; the existing worker timeout/cancellation/reaping boundary
still applies. Already granted or denied authorization does not re-prompt. Doctor,
tool descriptions and request results identify the selected route and direct the
person to **Automation**, not Contacts privacy settings. Calendar still uses
EventKit and its separate Calendar grant.

Contacts.app exposes records that are not unified across sources. IDs use the
`contacts-app:` namespace and must be searched afresh after switching backends.
Preserve same-name candidates and labeled fields, sort deterministically and
describe coverage as the app's current exposed records, not every synchronized
provider record. Backend selection is a local startup decision, not a tool input
that a model can use to broaden an existing grant.

## Verification boundary

Normal tests use synthetic columns, descriptors and request backends, including
permission revocation, identity/order changes, missing fields and empty controls.
Live SDK checks are separate and record counts/timings in STATUS.md. A successful
test from the maintainer's authorized launcher does not certify the direct
ChatGPT host: that connection must reload, report the selected route, explicitly
request Automation if needed and then perform actual reads.
