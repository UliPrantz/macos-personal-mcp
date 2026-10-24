# Exact native event opening

Date: 23 October 2026.

## Decision

Use a separately enabled `serve --enable-calendar-open` executor for a visible
Calendar `show` command. It creates nothing, sends nothing and changes no event
properties. It is not exposed or dispatched in read-only mode. Its annotation is
non-destructive and idempotent, but not read-only because it changes visible UI.

First resolve the exact current EventKit event and selected calendar using the
existing identity checks. Read its public
[`calendarItemIdentifier`](https://developer.apple.com/documentation/eventkit/ekcalendaritem/calendaritemidentifier),
which matched Calendar's scripting `uid` exactly in the live test. This identifier
differs from `eventIdentifier` and the server's `calendarItemExternalIdentifier`.
Resolve it afresh on every call; full sync can invalidate local identifiers.

Calendar's scripting calendar-ID getters fail on this Mac, and scripting event
selectors may resolve globally even under an invalid calendar container. Therefore
do not rely on the scripting calendar selector for containment. EventKit checks
the selected calendar first; the fixed scripting child then checks the exact
globally unique item UID, title, start/end instants, all-day flag, notes, location,
URL and absence of recurrence immediately before `show`. No name-only match,
generic app activation, guessed URL scheme or silent fallback is permitted.

Recurring occurrence opening is unavailable. A series UID alone does not prove
the requested occurrence would be displayed, so explicit occurrence selectors and
recurring/detached targets fail before any UI command. This restriction does not
change existing recurring occurrence reads.

## Evidence

Synthetic fixed-script tests verify the exact object reaches `show` once and
changed UID/date/notes or recurrence cause zero show commands. Service tests cover
both default-disabled dispatch and the independent read-only gate.

The live real-SDK STDIO client resolved the previously created controlled event
and Calendar acknowledged `show` for its exact validated item. No extra event or
invitation was created. A native command acknowledgment is distinct from human
observation of visible UI; STATUS.md records whether the owner confirmed display.
Private evidence remains in `.local/live-calendar-test/open-execution.json`.
