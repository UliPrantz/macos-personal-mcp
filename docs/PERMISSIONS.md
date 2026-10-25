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
| `not_determined` | macOS has no permission decision for this process yet | With your consent, ask ChatGPT to call `request_permissions` for that one domain. Approve the native OS dialog. There may be no Settings entry until this first request. |
| Calendar `write_only` | It can have write-only OS access, but this MCP needs reads to select and verify a calendar | Request full Calendar access with `request_permissions`. If it remains write-only, follow the returned Settings guidance. |
| `denied` | A decision has already refused access | Open the reported Privacy & Security pane and enable access for the responsible app/helper. macOS normally will not repeat the first-request dialog. |
| `restricted` | A system/device restriction prevents authorization | Ask the device administrator to review privacy/device policy. Repeated calls will not remove it. |
| Calendar `full_access` / Contacts `authorized` | The necessary OS grant is present | No permission change is needed. Verify an actual read from this same connection. |
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
Contacts authorization method. It can show an OS consent dialog and waits at
most 90 seconds; it does not fetch app records or create an event/contact. An
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
First use the explicit request tool. If that fails, remains undecided or times out,
resolve any pending OS dialog and inspect the returned host/error information.

Permission prompts also depend on the host's GUI context and privacy usage
metadata. A host may need valid Calendar/Contacts usage descriptions; the MCP
cannot manufacture another application's identity or guarantee its Settings name.
Report the observed host, domain, status and safe error code for diagnosis. Never
claim a grant merely because the request callback completed.

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
[Contacts authorization](https://developer.apple.com/documentation/contacts/accessing-the-contact-store).
