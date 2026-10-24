# Verification sources and privacy boundary

Public verification summaries are in STATUS.md. They distinguish synthetic tests,
SDK protocol checks and actual desktop/native reads. No raw mail, addresses,
contacts, calendars, account IDs or private diagnostics are included here.
Pre-release workspaces and raw evidence are retained outside public Git history.

## Native interfaces

- Mail scripting dictionary: `/System/Applications/Mail.app/Contents/Resources/Mail.sdef`.
- Calendar scripting dictionary: `/System/Applications/Calendar.app/Contents/Resources/iCal.sdef`.
- [EventKit reads](https://developer.apple.com/documentation/eventkit/retrieving-events-and-reminders)
  and [event creation](https://developer.apple.com/documentation/eventkit/creating-events-and-reminders).
- [Contacts](https://developer.apple.com/documentation/contacts).
- [EventKit participants](https://developer.apple.com/documentation/eventkit/ekparticipant):
  participant creation is unavailable through the public API used here.
- On-disk Mail/Spotlight formats: NATIVE_MAIL_INDEX_FORMAT.md and decisions 0012/0013.
  Reads are guarded and read-only; unsupported profiles fail explicitly.

## Protocol and implementation references

- [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
  and [SDK documentation](https://py.sdk.modelcontextprotocol.io/).
- [MCP STDIO](https://modelcontextprotocol.io/specification/latest/basic/transports/stdio)
  and [tools](https://modelcontextprotocol.io/specification/latest/server/tools).
  Tool annotations are hints, not approval enforcement.
- [Desktop MCP setup](https://learn.chatgpt.com/docs/extend/mcp).
- [Python 3.15.1](https://www.python.org/downloads/release/python-3151/).
- Source/format attribution and dependency notices: ../THIRD_PARTY.md.

Feature inspiration included supermemoryai/apple-mcp. This is an independently
implemented Python project; advertised upstream functionality is not evidence
that a native capability works. No placeholder success rows, scheduled sending,
provider fallback or invitation workaround is exposed.

Use synthetic fixtures for normal tests. Native investigation outputs, source
messages, personal selectors, send previews and permission diagnostics belong
outside Git. Report measured scope, gaps and observed flags without publishing
private content. Never infer archive completeness from one successful targeted read.
