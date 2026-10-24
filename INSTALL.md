# Install macOS Personal MCP

Connect ChatGPT desktop to the Mail, Calendar and Contacts apps on your Mac.
Choose **let an agent install it** or **install it yourself**. New installations
start read-only. Existing owner-selected write/approval settings are preserved.

## Let an agent install it

Paste this into ChatGPT desktop with local computer/Terminal access, Codex, or
another agent that can run commands on **this Mac**:

```text
Install https://github.com/UliPrantz/macos-personal-mcp on my Mac for ChatGPT
desktop. Follow docs/INSTALL_WITH_AGENT.md and handle setup, configuration and
verification yourself. Inspect any existing checkout, preserve my other MCPs
and approval settings, and start new installs read-only. Ask me only for macOS
permission dialogs or a restart you cannot complete yourself.
```

An agent running only in a cloud browser/container cannot install on your Mac.
This repository is public; cloning it does not require a GitHub account.

## Install it yourself

### 1. Download and install

Requires an Apple Silicon Mac, ChatGPT desktop with local MCP support, internet
access and Git. The tested full archive-search profile is **macOS 26.5.2**;
other versions have no validated large-scope body-search support. Small local
body scopes and other native tools have separate capability checks.

If the checkout already exists, inspect it and follow [Updating](#updating).
For a new checkout, paste into Terminal:

```sh
mkdir -p ~/Developer/Projects
git clone https://github.com/UliPrantz/macos-personal-mcp.git ~/Developer/Projects/macos-personal-mcp
cd ~/Developer/Projects/macos-personal-mcp
sh scripts/install.sh
```

If Git asks to install Apple's Command Line Tools, finish that system dialog
and rerun the commands. If cloning fails, check the repository URL and network
connection. No GitHub credentials are needed to clone the public source.

The installer downloads pinned uv and Python 3.15.1 and installs locked packages
inside this checkout. It leaves your shell profiles and global Python alone.
Source builds need Apple's Command Line Tools. If Rust is missing, the script
installs a minimal Rust 1.99.1 build toolchain under `.local/` as well; it does not
change your global Rust installation. The first install can take several minutes.
Keep the checkout in place afterward:
the desktop launches its `.venv/bin/macos-personal-mcp` directly.

### 2. Connect ChatGPT desktop

Open **Settings → MCP servers → Add server**. Enter:

| Setting | Value |
| --- | --- |
| Name | `macos-personal` |
| Transport | `STDIO` |
| Command | Copy the absolute executable path printed by the installer |
| Arguments | `serve`, `--read-only` (two arguments) |
| Tool timeout, if offered | `240` seconds |

Save, then select **Restart** for this connection. This is the local MCP route
documented by [OpenAI](https://learn.chatgpt.com/docs/extend/mcp); a website URL
or remote-server form cannot launch this native process.

Alternatively, merge the generated `.local/chatgpt-mcp.toml` table into
`~/.codex/config.toml` (or your host's configured Codex directory). Preserve the
rest of the file and avoid adding a duplicate table. This also sets the timeout.
The installer prepares the snippet; it does not edit host configuration itself.

### 3. Permissions and verification

Ask ChatGPT:

```text
Check macos-personal with doctor. List my Mail accounts, calendars and one
contact. Search the last three days for a word I choose, then read one result
using its exact returned identity. Report any incomplete search coverage.
```

Allow the native macOS dialogs for the features you want: Mail Automation,
Calendar and Contacts. `doctor` reports status without requesting grants, so an
actual read may be needed to trigger a feature's dialog. For Mail-file search,
check **System Settings → Privacy & Security → Full Disk Access** if access is
denied. Enable the app/process actually running the tools; the host may be
ChatGPT or a separate background helper. If macOS asks to quit/restart it, save
the conversation first, then resume and verify from the desktop again.

Do not grant additional permissions when the required reads already work. No
mail-provider credentials or separate Google/Microsoft/iCloud login are needed.
Accounts must already exist in the native apps. Native apps may synchronize
through those configured accounts.

Success means the **actual desktop catalog** exposes 16 read tools, including
the combined `mail_search`, and real searches/reads work. `mail_search_native`
and `mail_search_legacy` should be absent. No manual body indexing is required.
A Terminal-only test or `doctor` alone does not establish desktop access.

## Start using it

- “Find emails about the project deadline from the past three days.”
- “Find the email containing the exact phrase ‘existing credits’.”
- “Show my calendar for tomorrow.”
- “Find Alex's email address in my contacts.”

For search, the model should turn relative dates into timezone-aware bounds,
quote addresses/phrases, inspect coverage and use each result's identity to read
the message. [Usage guide](docs/USAGE.md) explains the few search restrictions.

## Enable sending or calendar creation

Read-only is the default. If you want writes, change the server arguments to:

```text
serve --enable-mail-send --enable-calendar-create --enable-calendar-open
```

Restart that connection. This exposes 19 tools. Sends and event creation use
independent native human confirmation by default. [Approval configuration](README.md#approval-and-writes)
explains deliberate host/model delegation. The installer does not opt you into it.
Calendar invitations/attendee creation are outside this native-only version.

## Updating

Inspect `git status` and confirm `origin` is this repository. Preserve local
changes. With a clean checkout, fast-forward to the desired verified revision
and rerun `sh scripts/install.sh`, then restart only this MCP connection.
For a development checkout use `sh scripts/install.sh --dev` to retain dev tools.
Existing MCP registration, write flags and approval policy remain unchanged.

## Troubleshooting and removal

| Symptom | Next step |
| --- | --- |
| No tools | Check the absolute command exists, save/restart the connection, and confirm local STDIO support |
| Old schema or legacy tool | Restart the existing connection and rediscover tools |
| Mail folders denied | Check the actual launching app/helper's Full Disk Access, then restart if macOS requires it |
| `native_profile` | This OS's large native index format is unvalidated; use a narrow date/account scope (at most 500 unresolved bodies) |
| `stale_cursor` / changing source | Start a fresh search at offset zero; do not reuse its old snapshot |
| Partial/unavailable bodies | Some local text is missing or undecodable; treat negative results as incomplete |

To uninstall, remove only the `macos-personal` server entry. After stopping it,
you may remove this checkout and its isolated runtime. Owned outcome journals
and pending attachment snapshots live separately in application data; preserve
unresolved sends. Never delete Mail, Calendar or Contacts data to uninstall.

Installer isolation follows [uv's documented installer controls](https://docs.astral.sh/uv/reference/installer/)
and [local Python/storage settings](https://docs.astral.sh/uv/reference/storage/).
The optional build compiler uses [Rust's documented local installation controls](https://rust-lang.github.io/rustup/installation/).
