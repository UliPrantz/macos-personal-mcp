# Install this MCP for a person

You are installing macOS Personal MCP on the user's Mac for ChatGPT desktop.
Carry out the installation and verification yourself. The user's install prompt
authorizes downloading the project's pinned runtime/dependencies and registering
this local server. New installs are read-only; preserve existing owner-selected
write flags and approval settings. Ask only for a blocking human action such as
an OS permission dialog or a restart that interrupts your session.

## 1. Establish the local target

- Work on the actual Mac, using Terminal tools or computer use with local shell
  access. A cloud container or browser-only session cannot install this native
  MCP. If unavailable, report that exact missing capability and link INSTALL.md.
- Check Apple Silicon macOS, ChatGPT desktop/local STDIO support and Git. The
  validated large Mail-index profile is macOS 26.5.2. Other versions must report
  the archive-search limitation; do not bypass its format gate.
- Prefer `~/Developer/Projects/macos-personal-mcp`. Inspect an existing directory,
  Git status and remote before changing anything. Reuse the actual checkout if
  already installed elsewhere; do not create a second competing registration.
  Clone `https://github.com/UliPrantz/macos-personal-mcp.git` only if absent.
  The repository is public; HTTPS cloning requires no GitHub sign-in. Preserve
  existing Git authentication and never request tokens in chat.
- Read AGENTS.md, INSTALL.md and current docs/STATUS.md. Preserve unrelated edits.
  Never reset, clean, force-push, publish the repository or change its visibility.

## 2. Install the isolated runtime

From the checkout run:

```sh
sh scripts/install.sh
```

Use `--dev` for an existing development environment. The script uses pinned uv
0.13.5, Python 3.15.1 and uv.lock. It installs beneath `.local/` and `.venv/`,
without changing global Python or shell profiles. It produces an absolute
executable and `.local/chatgpt-mcp.toml`. Do not copy this project to a temporary
directory for the real install: its runtime must remain at the registered path.
Build failures may require Apple's Command Line Tools; explain that concrete
system installer if needed, then resume. The script supplies project-local Rust
1.99.1 when missing, because some locked Python 3.15 dependencies need source
builds. Do not substitute an untested Python runtime.

## 3. Register exactly one server

Use ChatGPT **Settings → MCP servers → Add server → STDIO**, the supported Codex
MCP CLI, or a targeted edit to the local host configuration. The desktop, Codex
CLI and IDE share local MCP configuration for the same host:
[official setup documentation](https://learn.chatgpt.com/docs/extend/mcp).

For a new server, the generated table is the source of exact settings:

```toml
[mcp_servers.macos-personal]
enabled = true
command = "/absolute/checkout/.venv/bin/macos-personal-mcp"
args = ["serve", "--read-only"]
startup_timeout_sec = 10
tool_timeout_sec = 240
default_tools_approval_mode = "writes"
```

Use the real printed path. In a UI that takes an argument array, enter `serve`
and `--read-only` separately. Never put a remote URL in place of the command.

With an installed `codex` CLI, a new entry can be added using:

```sh
codex mcp add macos-personal -- /absolute/checkout/.venv/bin/macos-personal-mcp serve --read-only
```

Then set its `tool_timeout_sec` to 240 and the other settings above in the host's
actual config. The usual location is `~/.codex/config.toml`; respect a configured
Codex home. Check for an existing server before running `add`. Do not overwrite
its executor/approval settings or create a duplicate name.

Before editing a config file, make a private backup. Preserve every unrelated
key/server and comments; never replace the entire file with the snippet. Parse
the result as TOML and verify unrelated configuration is unchanged. Keep config
contents and any credentials out of chat/logs. Reuse the existing native/host
approval policy; a new install needs no policy file because native is the default.

Do not enable writes, legacy FTS, host auto-approval, cloud services or provider
APIs as part of a basic new installation. If the user explicitly requested writes,
enable only those executors and keep independent native review by default.

## 4. Connect, grant necessary access, and verify

Save and restart this MCP connection. Prefer the per-server Restart action over
restarting the whole app-server. If the host requires interrupting your session,
save progress and tell the person exactly how to resume before restarting.

Run `doctor` through the actual desktop tools. Mail Automation, Calendar,
Contacts and Mail-folder Full Disk Access are separate permissions. Request only
an observed missing permission for a requested feature. Native read calls can
trigger normal app permission prompts; `doctor` itself does not. The person may
need to click the OS dialog. Do not use sudo, modify TCC databases or grant broad
privacy access by script. Report the actual app/helper performing denied reads;
do not repeatedly ask for an irrelevant process's permission.

Verify from the **desktop tool catalog**, rather than only Terminal:

1. New read-only install: 16 tools, combined `mail_search` present; legacy/native
   aliases absent. A preserved guarded profile has 19 tools.
2. Call `doctor`, Mail account discovery, calendar discovery and one-contact
   pagination. Keep private contents out of the installation report.
3. Search a narrow recent date range with a common keyword, then an unlikely
   negative. Inspect incomplete/partial counts and unchanged flags. If no positive
   is found, choose a known subject token from a bounded metadata listing.
4. Read one result with its returned account, mailbox, local ID and RFC identity
   copied to `expected_message_id`. Both bracketed native RFC identities and
   public Mail identities are accepted; altered IDs must not be accepted.
5. Verify one quoted phrase and its reversed-order negative if practical. Do not
   claim exhaustive archive coverage, fuzzy semantics or an unsupported OS format.

No test email, Calendar event, invitation, native-store write, shadow-index build
or existing-item deletion is part of installation verification.

## 5. Finish with a usable handoff

Report the installed revision and path, server name, read-only/executor profile,
effective approval mode, actual desktop checks passed and any precise blocker.
Give the user two or three example requests from docs/USAGE.md. If a reload or
permission still blocks actual desktop calls, mark installation **pending that
step** and continue verification when they return. Do not call it fully connected
because package installation or `doctor` succeeded.

The copy/paste workflow is inspired by
[Framer's external-agent install prompt](https://www.framer.com/agents/external/).
This is a local source installation, not an OpenAI Directory/plugin submission.
