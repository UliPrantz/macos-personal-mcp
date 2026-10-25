# 🍎 macOS Personal MCP

**Your Mail, Calendar and Contacts, connected to ChatGPT.**

You know the answer is somewhere on your Mac. A date buried in an email, a
meeting in your calendar, a contact whose address you can never remember.
Ask your AI to find it, read it and help you act on it.

macOS Personal MCP connects an AI assistant to the Apple apps you already use,
with the accounts you already have. It works locally on your Mac and starts
read-only. You can enable sending emails and creating calendar events when
you're ready.

**Apple Silicon Mac · ChatGPT desktop with local MCP support · [AGPLv3](LICENSE)**

## ✨ A little less app-hopping

Imagine getting ready for tomorrow. Your calendar has the meeting, Mail has the
conversation, and Contacts has the person you need to follow up with. Now you
can bring that context into one conversation:

> What's on my calendar tomorrow? Find the recent emails about those meetings
> and help me prepare.

Or start with the small things that eat up your day:

- 🔎 **Find what you half-remember.** “Find the email containing ‘existing credits’
  from the past three days, and read me the relevant part.”
- 📧 **Catch up on a conversation.** “Find this week's emails about the project
  deadline and summarize what changed.”
- 👥 **Follow up.** “Look up Alex's email address and draft a reply here for me to review.”
- 📅 **Put it in the calendar.** With event creation enabled: “Add a 30-minute
  preparation block tomorrow morning to my work calendar.”

The assistant can search email subjects, senders and full locally available
bodies, read messages, check calendars and look up contacts. Optional sends and
event creation show a confirmation dialog by default.

## 💡 Why this exists

