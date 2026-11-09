# 0021: Open a human-finished email composer with mailto

Date: 9 November 2026.

The owner requested the draft-opening behavior inspected in
[iMCP](../MAIL_MCP_COMPARISON.md#imcp-composer-comparison-8-november-2026).
Implement `mail_compose` independently using public NSWorkspace and `mailto:`.
Do not route it through the scripted `content` setter or the guarded sender.

`--enable-mail-compose` is an owner-controlled launch flag, incompatible with
`--read-only`. Like existing optional executors, its schema is exposed in a
non-read-only registry, but dispatch requires its own enabled adapter. Sending
and Calendar executors remain independently disabled. The action is marked
non-read-only/non-destructive/non-idempotent: it opens UI, creates no server-side
send intent and may open another composer on repetition. Host review applies;
there is no second server confirmation dialog for opening a composer.

Use strict optional recipient arrays and plain subject/body fields. Reject
aliases, duplicates, header/control injection and unknown options. Percent-encode
every field so delimiters cannot become extra mailto parameters. Preserve
intentional whitespace; convert CR/LF line breaks to CRLF without inserting a
leading line. Bound recipients, text, the complete encoded URL, worker execution
and response size. Pass payloads through stdin, never shell code or argv; do not
log bodies, recipients or compose URLs. The fixed native worker runs AppKit on
its main thread and exposes no general URL-opening capability.

The default email app receives the URL and chooses its sender. Sender selection,
attachments, native reply linkage, automatic saving and sending are unsupported.
Report only `open_acknowledged`, with `saved_by_mcp=false` and
`sent_by_mcp=false`; the receiving email app may autosave independently. Native
acknowledgment does not verify rendering or draft persistence. An uncertain open
may already have created UI, so advise inspection before retrying.

This route needs no Mail-file or Mail Automation access. It does not establish
clean delivered MIME or replace `mail_send`; that tool's known blank paragraph
and quote-wrapper limitation remains. Synthetic checks cover encoding, bounds,
gating, schema/STDIO behavior and native refusal/uncertainty. Record any actual
native/desktop observation separately in STATUS.md; never infer visual or
delivery success from those checks.
