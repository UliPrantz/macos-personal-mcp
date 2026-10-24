# 0014: Complete the search/read workflow and make installation agent-friendly

Date: 24 October 2026. Owner requested a usability pass, actual reloaded desktop
verification, human installation instructions and a Framer-style install prompt.

## Message identity handoff

Actual desktop `mail_search` returned the known dated message. Passing its exact
selectors to `mail_get_message` initially failed: Envelope Index's RFC identity
includes one outer angle-bracket pair, while public Mail `messageId` omits it.
Account, mailbox and numeric identity were verified equal independently.

The public read bridge now accepts either representation by removing exactly one
well-formed outer pair before comparison. It preserves every character inside;
it does not strip whitespace, case-fold or accept nested/unbalanced brackets.
Mismatches produce the typed `message_identity` error instead of an opaque native
failure suggesting missing access. Existing before/after identity/flag checks
remain. Source-read identity gets the same treatment. The native MIME binding
and native search coverage contract are unchanged.

Synthetic JXA tests replace all application resolver call sites with test objects,
so default tests never contact Mail. Actual desktop search → message/source reads
and a wrong-identity rejection verify the production handoff. The fixed bundled
JXA is read for each call, so this bridge-only repair works on the already
reloaded desktop connection without another Python-process restart.

## Installation surfaces

README starts with one copyable agent-install prompt and a short manual path.
INSTALL.md serves people; docs/INSTALL_WITH_AGENT.md supplies the full agent
runbook, including inspection of existing state, native OS permissions and actual
desktop readback. docs/USAGE.md explains search phrasing, dates, paging and reading
results. This is source installation into the documented local STDIO host route,
not a Directory submission or a remote/provider integration. Official OpenAI
documentation supports shared desktop/Codex local MCP configuration and the
desktop Settings/Add server/STDIO/Restart workflow.

`scripts/install.sh` installs pinned uv 0.13.5, Python 3.15.1 and uv.lock into
the checkout's `.local/` and `.venv/`. If no usable Rust compiler exists, it adds
the tested Rust 1.99.1 build toolchain locally for dependency source builds.
Apple's Command Line Tools are a reported prerequisite. `--dev` keeps development
dependencies; the normal profile installs runtime dependencies only. It writes
a private example TOML table and prints the real absolute executable path.
It never edits host configuration, shell profiles, global runtimes or TCC.

An authorized installation agent handles registration through desktop settings,
the supported CLI or a targeted, backed-up TOML edit, preserving other entries
and owner-selected approval/executor settings. New installs start read-only with
native approval defaults; there is no automatic send/event verification, legacy
index build, broad privacy grant or provider login. The repository was private
at this checkpoint; decision 0015 records the subsequent public release.
Computer use must run on the actual Mac.

Clean runtime verification uses a separate ignored checkout path containing
spaces, then checks repeatability, generated TOML and real SDK discovery from
another working directory. This is a clean environment on this Mac, not proof of
all prerequisites on an untouched Mac; STATUS records exactly what was tested.

Sources: [OpenAI local MCP setup](https://learn.chatgpt.com/docs/extend/mcp),
[Framer install-prompt pattern](https://www.framer.com/agents/external/),
[uv installer](https://docs.astral.sh/uv/reference/installer/),
[uv storage](https://docs.astral.sh/uv/reference/storage/),
[Rust local installation](https://rust-lang.github.io/rustup/installation/).
