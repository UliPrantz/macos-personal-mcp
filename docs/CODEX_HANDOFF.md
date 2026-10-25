# Maintainer handoff

Start with AGENTS.md, README.md, INSTALL.md, PROJECT_SPEC.md and STATUS.md.
Detailed search, approval and development instructions are in TECHNICAL_DETAILS.md.
The public repository starts with one clean initial commit. Pre-release history
and raw native-data evidence are not part of the public repository.

## Current implementation

- Python 3.15.1, official MCP SDK 2.0.0, PyObjC 12.2.2, uv.lock, strict Pyright,
  Ruff and functional CI. `scripts/install.sh --dev` prepares a local dev runtime.
- One client-owned STDIO process. Native Mail scripting; public EventKit and
  Contacts APIs in bounded workers. No provider API/OAuth/cloud fallback or
  autonomous daemon/indexing. Calendar attendee creation is intentionally excluded.
- Canonical `mail_search` combines selected subject/sender/body fields with native
  MIME/index retrieval, evidence/excerpts, bounded fuzzy spelling and honest
  coverage. Read decisions 0012/0013. Legacy FTS is hidden unless explicitly
  enabled as `mail_search_legacy`; never silently mix the semantics.
- Search identities work directly in message/source reads. One well-formed RFC
  angle-bracket wrapper is equivalent to Mail's public unwrapped identity;
  changed IDs fail before reading content. See decision 0014.
- New installations disable source writes (16 read tools plus permission setup,
  17 total); explicit native write executors expose 20 tools. Native review is the default. Owner-controlled startup policy
  may delegate consent to the host/model; validation and outcome guards remain.
- AGPL-3.0-only, with third-party licenses/notices preserved. See LICENSE, NOTICE,
  THIRD_PARTY.md and decision 0015. Commercial contact requests are voluntary.
- Doctor gives per-domain `next_actions` and observed host context. Only explicit
  `request_permissions` can request one Calendar/Contacts grant; ordinary reads
  and doctor never prompt. Not-determined differs from denied/restricted. Read
  PERMISSIONS.md and decision 0016 before changing that boundary.
- Mail's observed single appended ASCII space passes review. Other body changes
  remain blocked. Draft rejection has a persistent safe failure code and never
  permits an automatic retry; preserve old uncertain operations and existing drafts.

## Verification

```sh
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/pyright --pythonpath .venv/bin/python
.venv/bin/pytest
sh -n scripts/install.sh
```

Normal tests use synthetic data and must never call the maintainer's native apps.
Live reads are separately opt-in. General maintenance is not permission for test
emails/events, changing OS privacy settings, or deleting native data. Preserve
other MCPs, local changes, host approval settings and unresolved outcome journals.

Actual desktop search/message/source reads, Calendar/Contacts reads and the
native approval policy have been demonstrated in declared scopes. SDK success
alone does not prove a new desktop installation; follow INSTALL_WITH_AGENT.md.
Native archive coverage is nonexhaustive, the indexed OS format is gated, semantic
search is absent, and some archive searches exceed the two-second target.

The source review in MAIL_MCP_COMPARISON.md records seven peer implementations
and a local metadata experiment. First proposed improvement: apply exact account/
mailbox SQL scope before the catalogue row cap. This is not implemented yet.
Compare equivalent MCP workloads before deciding whether to replace the native
route with an incremental owned index; do not silently enable legacy search.

Commit verified changes with the documented agent identity, keep STATUS accurate,
and preserve a small, typed implementation. Never add private data or credentials
to the public repository. Do not recreate previous test events or resend mail.
