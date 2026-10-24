# Activate the tested native tools in the desktop profile

Date: 23 October 2026. Supersedes the earlier read-only desktop registration
choice; the server's read-only default and native approval enforcement remain.

The mandatory-native-only approval policy below is superseded by
[decision 0010](0010-owner-configurable-server-approval.md): the owner can
explicitly delegate server review to the host/model. Native remains the default.

## Decision

Finish daily-use integration by configuring this project's desktop STDIO entry as
`macos-personal`, replacing the legacy `macos-personal-readonly` entry. Launch the
same isolated absolute executable with `serve --enable-mail-send
--enable-calendar-create --enable-calendar-open`. A model tool cannot change
launch mode; this is installation configuration for the originally requested,
already tested native features. No Mail/Calendar data is changed by installation.

Preserve all unrelated configuration and MCP registrations byte for byte. Parse
the old/new TOML and independently compare all non-project settings. Save only
the prior project table privately for reversal. Raise this entry's tool timeout
from 25 to 240 seconds so the three-minute native approval dialog can finish.
Retain `default_tools_approval_mode = "writes"`; the host documents this as
prompting for tools not annotated read-only. Native exact per-action human
confirmation remains independently mandatory for email sends and event creation.
No global shell approval, Python, Git or other MCP settings are relaxed.

Read-only mode remains separately available with `serve --read-only`; no
source/UI write tools are discovered or dispatched in that mode. The guarded
profile exposes exactly the 16 existing read/preparation tools plus native Mail
send, Calendar create and exact nonrecurring event show. Attendee creation and
direct provider APIs remain excluded by decision 0008.

## Verification and activation boundary

A real SDK STDIO client starts the exact configured executable/arguments from
`/tmp`, verifies all 19 tool schemas/annotations and omission of invitations,
checks read_only=false plus native permissions, reads Mail account/Calendar/
Contacts metadata, and verifies model `approved` inputs fail validation. This
configuration probe invokes no live writes or UI commands. Existing live
send/delivery and Calendar creation tests prove the native execution routes;
they are not repeated as a side effect of activation.

At configuration time, the conversation retains its old server/catalog until
the desktop MCP connection reloads. A configured-profile SDK success is not a claim that this
conversation can already discover the new write tools. Save/push first, then
reload the desktop connection; after resuming, inspect the actual catalog and
perform read-only verification. Do not send another email or create another test
event merely to confirm discovery. No new macOS permission or provider login is
required for the tested route.

The owner's subsequent reload completed this boundary: the actual desktop
catalog now exposes all 19 tools, and native policy/read checks passed without
another send or creation. See STATUS.md for measured results and remaining limits.

References: [official MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli),
[configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).
