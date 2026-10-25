# Give the MCP access to your Apple apps

Ask ChatGPT: **“Run macos-personal doctor and follow its next_actions for the
features I want to use.”** Doctor checks access without showing permission
dialogs, reading your contacts/events or creating test items.

macOS access belongs to the **app or helper running the MCP**. It may appear as
ChatGPT, Codex or a Python/helper process. It usually will not be listed as
“macos-personal.” `doctor.host` shows the executable and observed parent command
for troubleshooting; it does not prove which identity macOS will display.

## Calendar and Contacts: start with the actual state

| Doctor status | What it means | What happens next |
| --- | --- | --- |
| `not_determined` | macOS has no permission decision for this process yet | On a compatible host and with your consent, call `request_permissions` for that one domain. There may be no Settings entry until this first request. A known missing entitlement needs a host update instead. |
| Calendar `write_only` | It can have write-only OS access, but this MCP needs reads to select and verify a calendar | Request full Calendar access with `request_permissions`. If it remains write-only, follow the returned Settings guidance. |
| `denied` | macOS refused access; this can be a user decision or a host packaging block | Use Settings if the responsible app/helper is listed. If no dialog or entry appeared, diagnose native host entitlements/usage descriptions first. |
| `restricted` | A system/device restriction prevents authorization | Ask the device administrator to review privacy/device policy. Repeated calls will not remove it. |
| Calendar `full_access` / framework Contacts `authorized` | The domain's OS grant is present | No permission change is needed. Verify an actual read from this same connection. |
| Contacts.app `authorized` | Automation consent is present | This permits event delivery, not necessarily Contacts data access. Follow `next_actions` for the underlying host authorization and verify an actual read. |
| Contacts `limited` | Only selected contacts are available | Use that scope, or expand the selection in Contacts privacy settings if you want more. |
| `unknown`, failed request or unchanged `not_determined` | A grant was not established | Check for a pending dialog, then inspect `doctor.host` and the request error. Do not call it denied or assume a Settings entry exists. |

The agent-facing requests are:

```json
{"domain":"calendar"}
```

or:

```json
{"domain":"contacts"}
```

Pass one of these to **`request_permissions`**, from the same ChatGPT desktop MCP
connection you will use afterward. It calls the public EventKit full-access or
Contacts authorization method by default. The optional Contacts.app backend
requests explicit Automation consent instead; that grant alone does not establish
access to Contacts data. The tool can show an OS consent dialog and waits at most
90 seconds; it does not fetch app records or create an event/contact. An
existing adequate grant is a no-op. Denied/restricted requests do not attempt to
bypass the existing decision. Check `before`, `after`, `granted`, request completion
and returned `guidance` rather than assuming the call granted access.

Then run `doctor` again and perform a small real read: list calendars, or request
one contact. A request made from a separate Terminal process may have a different
permission identity and does not prove access from ChatGPT.

## If you need Settings

- **Calendar:** System Settings → Privacy & Security → Calendars. Choose full
  access for the responsible app/helper. Write-only is insufficient for the MCP's
  calendar reads and selected-calendar validation.
- **Contacts:** System Settings → Privacy & Security → Contacts. Choose the scope
  you want to expose. This MCP offers contact **reads only**, even if the OS grant
  permits more.
- **Mail Automation:** a Mail account-discovery call can cause macOS to ask whether
  the launching app/helper may control Mail. If previously denied, use Privacy &
  Security → Automation and enable Mail under that responsible app.
- **Mail files:** on an observed Mail-storage denial, use Privacy & Security → Full
  Disk Access for the actual reader. The permission tool cannot grant this access.
  A missing local Mail directory instead needs native account setup/synchronization.

Restart the MCP connection after a grant. Restart the named app/helper only if
macOS asks. Recheck through the actual desktop tools. Granting access to one host
or adding an arbitrary Python binary may not affect another host's permission.

## If there is no dialog or entry

`not_determined` is not an instruction to find a toggle that does not exist yet.
On a compatible host, first use the explicit request tool. If it fails, remains
undecided or times out, resolve any pending OS dialog and inspect the returned
host/error information. Do not repeat requests for a confirmed missing entitlement.

Permission prompts also depend on the host's GUI context and privacy usage
metadata. A host may need valid Calendar/Contacts usage descriptions; the MCP
cannot manufacture another application's identity or guarantee its Settings name.
Report the observed host, domain, status and safe error code for diagnosis. Never
claim a grant merely because the request callback completed.

## Contacts refused without a dialog in ChatGPT

Verified on 25 October with ChatGPT desktop **26.1021.31345**: Calendar access was
requested and granted, but Contacts changed from `not_determined` to `denied`
with error 100 and no dialog. The host had no Contacts entry in System Settings.
This was not a user clicking “Don't Allow.”

The macOS privacy log identified ChatGPT as the responsible application and
explicitly reported that its hardened runtime lacked
`com.apple.security.personal-information.addressbook`. Inspection of the installed
app's signing information confirmed the missing Contacts entitlement; its
`NSContactsUsageDescription` was also absent. Its Calendar entitlement and usage
description were present, explaining why Calendar could prompt normally.

