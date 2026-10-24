# Native macOS integration; no attendee creation or provider backends

Date: 23 October 2026. Owner decision; supersedes the invitation investigation and
provider fallback options in the original requirements and decisions.

The owner explicitly chose to omit attendee creation to keep this project native
to macOS. Implement Mail through public Apple Events and Calendar/Contacts through
public EventKit/Contacts APIs. Do not add direct Google, Microsoft, CalDAV/HTTP or
other provider API clients, provider SDKs, OAuth flows, copied application tokens
or cloud fallback. No provider login is required by this MCP.

The native applications may fetch, send and synchronize through the accounts the
owner already configured. That is their normal behavior; this MCP does not add
an independent provider connection. Native Mail sending and Calendar creation
retain exact independent human approval. Desktop read-only mode remains a
separate configuration choice and is not changed by this scope decision.

Remove the unimplemented `calendar_create_invitation` tool and input model rather
than advertise a feature intentionally outside scope. Direct calls to the old
name fail as an unknown tool, including in write mode. Event creation continues
to reject invitee/attendee inputs. Reading attendees already present on native
events remains supported and sends nothing. Do not substitute an ICS email,
private EventKit setter or screen automation.

This closes the invitation investigation as an explicit product exclusion, not a
missing macOS permission or unfinished provider authentication task. Future
agents must not resume provider integration without a new explicit owner scope
change. Existing unrelated connectors/configuration are untouched.

Synthetic checks cover absence and rejection of the old invitation tool in both
launch modes, with no native dispatch. Existing event input and approval tests
continue to enforce no invitees and exact per-action confirmation.
