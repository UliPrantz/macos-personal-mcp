# 0002: Verified offline development, explicit native and write gates

Status: initial restricted-session implementation boundary, 22 October 2026.
Product incomplete. Later the same day unrestricted task access restored GitHub
networking and Mail account discovery; target-interpreter CI passed, and a local
Python 3.15.1 installation became available through isolated uv 0.13.5. The owner
granted native permissions and enabled ChatGPT Full Disk Access, pending restart.
The offline/access evidence below is historical; consult [STATUS.md](../STATUS.md)
for current measurements. Write execution remains closed.

## Runtime and dependency evidence

Retain Python 3.15.1 as the installation target and `requires-python >=3.15`.
Do not claim that the local compatibility environment meets that target.
The installed uv 0.13.1 reports `No download found for request:
cpython-3.15.1-macos-aarch64-none`. The shell cannot resolve GitHub or PyPI.
Homebrew provides 3.15.0; no compatible cached Pydantic core wheel is available
for it. This is an access/artifact blocker, not proof that Python 3.15 is unsupported.

An isolated `.local/test-env` using the existing Python 3.14.7 interpreter and
cached SDK 2.0.0/Pydantic 2.13.4 runs compatibility tests without changing any
global installation or the WhatsApp environment. It is not the production install.
Cached installed distributions were repackaged only into ignored local wheels for
these tests. These repacked archive hashes are **not** upstream artifact hashes.

The portable uv.lock uses original PyPI URLs/hashes from existing lock records
and uv download metadata, with dependency resolution performed by uv against
the available metadata. No local wheel/archive paths belong in that lock.
`uv lock --check --offline --python /opt/homebrew/bin/python3.15` accepts it.
A fresh locked installation on 3.15.1 remains unverified. The current lock targets
Apple Silicon macOS; other platforms are not supported by this revision.

Use the official SDK's v2 `Server` handlers, explicit tool schemas and strict
Pydantic JSON validation. Test real SDK clients with modern discovery and the
legacy initialize handshake. Keep transport stdout free of diagnostics.
References: [SDK](https://py.sdk.modelcontextprotocol.io/),
[Python 3.15.1](https://www.python.org/downloads/release/python-3151/).

## Small fixed native bridge

This revision uses Python application/domain code with one fixed bundled JXA
Apple Events adapter. Arguments are JSON data passed separately from script
source. Native results are strictly validated in Python. This is the minimal OS
scripting exception allowed by the specification, not a new application backend.
Node is used only to run synthetic bridge fixtures in tests.

The available PyObjC core cache is for CPython 3.12; Contacts/EventKit bridge
packages for the target are unavailable offline. Installing/replacing native
bridges must wait for dependency access and real permission checks. Do not spread
dynamic Objective-C values through domain code. Retain the typed Bridge protocol
so a public PyObjC adapter can replace the fixed script after measured verification.

The script has no native mutation commands. Header reads do not fetch bodies.
Targeted reads compare RFC identity before body access and again afterwards;
observed read-state changes fail without restoring flags. Offset pages describe
their concurrency limits. Calendar recurrence/timezone/all-day coverage and
limited Contacts access remain explicitly incomplete.

## Writes remain closed

Read-only discovery omits all four source/UI-mutating tools; dispatch rejects
them even if a client guesses the name. `--enable-writes` exposes conservative
write schemas but still refuses execution before native dispatch. No host policy,
model boolean, preview digest or prepare/commit call is treated as human consent.

Mail preparation validates an unambiguous configured sender, literal To/CC/BCC,
regular attachment files, sizes and content hashes. It produces a concrete
preview only. It does not arm a send. No write journal is needed yet because no
write executor exists. Before introducing any executor, implement and test the
outcome journal, payload/attachment revalidation, exact human review and unknown
outcome handling together. No uncertain action may be retried automatically.

Host per-tool prompt settings exist in
[official desktop configuration documentation](https://developers.openai.com/codex/mcp/),
but have not been demonstrated with this MCP in the desktop conversation.
The fail-closed gate is independently tested; human approval enforcement is not
claimed complete.

## Required investigations

`~/Library/Mail` cannot be listed by this process. No database was opened and no
privacy setting was changed. Full-body ingestion, refresh, MIME decoding/indexing,
coverage/freshness and real corpus performance remain blocked. Do not implement
a nominal cache over bounded body scans and call it complete search.

The installed Calendar dictionary exposes read-only attendee email/name/status.
[Apple's EventKit participant contract](https://developer.apple.com/documentation/eventkit/ekparticipant)
does not permit adding participants. Calendar account discovery itself fails
in this process, so no suitable provider scheduling adapter or authorized provider
credentials have been established. Invitation execution must fail before any
partial event or notification. No ICS email or private setters are substituted.
