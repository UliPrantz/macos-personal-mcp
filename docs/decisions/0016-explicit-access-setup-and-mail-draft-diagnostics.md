# 0016: Explicit access setup and clear Mail draft failures

Date: 25 October 2026. Implemented in version 0.3.2.

The owner reported a send remaining in Drafts and confusing Calendar/Contacts
setup instructions: readers checked authorization but never requested a first
grant, while the agent sent users to Settings before any entry necessarily existed.

## Permission setup

Keep `doctor`, startup and ordinary data reads nonprompting. Add per-domain
`next_actions` and observed executable/parent context to doctor. Distinguish
not-determined, denied, restricted, Calendar write-only, Contacts limited and
unknown states. Do not infer macOS's responsible identity from a process path or
promise the Settings entry is named after the MCP.

Add one explicit `request_permissions` tool with a required Calendar or Contacts
domain. Use public EventKit/Contacts request selectors in the existing bounded
native worker. Only an undecided permission or Calendar full-access upgrade can
request; existing adequate grants, denial and restrictions do not prompt again.
Inspect the authorization state after the callback; completion alone is not a
grant. A timeout or unchanged undecided result directs diagnosis rather than
repeated requests or premature Settings advice. Public OS dialogs remain the
human decision point; no permission reset, database modification or provider API.

The setup tool is available when source writes are disabled, as an explicit
exception to the prior blanket UI-effect exclusion in read-only mode. It is
annotated non-read-only, non-destructive and non-idempotent. It does not enable
send/create executors or alter app records, config or server approval. There are
16 pure read tools plus one setup tool (17 total); three optional executors make
20. Explicit legacy search adds one more. Mail Automation and Full Disk Access
remain separate, with feature-specific instructions.

Request usability depends on the actual host's native GUI/privacy metadata.
A failed native request must remain a failed/undecided grant, with concrete host
remediation. Do not guarantee first-run prompting on an untested host or change
permissions already working merely to manufacture a test.

## Mail draft diagnosis and fix

Read-only investigation matched an existing draft to its original reviewed tool
payload and uncertain outcome record. Sender, subject and recipients matched,
but Mail's live outgoing-message body had one additional trailing ASCII space.
The existing exact equality guard would reject that body before the send call.
No replacement message or event was created, deleted or sent in the investigation.
Keep real addresses, subjects, IDs, bodies and raw logs outside the public repo.

Accept exact body equality or precisely one appended ASCII space, the observed
Mail rich-text artifact. Do not broadly trim whitespace, normalize other content,
accept a signature or silently authorize material changes. All address/subject
checks and attachment snapshot protections remain.

Return a typed safe failure code on native draft-verification rejection, explaining
that the send command was not called. Preserve conservative uncertain-write
status because a draft creation is a native effect. Persist safe failure codes
in a separate table in the owned outcome journal so replay retains useful
diagnostics without storing payloads. Preserve the original four-column outcomes
table for older live clients. Extend old journals transactionally without resetting uncertain IDs.
Other native failures report a safe stage/code and recommend inspecting Drafts,
Outbox, Sent and receipt before any retry. Never automatically delete drafts,
replay an uncertain send or claim an acknowledgment proves delivery.

Synthetic tests cover the exact whitespace allowance, rejected changes,
permission state/action distinctions, explicit setup in read-only mode, deadlines,
old-journal migration and persistent no-retry barriers. Existing-grant live checks
can verify the no-op request path without changing permissions. A fresh desktop
catalog/reload and any specifically approved controlled send are separate live
gates; record their actual status in STATUS.md.

## Follow-up: direct ChatGPT host validation (0.3.3)

A real first request from ChatGPT 26.1021.31345 granted Calendar access but refused
Contacts without a dialog. The native privacy log explicitly attributed the
request to ChatGPT and cited its missing hardened-runtime Address Book
entitlement. Signing metadata confirmed that omission and the absent Contacts
purpose string. There was no ChatGPT entry in Contacts privacy settings. Earlier
successful reads from a separately authorized launch context did not validate
this direct embedded host.

Do not equate denied authorization with a user declining a prompt or assume a
Settings entry exists. First-request Contacts error 100 directs host diagnosis,
while a real user refusal with an existing entry can still use Settings. The
affected host requires an app fix or a properly authorized native helper for
direct framework access; no helper or third-party app modification is added. The README must
expose this compatibility limit rather than imply Contacts universally works.

Peer review found an existing alternative: Contacts.app through public Apple
Events. Local probes succeeded, but subsequent direct-host reads failed even
after Automation consent because the original caller's Contacts authorization
still applies. Decisions 0017/0018 record the explicit backend and host boundary.
Record identities differ from unified CNContactStore; no automatic fallback is
used. See [the permission comparison](../PERMISSION_MCP_COMPARISON.md).

Doctor reports its loaded server_version, and error guidance explains that an
old server can retain an old catalog while newly spawned workers read new files.
Restart the existing connection and rediscover; no new checkout is needed.
