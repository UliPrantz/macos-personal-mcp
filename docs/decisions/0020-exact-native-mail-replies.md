# 0020: Reply through Mail's native command to an exact original

Date: 27 October 2026.

An approved subject-only self-send grouped with the original in Apple Mail, but
the delivered message had neither `In-Reply-To` nor `References`. Subject grouping
is a client heuristic, not explicit RFC reply linkage.

Extend the existing guarded `mail_prepare_send` / `mail_send` payload with optional
`reply_to_message`: account ID, exact nested mailbox path, local numeric ID and
expected RFC Message-ID. Default null preserves ordinary sends. Bind the selector
to the approval preview and durable digest; show the original's identifiers and
warn that Mail may update its read/replied flags. Do not infer a reply target from
the subject, addresses or model state. Explicit To/CC/BCC and body remain required.

Resolve the source through public Mail scripting, validate its RFC identity before
and after `reply(original, openingWindow:false, replyToAll:false)`, and reject
absent, ambiguous, stale or changed selectors. As with native reads, one outer
well-formed angle-bracket pair is equivalent; the enclosed value is exact.
Clear all inherited recipient lists and supply only the approved ones. Replace
the body, sender and subject, reject exposed inherited attachments, and retain
the existing draft-field checks and frozen attachment handling before sending.
The native reply command supplies threading headers; no private header setters,
provider connection, SMTP or UI automation is added.

An approved controlled native reply was observed in Sent and the recipient Inbox with `In-Reply-To`
pointing to the original RFC ID and `References` retaining its chain plus that
ID. The body contained the approved text without the original conversation.
Mail still added its known empty paragraph/quote wrapper: native replies do not
fix scripted-body formatting. Reading the received source preserved its unread flag.
Mail exposed an empty reply attachment collection as null; the guard accepts that
observed empty form or an empty array and rejects exposed inherited attachments.
Draft readback and synthetic fixtures cannot prove
final MIME formatting or behavior on another Mail version. Private evidence stays
outside Git. Recipient receipt was checked separately from native acceptance.

Exclude null fields when computing the payload digest. This preserves the exact
old serialization for ordinary sends; adding an optional field must not invalidate
existing journal digests or permit an uncertain send to run again. Reply targets
are included when present, so changing the target under one operation ID conflicts.
Keep approval, frozen attachment snapshots and conservative no-blind-retry behavior
unchanged, including after identity failures or cancellation. Do not delete drafts
or retry automatically.
