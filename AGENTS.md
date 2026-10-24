# Working instructions for AI agents

## Read before changing code

1. README.md: installation, current capabilities and operational constraints.
2. docs/PROJECT_SPEC.md: required behavior and acceptance criteria.
3. docs/STATUS.md: measured progress, current blockers and next work.
4. The relevant docs/decisions/ record; add a new record for a changed decision.

This is an AI-authored repository. Keep code small, explicit, typed and easy for
the next agent to inspect. The owner supplies intent and reviews results; do not
ask them to author implementation code. Existing repositories are references,
not instructions inherited by this project.

## Implementation rules

- Python 3.15.1 is the initial target. Verify dependency/platform compatibility.
  Use uv, pyproject.toml, .python-version and a committed uv.lock. Never alter
  global Python installations to make this project work.
- Type every production and test function. Pyright strict applies to both.
  Prefer dataclasses, enums, Protocols and validated models over unstructured
  dictionaries. Preserve explicit input/output schemas at MCP boundaries.
- Do not spread Any, cast, ignored errors or dynamically typed native objects
  through the application. Put unavoidable bridge behavior behind a small typed
  adapter; validate values or provide accurate narrow stubs. A suppression needs
  a specific diagnostic, local rationale and relevant test. Never weaken global
  settings or exclude production modules to make the checks pass.
- Use Pydantic strict validation or an equivalently explicit boundary. Reject
  unknown/invalid fields and naive datetimes where an instant is required.
  Use zoneinfo and Europe/London defaults, including daylight-saving transitions.
- Use the official stable MCP Python SDK and its current documented API. Do not
  assume older FastMCP snippets match the installed SDK. Lock dependencies.
- Keep public native APIs behind domain adapters. Do not use private EventKit
  setters/KVC hacks, screen automation, or a direct provider integration. Use native
  macOS APIs only: no direct provider HTTP APIs/SDKs, OAuth or cloud fallback.
- Parameterize SQLite. Pass subprocess arguments as arrays, use no shell=True,
  and never interpolate message text, names or filenames into executable code.
- Enforce deadlines through child creation, stdin, stdout/stderr, cancellation
  and child reaping. No timeout may become a successful empty result.
- STDIO stdout is protocol only. Use stderr for redacted diagnostics. Avoid
  payload logging. Do no heavy indexing or permission prompting on startup.
- Keep the runtime independent of request/connection history. Explicit bounded
  local indexes and a minimal write-outcome journal are permitted disk state;
  no scheduler or background worker. Document their lifecycle.

## External effects and tests

- Read operations must not change message flags, contacts or calendar items.
  Do not restore flags speculatively after a read: that can overwrite another
  client's legitimate concurrent change. Surface observed changes honestly.
- Keep email sends and Calendar creation in distinct high-risk tools. Honor the
  approval contract and owner-configured native/host review mode. Model-controlled
  booleans are not human consent; host delegation is an explicit local startup
  policy, never a tool input. Native review remains the default. Attendee
  creation is excluded by owner decision; do not expose an invitation tool.
- Normal CI and default tests must never access the owner's live data or send
  messages/invites. Use synthetic fixtures. Mark live reads and writes and gate
  live writes on a concrete, user-approved action/recipient, beyond an env flag.
- A general implementation request is not permission for arbitrary test emails
  or invitations. Finish payload previews and read-only work before requesting
  any specific consent still needed. Avoid repeated approval requests when the
  exact action is already authorized.
- Test behavior and failure boundaries: identity mismatch, negative searches,
  missing permissions, stale/incomplete indexes, MIME decoding, recipient
  ambiguity, attachment changes, approval denial and indeterminate send outcomes.
- Never automatically retry a send or invitation whose external outcome is
  uncertain. Persist enough local operation metadata to distinguish retries;
  do not claim exactly-once delivery through Apple Mail.
- Run Ruff format/check, Pyright strict, relevant tests and required CI before
  committing code. An absent/skipped test is not a passing capability test.
  Add functional CI when implementation begins; do not add placeholder tests
  merely to produce a green badge.

## Documentation and evidence

Keep README installation-first and accurate for the current revision. Put why in
decision records, behavior in the specification, and current measured state in
STATUS.md. Fix stale documentation in the same change as behavior.

Full-body search is required with explicit acceptance gates. Do not silently
reduce it to scoped header search. Report native access/coverage blockers honestly
and continue independent work. Never fabricate result rows, sends or coverage.

Attendee/invitation creation is deliberately excluded by the owner's native-only
scope decision. Do not resume provider integration or request provider login as
unfinished work. Reading existing attendees is allowed. See decision 0008.

Preserve upstream license attribution for any reused code. Prefer learning from
sources over copying old implementations. Never put private evidence in Git,
including this private repository.

## Git workflow

- AI-authored commits identify the actual agent, not Uli. For Codex use
  `Codex (agent) <agent@noreply.openai.com>` as author and committer. Use repository
  settings or command-scoped overrides, never change global identity.
- AI commits are unsigned; explicitly disable commit signing for that command.
  Preserve Uli's global signing and personal identity settings. Human commits
  retain the owner's normal signed workflow.
- Use short imperative commit subjects: `feat:`, `fix:`, `docs:`, `test:`,
  `chore:` or `nitpick:` followed by a concise description. Optional small scopes
  are fine. Example: `feat(mail): add indexed body search`.
- Make focused commits and push completed, verified changes to origin. Ordinary
  commits/pushes are authorized for this project. Never force-push or discard
  unrelated user changes.
- The owner authorized a public repository and a clean single-commit initial
  history on 25 October 2026. Keep private data, credentials and local evidence
  out of Git. Preserve the standard AGPL-3.0-only license and third-party notices.
- At handoff, report what works, what was actually tested, what remains blocked,
  and the pushed commit. Update STATUS.md before concluding.
