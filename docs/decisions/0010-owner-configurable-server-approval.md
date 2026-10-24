# Owner-configurable server review, including host/model delegation

Date: 23 October 2026. Explicit owner request. Supersedes the earlier requirement
that native per-action confirmation must be the only executable configuration.
Native-only integration and exclusion of attendee creation remain unchanged.

## Policy

Load a strict local TOML snapshot at startup from
`~/Library/Application Support/macos-personal-mcp/permissions.toml`, or an absolute
`--config` path. No MCP tool or payload field can change this policy. An owner
file edit takes effect after restarting the connection. Missing default config
uses `native`; a missing explicit file, invalid TOML/schema/mode, unknown tool
override, symlink, nonregular/unowned or group/world-writable file fails startup.
Read at most 64 KiB. Do not log file contents. Tests use isolated synthetic files.

`[approval] default = "native"` retains exact independent human dialogs for email
send and event creation. `default = "host"` removes all server confirmation
dialogs and delegates consent decisions to the host/model. The host reviewer
does not attest that a human approved the action. This is an intentional owner
configuration, not an `approved=true` field or a model-generated consent token.

Optional `mail`, `calendar` and `contacts` values set domain defaults;
`[approval.tools]` sets exact tool overrides. Precedence: tool > domain > default.
Modes are only `native` and `host`. Read tools, Contacts and event opening already
have no server review dialog; host annotations/policy govern those calls in
either mode. Contacts remains read-only. Approval settings do not invent tools
or add mutation capabilities to reads.

The existing default read-only gate and explicit executor launch flags remain
independent. Neither a policy file nor a tool input can override an explicit
read-only launch. Changing approval mode also does not bypass macOS privacy
grants, host/managed restrictions, strict schemas, sender/calendar identity,
attachment snapshots/revalidation, or durable no-blind-retry outcome handling.
Native write annotations remain conservative in both modes.

## Transparency and verification

`macos-personal-mcp policy` reports the loaded path, effective per-tool mode,
discovery/executor availability and whether a server dialog would be used.
`doctor` and tool descriptions also disclose the effective review policy. Fresh
write outcomes include `approval_mode`; journal replays return null because the
minimal journal does not record the original mode. A policy change cannot turn a
recorded operation into a fresh send/create, and no exactly-once delivery promise
is introduced. No recipients, content or policy file is added to the journal.

Synthetic tests demonstrate delegated Mail/Calendar dispatch without an AppKit
child, native denial causing zero dispatch, domain/tool precedence, startup
snapshot behavior, invalid/unsafe config failures, read-only/disabled-executor
precedence, rejected model approval inputs and retry protection across mode
changes. No live send/create is authorized by implementing or testing this mode.

The installed owner file starts in native mode. A two-line host-delegated example
is provided for deliberate opt-in. The existing host setting `writes` is retained;
it can still prompt independently. Host auto-approval is a separate host choice,
not something this MCP may silently enable. Permission files are not a security
boundary against an agent separately granted unrestricted filesystem access.

References: [MCP host tool policy](https://learn.chatgpt.com/docs/extend/mcp),
[MCP tool security considerations](https://modelcontextprotocol.io/specification/2025-11-25/server/tools#security-considerations).
