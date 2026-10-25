# Use Mail, Calendar and Contacts

You can ask normally; the model supplies tool arguments. Try:

- “Find emails about my project deadline from the past three days.”
- “Find the email containing ‘existing and prepaid credits’ and read it.”
- “What's in my calendar tomorrow?”
- “Find Alex's email address in my contacts.” (Requires a compatible calling app.)

Contacts remains supported, but the tested direct ChatGPT desktop build lacks its
required Contacts entitlement. Changing Settings or granting Automation cannot
add that declaration. Other compatible hosts can use Contacts now; future app
updates can be checked with the same tools. See [host compatibility](PERMISSIONS.md#contacts-refused-without-a-dialog-in-chatgpt).

## Search, then read

`mail_search` is the default search. It checks subject, sender and body across
local accounts/history unless dates or accounts narrow the request. There is no
manual indexing step. Each result includes the selectors needed for
`mail_get_message`: copy `account_id`, `mailbox_path`, `local_id` and `message_id`
(as `expected_message_id`). Do not guess or reconstruct them. A search excerpt
is not the full email. Native IDs enclosed in angle brackets are accepted by
the public message/source reader without changing the identity inside them.

## Search examples for agents

```json
{"query":"project deadline","since":"2026-10-21T00:00:00+01:00","before":"2026-10-24T00:00:00+01:00"}
```

Tokens are ANDed; one can match the subject while another matches the body.
To require a phrase in one field, quote it:

```json
{"query":"\"existing and prepaid credits\""}
```

Quote addresses and punctuation-bearing strings too:

```json
{"query":"\"person@example.com\"","search_fields":["sender"]}
```

Select `"search_fields":["body"]` for body-only matching. `fuzzy_distance: 1`
helps with a typo in one ASCII word of 4–40 letters/digits; distance two is more
expensive and can hit a limit. Fuzzy spelling is not conceptual/semantic search.
Boolean operators, `sender:` syntax, unquoted addresses and `word*` are not part
of this query language. Use ordinary tokens, quoted phrases and field selection.

Translate relative dates using the user's timezone; pass explicit offsets.
`since` includes its instant; `before` excludes it. Omitted dates mean all local
history. Results are newest-first. For another page, retain the same query and
filters and pass `next_offset` plus the previous `snapshot`. If it becomes stale,
start again at offset zero. Physical copies in different folders stay distinct.

## Understand coverage

`matched_fields` and excerpts show evidence actually checked. An email already
proved by headers does not need its body read, so its body may not be listed as a
matching field. `header_matches` counts those positives; `searched_bodies` counts
actual MIME reads. Excerpts use normalized/casefolded text.

Inspect `partial_bodies`, `unavailable_bodies`, `unsearched_candidates` and
`error_counts`. `execution_complete` means the selected work finished, while
`exhaustive` remains false. A negative over missing/partial/index-omitted text
cannot prove an email does not exist. Narrow the date/account scope or read a
known candidate when coverage matters. Body scopes of at most 500 unresolved
messages bypass Spotlight; larger ones require the verified native index profile.
Archive search can be slower than recent mail.

`mail_search_headers` and metadata listing are specialized public Mail tools for
explicit account/folder/date scopes. Optional `mail_search_legacy` is a separate
maintained FTS cache with different semantics; it is hidden in a normal install.
Do not silently switch to it or merge its results as if coverage were identical.

## Writes

A new install is read-only. With the explicit executors enabled, asking for a
send or event creation prepares an exact native review by default. Read the
recipient/calendar/payload before approving. The owner can deliberately delegate
server approval through local configuration. Calendar invitations are excluded.
See [installation](../INSTALL.md#enable-sending-or-calendar-creation) and the
[approval policy](TECHNICAL_DETAILS.md#approval-and-writes).
