# Mail capabilities for agents

This is the supported contract, with evidence scoped to the development Mac.
The tool descriptions, input schemas, initialization instructions and `doctor`
expose the most important limits without requiring repository access. A running
connection needs an update and reload before it exposes changed descriptions or
features. Do not infer deployed capabilities from an unmerged pull request.

## Compose and send

| Feature | Current contract | Verification and limits |
| --- | --- | --- |
| Special characters | `body` and `subject` accept Unicode strings. Body limit: 1,000,000 characters; subject limit: 998 characters. CR/LF/NUL are rejected in subjects. | Synthetic bridge tests preserve accented text, emoji, quotes and script-like punctuation. Received UTF-8 MIME from an earlier test preserved an accent, pound sign and cat emoji. An approved 27 October 2026 send preserved its Unicode subject and sampled umlauts, accented letters, currency, punctuation, emoji and Chinese text in decoded Sent and recipient Inbox MIME. This does not certify every character, recipient client or internationalized email address. |
| URLs | Include the full URL as plain body text, including its query and fragment. | No link renderer or custom anchor-label API exists. The controlled received MIME preserved the sampled URL exactly, including percent encoding, ampersand, plus sign and fragment, but contained no HTML anchor. Actual recipient-client clickability was not tested. |
| Formatting | Input is plain text, including paragraphs. | No HTML, Markdown or RTF authoring mode; no guarantee of bold, tables, styled lists, named hyperlinks, inline images or pixel-exact layout. The controlled received MIME retained Markdown markers literally and escaped HTML tags instead of rendering them. Mail may generate HTML MIME from plain input; that does not make the input an HTML API. |
| Native layout | The draft must match the approved body, allowing only Mail's observed one appended ASCII space. | Delivered MIME can still add a leading empty paragraph and quote wrapper. This remains unresolved. Do not trim or normalize arbitrary content to bypass the guard. See [decision 0019](decisions/0019-mail-scripted-body-formatting.md). |
| Sending attachments | Up to 20 absolute readable regular-file paths, each at most 20,000,000 bytes, with at most 50,000,000 bytes combined. Final-component symlinks are rejected. | These are input limits, not provider limits; encoded message size and account policies can impose lower limits. No attachment URL, remote download, inline/CID placement or cloud-link substitution is provided. Mail controls attachment placement and can split body HTML around files. |
| Attachment identity | Preview reports byte count and SHA-256. Review binds these identities; private frozen copies preserve filenames for dispatch, and changes detected before dispatch invalidate the reviewed request. Later original-file changes do not alter frozen bytes. | Historical controlled sending verified received attachment bytes. The new Sent and recipient Inbox copies contain a 52-byte text file and 256-byte binary file, each matching its approved SHA-256 and bytes. The accented filename is canonically equivalent but uses decomposed Unicode rather than the submitted precomposed character. Filename codepoint identity is not guaranteed. The stopped mailto/RTF formatting candidates did not establish attachment delivery through those paths. Do not extrapolate to all file types, sizes or accounts. |
| Send outcome | `accepted` means Mail accepted the native send command. | It is not proof of Sent synchronization, delivery, Inbox placement, final formatting or attachment integrity at the recipient. Check Sent and receipt by RFC Message-ID, then decode recipient MIME and compare attachment hashes when required. Do not retry an uncertain operation, including with a fresh operation ID, or delete its draft automatically. |
| Replies | A subject beginning `Re:` can cause client-side conversation grouping. | Subject-only sends do not establish `In-Reply-To`/`References`. This revision supports exact native replies through `reply_to_message`; check the running tool's schema before using it. See [reply behavior](decisions/0020-exact-native-mail-replies.md); native replies may change the original's read/replied flags. |

The API validates literal addresses separately from body text. Unicode body
support is not a claim of SMTPUTF8 address delivery. Always use the exact
configured sender and approved To/CC/BCC addresses. A preparation preview is
neither consent nor a send, and its `executable=false` is not a delivery result.

## Read messages, attachments and read state

| Operation | Available now | Limits |
| --- | --- | --- |
| Message reads | `mail_get_message` returns bounded body text, headers, metadata and attachment names/IDs/approximate sizes. | Inspect `body_truncated`. This is Mail's text rendering, not a byte-exact source/body round trip; the controlled attachment message included additional blank lines and U+2028 separators. Use decoded source for fidelity checks. Attachment metadata does not contain downloadable file bytes. |
| RFC/MIME source | `mail_get_source` returns complete source within the explicit character bound, after identity validation. | Unavailable or oversized source fails instead of returning a successful partial source. Decode MIME transfer encodings and charsets before comparing text or attachment bytes. Inspect the full MIME tree: Mail can put several body HTML fragments around attachments in multipart/mixed; the first HTML part may be empty. Exclude text attachments from body comparisons. A plain-text alternative may contain U+FFFC attachment placeholders. There is no dedicated attachment download/save/extraction tool. |
| Search | Locally available subject/sender/body search, with coverage reporting. | Attachment contents are excluded. Search coverage is not exhaustive; missing/partial bodies and unsupported native formats remain possible. |
| Read/unread inspection | Message metadata includes `read`; listing/search support `unread_only`; mailbox listing includes scoped unread counts. | Counts and filters describe their observed scope, not a continuously synchronized global snapshot. |
| Read-state preservation | Message/source reads sample `read_before` and `read_after`, fail on an observed change, and never set or restore flags. Native catalogue search opens storage read-only. | An error does not guarantee flags remained unchanged. Native errors may be redacted to `native_failure`; concurrent changes by Mail or another client cannot be excluded. Search's `flags_unchanged` describes this reader's non-writing path, not a lock on other clients. |
| Mark read / mark unread | **Not implemented by this MCP**, in any launch mode. | Mail's local public scripting dictionary exposes writable Boolean `read status`, so a native future tool is feasible. This is API inspection, not a tested mutation or an existing feature. Do not substitute a reply, UI action or provider API to change flags. |

The new controlled recipient Inbox message was unread. Sequential source and
message reads both reported `read_before=false` and `read_after=false`; the
message metadata also remained unread. Earlier existing-message rechecks
observed read-to-read preservation. No read-state mutation was performed for
this audit. A future setter needs an exact account/mailbox/message
identity, an explicit desired Boolean, guarded write exposure and readback of the
result, separately from read-only tools.

## Evidence and agent workflow

Distinguish schema acceptance, synthetic execution, native draft verification,
send acceptance and recipient verification. They establish different things.
Normal CI uses synthetic data and sends nothing. The live observations above
come from explicitly approved self-sends on the development Mac, using Apple
Mail 16.0 (3864.600.51.1.1); they are not promises for every launcher or account.
Raw source, addresses, message IDs, journals and full test payloads stay private.

Before sending, review the complete sender, all recipients, subject, body and
attachment identities under the configured approval policy. Explain relevant
unsupported formatting before the user approves it. Never claim that a preview,
successful command or an unread flag alone proves delivery or clean formatting.

See [current verification](STATUS.md), the [behavior contract](PROJECT_SPEC.md),
[approval and writes](TECHNICAL_DETAILS.md#approval-and-writes) and the
[comparison of other Mail MCPs](MAIL_MCP_COMPARISON.md#sending-and-body-formatting-follow-up).