**Contacts itself is supported.** A hardened-runtime responsible calling app needs
that entitlement, a Contacts usage description and the user's macOS grant. Other
compatible hosts can use the existing tools. If OpenAI adds the declarations in
a future ChatGPT build, the same tools can request permission and be verified;
there is no separate Contacts integration to install.

For the tested build, changing an MCP approval setting, repeating the request or
looking for a nonexistent toggle cannot supply the missing signed entitlement.
OpenAI would need to update its app. This MCP does not modify ChatGPT's signature
or build a separate helper. A generic error 100 is not proof of missing metadata
on every host: use the observed signing information and native denial evidence.

The optional Automation route was also tested in the affected connection:
Automation was granted, but list/search failed. Native privacy logs showed
Contacts.app requesting Address Book access on behalf of the original ChatGPT
caller, then refusing its missing entitlement. Switching backend therefore does
not fix this host. This differs from the separately authorized managed launcher,
where actual desktop list/get/negative-search calls succeeded. Permission identity
belongs to the launch context; success in one does not certify another.

## Optional Contacts.app Automation route

**`--contacts-backend contacts-app`** deliberately selects Contacts.app's public
scripting interface. It remains available for compatible hosts; it is not an
entitlement workaround. The default is still the direct Contacts framework.
See [installation](../INSTALL.md#contacts-host-compatibility-and-optional-backend)
and the [source comparison](PERMISSION_MCP_COMPARISON.md).

On a compatible host, restart the connection after selecting it, confirm
`doctor.permissions.contacts_backend` is `contacts-app`, and follow its
`next_actions`. Explicit `request_permissions(domain="contacts")` can open
Contacts.app in the background and ask whether the host may control it. There are
no screenshots, clicks, keyboard automation or provider connections. For an
actual Automation refusal, use **Privacy & Security → Automation → responsible
host → Contacts**, if that entry exists. The separate Contacts data gate still
applies. A setup result of `granted=true` means Automation consent was granted,
not that Contacts data has been read successfully.

Doctor keeps Automation status separate from underlying framework authorization.
When Automation is authorized but framework access is not established, it reports
unverified readiness and host diagnosis instead of claiming data access. These
status checks do not prove a missing entitlement by themselves: inspect the host
when needed, and do not assume a user denied a dialog.

Doctor and reads do not launch Contacts.app or prompt. If the app is stopped,
they report `not_running`; explicit setup can open it. Read events additionally
set Apple's no-consent-prompt and never-interact flags, so revocation after
preflight fails instead of opening a dialog. No hidden fallback runs after a
framework denial or limited grant. The owner chooses which route to expose.

Local SDK tests verified lists, disjoint pages, exact reads, name/email/phone
lookups, a negative search and an existing-grant setup no-op. Actual desktop
list/get/negative calls also succeeded through the managed launcher. The direct
ChatGPT host failed after Automation consent, as described above. No read result
from one launcher is substituted for another's verification.

Contacts.app records are not unified across sources: this Mac exposed 619 records
versus 617 unified contacts. IDs use `contacts-app:` and must be searched afresh
after switching backends. Fields are batched in memory and discarded after each
call; there is no additional address-book index or synchronization process.

## New files but an old tool catalog

The MCP server keeps its definitions in memory, while disposable native workers
load code from the checkout. Updating files can therefore produce new permission
error messages while an old server still lacks `request_permissions`.

Restart the existing `macos-personal` entry in ChatGPT's MCP settings. If an
existing conversation retains the old catalog, use a fresh local chat with that
same registration. No new clone or duplicate server is needed. A freshly launched
guarded server exposes 20 tools; read-only startup exposes 17. Confirm
`doctor.server_version` matches the installed package and that `host`,
`next_actions` and the setup tool are available. A missing `server_version` is an
older loaded doctor contract.

## OS permissions and send/create approval are separate

OS permission permits the process to use an Apple service. The MCP's default
native confirmation dialog approves **one exact email or calendar event**.
Approving that payload does not grant missing Calendar/Contacts access. Changing
`permissions.toml` to delegate send/create approval also cannot grant macOS access.

`request_permissions` remains available with source writes disabled so setup can
work before enabling writes. It is annotated as a non-read-only, non-destructive
setup action because it can show an OS dialog. It cannot enable send/create tools,
change approval policy or create app data. Ordinary reads, `doctor` and startup
never request Calendar/Contacts access automatically.

Apple references: [Calendar access request](https://developer.apple.com/documentation/eventkit/ekeventstore/requestfullaccesstoevents%28completion%3A%29),
[Calendar access levels](https://developer.apple.com/documentation/technotes/tn3152-migrating-to-the-latest-calendar-access-levels),
[Contacts authorization](https://developer.apple.com/documentation/contacts/accessing-the-contact-store),
[Address Book entitlement](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.security.personal-information.addressbook).