[Apple MCP](https://github.com/supermemoryai/apple-mcp) showed how useful it could
be to let an AI work with the apps already on a Mac. This project takes that
idea into everyday Mail, Calendar and Contacts workflows, with particular care
for finding the email you actually need and reading it correctly.

There are no separate Gmail, Microsoft or iCloud API keys to configure. Mail
search reuses local Mail data and, for larger searches, Apple's existing search
index. You don't need to build or maintain a second email index to get started.

**Local access, with a clear data boundary:** this MCP runs on your Mac and adds
no separate mail-provider connection. The messages and other data you ask it to
retrieve are returned to your AI app and handled under that app's data policy.
Your native Apple apps continue to sync normally.

## 🚀 Get started: let your AI install it

Copy this into **ChatGPT desktop with local computer/Terminal access, Codex, or
another agent that can run commands on your Mac**:

```text
Install https://github.com/UliPrantz/macos-personal-mcp on my Mac for ChatGPT
desktop. Follow docs/INSTALL_WITH_AGENT.md and handle setup, configuration and
verification yourself. Inspect any existing checkout, preserve my other MCPs
and approval settings, and start new installs read-only. Ask me only for macOS
permission dialogs or a restart you cannot complete yourself.
```

The agent handles installation and connecting the tools. You approve any macOS
permission dialogs. No GitHub account is needed. An agent running only in a
cloud browser cannot install software on your Mac.

**Compatibility:** requires an Apple Silicon Mac. Full archive body search is
currently validated only on **macOS 26.5.2**; other versions have no validated
large-scope body-search support. [Compatibility and troubleshooting](INSTALL.md#troubleshooting-and-removal).
Contacts also depends on your AI app: the tested ChatGPT desktop build blocks
the default direct Contacts API before showing a permission dialog. The optional
`--contacts-backend contacts-app` route uses native Automation consent instead
(no screen control); verify it from your actual ChatGPT connection.
[Host compatibility and next steps](docs/PERMISSIONS.md#contacts-refused-without-a-dialog-in-chatgpt).

<details>
<summary><strong>🛠️ Prefer to install it yourself? Three steps</strong></summary>

You'll need Git, internet access and ChatGPT desktop with local MCP support.
The installer supplies Python and dependencies inside the checkout.

**1. Install.** For a new checkout, paste into Terminal:

```sh
mkdir -p ~/Developer/Projects
git clone https://github.com/UliPrantz/macos-personal-mcp.git ~/Developer/Projects/macos-personal-mcp
cd ~/Developer/Projects/macos-personal-mcp
sh scripts/install.sh
```

If prompted to install Apple's Command Line Tools, finish that installation and
rerun the commands. The first install can take several minutes. Keep the checkout
at this location. If it already exists, [inspect it before updating](INSTALL.md#updating).

**2. Connect.** Open **ChatGPT → Settings → MCP servers → Add server**:

| Setting | Enter |
| --- | --- |
| Name | `macos-personal` |
| Transport | `STDIO` (local process) |
| Command | The absolute executable path printed by the installer |
| Arguments | `serve` and `--read-only` as two arguments |
| Tool timeout, if offered | `240` seconds |

Save and **Restart** that connection.

**3. Allow access and try it.** Ask ChatGPT to run `doctor` and follow its
`next_actions`. If Calendar or Contacts says `not_determined`, ask it to call
`request_permissions` for that feature, then approve the macOS dialog. There may
be no Settings entry until that first request. [Permission help](docs/PERMISSIONS.md).
If Mail-file search is denied, check **System
Settings → Privacy & Security → Full Disk Access** for the app or helper running
the MCP, then restart it if macOS requests that. Ask ChatGPT:

```text
Check macos-personal with doctor, then find emails about the project deadline
from the past three days and read the most relevant result. Report incomplete
search coverage.
```

You should be able to search and read a result from ChatGPT. No manual indexing
or separate mail-provider login is needed. [Detailed setup and removal](INSTALL.md).

</details>

<details>
<summary><strong>✉️ Enable sending emails and creating calendar events</strong></summary>

New installations start read-only. To enable these actions, replace the server
arguments with:

```text
serve --enable-mail-send --enable-calendar-create --enable-calendar-open
```

Restart the connection. Sends and event creation ask for native human
confirmation by default. You can also deliberately delegate approval handling
to your AI app through [approval configuration](docs/TECHNICAL_DETAILS.md#approval-and-writes).
Calendar invitations and adding attendees are not supported.

</details>

## 🎯 What to expect today

Search, message reads, Calendar and Contacts have been tested through the actual
desktop connection. Recent-mail searches are usually quick in our measured
scopes; larger archive searches can take several seconds. Keywords, exact
phrases, date ranges and limited typo matching work. Semantic search is not
implemented.

Search depends on what's available locally. Missing or partial bodies and index
gaps are reported, so an incomplete search isn't presented as proof that an email
doesn't exist. [Measured results and current limits](docs/STATUS.md).

[More everyday examples](docs/USAGE.md) · [Installation help](INSTALL.md) ·
[Report a problem](https://github.com/UliPrantz/macos-personal-mcp/issues)

<details>
<summary><strong>⚙️ Technical details, configuration and development</strong></summary>

- [How the tools work and their limits](docs/TECHNICAL_DETAILS.md#implemented-surfaces-and-limits)
- [Search syntax, native index, coverage and optional legacy cache](docs/TECHNICAL_DETAILS.md#full-body-search-and-local-state)
- [Read-only mode, optional writes and approval settings](docs/TECHNICAL_DETAILS.md#approval-and-writes)
- [Permission states, native dialogs and the right Settings entry](docs/PERMISSIONS.md)
- [Development and verification](docs/TECHNICAL_DETAILS.md#development-and-verification)
- [What we learned from other Apple Mail MCPs](docs/MAIL_MCP_COMPARISON.md)
- [Agent installation runbook](docs/INSTALL_WITH_AGENT.md) and [maintainer handoff](docs/CODEX_HANDOFF.md)

</details>

## License and credit

Copyright © 2026 Uli Prantz. [GNU AGPLv3 only](LICENSE), with
[third-party notices](THIRD_PARTY.md) preserved. Commercial use is allowed under
the license; it does not require royalties or reporting your usage.

Using this commercially? [I'd love to hear about it](https://github.com/UliPrantz/macos-personal-mcp/issues).
That's a voluntary invitation, not an extra license condition.
