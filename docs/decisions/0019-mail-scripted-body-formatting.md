# 0019: Scripted Mail body formatting is a native limitation

Date: 27 October 2026.

## Evidence

A controlled, explicitly approved self-send reproduced a leading empty paragraph
and a quote block in the delivered message. The submitted body had neither.
The raw MIME contained an `Apple-Mail-URLShareUserContentTopClass` empty div and
an `Apple-Mail-URLShareWrapperClass` blockquote; the plain alternative began with
a newline and quote prefixes. Mail's outgoing `content()` still matched the
reviewed body (or its previously observed single trailing ASCII space).

Creating an empty scripted message and assigning its content afterwards did not
remove the wrapper in a second approved delivered test. Therefore changing setter
order is not a fix. Draft readback cannot prove final MIME formatting.

Mail's public `mailto` command was also tested with an approved payload. A compose
window appeared, but no new object appeared in `outgoingMessages()`, including
on later inspection. The candidate stopped before sending, retained its uncertain
operation record, and was not retried. A visible compose window does not establish
a public scripting handle suitable for sender verification, attachments or send.

Mail's local scripting dictionary exposes writable rich text but describes the
hidden `html content` setter as deprecated and doing nothing. There is no public
outgoing-header setter or quote-level property. Do not substitute private APIs,
UI automation, SMTP or a mail-provider connection under the native-only contract.

## Decision

Do not ship either failed workaround or label this problem fixed. Keep the
existing send path and record the delivered-format limitation where users enable
sending. Keep the prior draft/send fix: accept exact body equality or precisely
one appended ASCII space. Never trim or ignore a leading newline to conceal this
different problem. Regression coverage rejects native draft leading newlines,
extra trailing spaces and appended newlines, while the single-space case sends.

Normal synthetic tests establish guards and control flow, not Apple's MIME
serialization. A future formatting fix requires an approved delivered MIME test
and attachment verification through that exact path. Never retry an uncertain
operation or delete its drafts automatically. Private test addresses, bodies,
message IDs, native exports and operation records remain outside Git.

The observed behavior matches the original reporter's
[Mail scripting reproduction](https://forums.macrumors.com/threads/applescript-creating-a-new-message-in-mail-app-is-causing-weird-formatting-issues.2385052/).
That report's mailto suggestion is not sufficient for this MCP's guarded sender.
