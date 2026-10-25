# 0018: Retain Contacts with explicit host compatibility

Status: accepted, 25 October 2026.

## Evidence

The direct ChatGPT Desktop 26.1021.31345 connection granted Contacts.app Automation
but failed list/search. Native privacy logs identified ChatGPT as the responsible
caller, the MCP worker as accessing, and Contacts.app as requesting access. macOS
refused Address Book access because the responsible app lacked
`com.apple.security.personal-information.addressbook`. The signed app also lacks
`NSContactsUsageDescription`. Calendar has its own declarations and grant.

The separately launched managed Codex connection successfully listed Contacts,
read an exact returned ID and completed a negative search. These are distinct
launch contexts; a parent executable path alone does not prove TCC attribution.
Automation permits event delivery, not necessarily access to the target's data.
Decision 0017's expectation that Automation might fix the affected host was not
borne out by the direct-host test.

## Decision

The owner chose to keep Contacts for compatible hosts and future compatible app
updates. Keep the three read tools and both explicit startup backends. A hardened
responsible host needs the Address Book entitlement, a valid Contacts usage
description and a macOS grant. Settings cannot add a missing signed declaration.
An app update may permit setup later, but its actual connection still needs a
grant and read verification. No helper, re-signing, screen automation, provider
connection or private-store workaround is added.

Expose this limitation in each Contacts tool description, permission setup,
native errors and installation guidance. Preserve native error codes without
including personal payloads. Doctor separately inspects Contacts framework status
without prompting when Automation is selected, and does not call data access
ready on an Automation grant alone. Status inspection does not block a read or
silently switch backends. Generic denial does not diagnose missing declarations
or prove that the user refused a prompt.

Keep the existing worker permission schema compatible with running parents;
the extra nonprompting framework inspection is an internal operation, not a new
public tool. Reload is needed for new descriptions and doctor logic. Preserve
the owner-selected review policy and all existing Mail/Calendar safety behavior.

## Verification

Synthetic coverage distinguishes Automation granted/framework denied, unknown
and limited states; request callbacks, read failure codes and nonprompting flags
remain tested. Real SDK discovery checks both backends and protocol modes without
accessing personal data. Actual per-host results and current checks are in
STATUS.md; do not generalize one launcher to all ChatGPT installations.
