# Reviewed Calendar creation

Date: 23 October 2026.

The earlier read-only desktop registration choice below is superseded by
[decision 0009](0009-guarded-native-desktop-profile.md). The independent native
approval and outcome-safety requirements remain unchanged.

The mandatory-native-only approval policy below is superseded by
[decision 0010](0010-owner-configurable-server-approval.md): the owner can
explicitly delegate server review to the host/model. Native remains the default.

## Decision

Add an independently enabled `serve --enable-calendar-create` executor using
public EventKit setters and `saveEvent:span:commit:error:` in a bounded disposable
Python child. Default desktop discovery and dispatch remain read-only.
`--enable-writes` alone exposes schemas but cannot execute them. Mail and Calendar
execution flags can be combined; either conflicts with `--read-only`.

Creation accepts aware timed instants or ordered all-day civil dates with an
exclusive end, plus an explicit IANA timezone, title, location, notes and optional
URL. Reject mixed/partial dates, naive instants, invalid zones and attendee or
model-approval fields. All-day boundaries use local midnight independently across
DST; a nonexistent local date boundary is rejected.

Resolve exactly one calendar by its persistent ID. Require writability and reject
subscribed/immutable calendars without a fallback. Human review shows the exact
calendar/source/ID, all content, dates/timezone, no attendees, operation ID and
digest. Shared or synchronizing calendar effects are stated explicitly. Re-read
the calendar/source after review and again inside the native worker; any change
fails closed. Cancel is the default Return-key action, and the UI expires after
three minutes. An inert diagnostic reviewer cannot authorize an executor.

Use the existing owner-only minimal outcome journal, with a calendar-specific
digest prefix. Persist dispatch intent before launching the write child. Verify
the saved event's calendar, content, timing, timezone, all-day dates and absence of
attendees. A successful native save acknowledges local EventKit persistence,
not provider sync or attendee delivery. An uncertain save/cancellation/crash is
never automatically retried; replay returns journal metadata without creating
another event. No event bodies or calendar identities enter the journal.

## Validation and limits

Synthetic tests cover denial/timeout, exact-calendar absence/ambiguity,
read-only/subscribed/immutable targets, changed source after review, durable
replay, cancellation and uncertain/wrong saved results. A London all-day event
crossing the October DST change spans 25 elapsed hours while preserving one civil
day and an exclusive end date. These tests do not touch native owner data.

The controlled live test uses an owner-selected personal calendar, explicitly
excluding a separately named board calendar, and no attendees. Its exact payload
and result remain private; STATUS.md records the measured outcome. All-day
creation is synthetically checked, not a separate live-write claim. Cleanup is
not included in creation authorization.

Exact-event opening is a separate UI effect, subsequently implemented for
nonrecurring targets using public item identity; see
[decision 0007](0007-exact-native-event-opening.md). Invitations remain
unavailable: [EventKit cannot add participants](https://developer.apple.com/documentation/eventkit/ekparticipant),
and Calendar's installed scripting attendee properties are read-only. This
creation feature provides no provider fallback, ICS substitution or invitation
path. The owner subsequently excluded attendee creation and direct provider
integrations entirely; see [decision 0008](0008-native-only-scope-without-invitations.md).
No provider authentication or adapter is now pending.
