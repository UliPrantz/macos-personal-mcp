# 0004: Native per-action Mail approval and a durable outcome journal

Status: implemented and controlled live delivery verified, 23 October 2026.

The earlier read-only desktop registration choice below is superseded by
[decision 0009](0009-guarded-native-desktop-profile.md). The independent native
approval and outcome-safety requirements remain unchanged.

The mandatory-native-only approval policy below is superseded by
[decision 0010](0010-owner-configurable-server-approval.md): the owner can
explicitly delegate server review to the host/model. Native remains the default.

## Decision

Keep the registered desktop server read-only. `--enable-writes` continues to
expose schemas with execution disabled. A separate explicit local launch mode,
`--enable-mail-send`, enables only the Mail executor; Calendar writes/invitations
remain unavailable. A tool cannot change launch mode. No model boolean, digest,
preview or arbitrary token grants consent.

Use a disposable Python AppKit NSAlert for independent human review. Show every
literal sender/To/CC/BCC address, subject, complete body, original attachment
paths, sizes and SHA-256 hashes. Text is plain, selectable and scrollable.
Cancel is the default Return action; Send has no keyboard shortcut. The parent
bounds creation/I/O/response/cancellation and kills/reaps the dialog after three
minutes. Missing UI, invalid response, digest mismatch, denial or timeout prevents
native write dispatch. The dialog runs only for an explicitly invoked operation,
never at server startup. No UI automation is used.

The owner exercised both approval and cancellation on the same prepared private
self-test preview through the native dialog. These diagnostic invocations had no
send path and dispatched nothing. Synthetic integration tests separately prove
that executor denial, missing approval and changed bytes dispatch nothing.
A real send invocation still requires its own native confirmation; diagnostic
approval is not stored as a reusable grant.

## Attachments and outcome safety

Snapshot attachment bytes into owner-only application storage before review,
verify their hashes against the preview, and revalidate original files after
approval. Pass the verified frozen paths to Mail, preserving basenames. Keep
snapshots after dispatch because Mail may still consume them asynchronously,
including when the external outcome is unknown. Denied/preparation-only snapshots
are removed. This bounded per-operation artifact is not a background service.

Owned storage: `~/Library/Application Support/macos-personal-mcp`, mode 0700.
The SQLite `write-outcomes.sqlite3` file is 0600 and records only operation ID,
payload digest, status and timestamp; never recipients, body, subject or credentials.
Reserve the operation atomically, persist dispatch_started before even creating a
Mail draft, and record accepted or outcome_unknown afterward. Crash markers,
uncertain outcomes and repeated IDs cannot trigger another approval or dispatch.
Changed payload with a reused ID is rejected. This does not promise exactly-once
provider delivery. An Apple Mail send acknowledgement is not delivery proof.

Source-app errors after dispatch may leave a draft or an email with unknown
outcome; do not automatically delete it or resend. The write bridge rechecks the
unique enabled sender and native recipients/content before calling send. Tests
prove unreviewed native content/ambiguous senders cannot send. A controlled live
test must still verify receipt and attachment bytes.

## Lifecycle

No source data, global configuration or other MCP registration is changed by this
mode. Installation remains local STDIO. A host using this opt-in mode needs a tool
timeout longer than the three-minute human review plus native dispatch (for
example 240 seconds). Read-only configuration remains unchanged.

Inspect the journal and Mail/Sent/recipient state before considering any new
operation after uncertainty. Do not change IDs to bypass uncertainty checks.
Owner-only retained `attachments-<operation_id>-*` folders may be removed manually
after delivery/outcome is resolved; removing them while Mail is consuming files
can break a pending send. Uninstall by removing this project's MCP entry, isolated
runtime and, only when all pending outcomes are resolved, its owned storage.
Never delete Mail data or another application's state.

Reference: [Apple NSAlert](https://developer.apple.com/documentation/appkit/nsalert).

## Controlled live result

The owner subsequently confirmed the actual guarded STDIO invocation. Apple Mail
accepted the command; exactly one Sent and recipient Inbox copy shared the same
RFC identity. Both decoded 107-byte attachment copies matched the original hash.
The desktop MCP read the received body completely and observed unchanged flags.
No repeated send or invitation occurred. The normal desktop entry stays read-only.
