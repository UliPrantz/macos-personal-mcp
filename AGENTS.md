# Repository instructions for AI agents

Read README.md, docs/PROJECT_SPEC.md, docs/STATUS.md and the relevant design
decisions before changing behavior. Installation and development commands are in
INSTALL.md and docs/TECHNICAL_DETAILS.md.

## Implementation

- Use the pinned Python target, uv and uv.lock; do not alter global runtimes.
- Keep production and tests explicitly typed. Strict Pyright and Ruff apply;
  isolate native bridge behavior behind small typed adapters and narrow stubs.
  Do not weaken checks or spread Any, casts or ignored diagnostics.
- Validate strict MCP input/output schemas. Reject unknown fields, coercions and
  naive instants; preserve Europe/London defaults and daylight-saving behavior.
- Use the official MCP Python SDK and native macOS integration. No direct provider
  HTTP/SDK/OAuth fallback, private API setters, screen automation or new helper.
- Parameterize SQLite, open native stores read-only and preserve their schema,
  flags and WAL behavior. Never use immutable mode for a live changing database.
- Pass subprocess argument arrays without shell=True or interpolated executable
  scripts. Bound startup, I/O and work; cancel, kill and reap children on failure.
  Timeouts and incomplete reads must never become successful empty results.
- STDIO stdout is protocol only. Redact stderr diagnostics and avoid payload logs.
  No heavy startup indexing, background scheduler or unsolicited permission prompt.
- Preserve native message/contact/event identities and duplicate-name candidates.
  Reads must not mutate source data or speculatively restore message flags.
- Keep one canonical mail_search. Legacy FTS requires explicit startup opt-in,
  exact-scope maintenance and freshness checks; never substitute its semantics.
  Report missing/partial bodies and coverage limits honestly.

## Access and external effects

- Doctor and ordinary Calendar/Contacts reads never request grants. Only explicit,
  user-requested request_permissions setup may request one selected domain.
  Not-determined, denied, restricted, limited and Calendar write-only differ.
- Missing host entitlements can prevent a dialog or Settings entry. Denial does
  not prove user refusal. Contacts.app Automation is an explicit backend, never
  a fallback; reads retain no-prompt flags. Automation consent alone does not
  establish Contacts data access. Keep the tested ChatGPT host limit visible and
  preserve support for compatible hosts. Do not repeat setup or build workarounds
  for a known missing entitlement without a new user request.
- OS grants, enabled executors and action approval are separate. Native review is
  the default; respect explicit owner-controlled host delegation. Tool-controlled
  booleans and previews are not consent. Validation and outcome guards always apply.
- Mail sends and Calendar creation need distinct guarded tools. General maintenance
  is not permission for test messages/events. Stage exact payloads before requesting
  any specific approval still needed; do not request already supplied approval again.
- Never automatically retry uncertain sends or delete their drafts. Preserve the
  outcome journal and unresolved attachment snapshots across upgrades/cleanup.
- Calendar invitations/attendee creation and Contacts mutations are outside scope.
  Existing attendees may be read. Do not add provider or ICS substitutes.

## Verification and documentation

- Normal tests/CI use synthetic fixtures and never access live personal data or
  send messages/events. Live reads are opt-in; live writes additionally require
  concrete user-approved recipients/payloads. A skipped test is not a passed gate.
- For code changes run Ruff format/check, strict Pyright, relevant functional
  tests and required build checks. For documentation changes check local links,
  stale references and git diff --check. Verify the pushed CI result.
- Distinguish SDK checks from actual desktop verification. Permissions, accounts,
  configuration and performance depend on the launching host and measured scope.
- Keep README installation-first, the contract in PROJECT_SPEC.md, current results
  and limits in STATUS.md, and durable rationale in docs/decisions/. Update affected
  docs with behavior changes; avoid temporary handoffs or implementation diaries.
- Keep private evidence, credentials and native exports out of Git. Preserve
  AGPL-3.0-only and third-party attribution; never copy unreviewed research code.

## Git

- Commit and push completed, verified changes without force-pushing or discarding
  unrelated work. Inspect an existing checkout before editing it.
- Use Codex (agent) <agent@noreply.openai.com> as AI author and committer. Disable
  signing for that commit; preserve the owner's global identity/signing settings.
- Use short imperative conventional subjects such as feat:, fix:, docs: or chore:.
- Finish with the verification result, material limits and pushed commit.
