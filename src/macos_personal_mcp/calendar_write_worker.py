"""Public EventKit save in a disposable child; no private setters or attendees."""

import sys

import EventKit as EK
from Foundation import NSURL, NSDate, NSTimeZone

from macos_personal_mcp.models import Failure, NativeReply
from macos_personal_mcp.native_worker import calendar_model, event_model, require_calendar_read
from macos_personal_mcp.process import NativeError
from macos_personal_mcp.safety import EventPreview


def create(preview: EventPreview) -> str:
    require_calendar_read(EK.EKEventStore.authorizationStatusForEntityType_(0))
    store = EK.EKEventStore.alloc().init()
    matches = [
        c for c in store.calendarsForEntityType_(0) if c.calendarIdentifier() == preview.calendar.id
    ]
    if (
        len(matches) != 1
        or calendar_model(matches[0]) != preview.calendar
        or not matches[0].allowsContentModifications()
    ):
        raise NativeError(
            "calendar_changed", "Exact reviewed calendar/source is no longer available or writable"
        )
    request = preview.payload
    start, end = request.instants()
    zone = NSTimeZone.timeZoneWithName_(request.timezone)
    if zone is None:
        raise NativeError("timezone", "Native timezone is unavailable")
    event = EK.EKEvent.eventWithEventStore_(store)
    event.setCalendar_(matches[0])
    event.setTitle_(request.title)
    event.setStartDate_(NSDate.dateWithTimeIntervalSince1970_(start.timestamp()))
    event.setEndDate_(NSDate.dateWithTimeIntervalSince1970_(end.timestamp()))
    event.setTimeZone_(zone)
    event.setAllDay_(request.all_day_start is not None)
    event.setLocation_(request.location)
    event.setNotes_(request.notes)
    if request.url:
        url = NSURL.URLWithString_(request.url)
        if url is None:
            raise NativeError("url", "Event URL is invalid")
        event.setURL_(url)
    success, error = store.saveEvent_span_commit_error_(event, EK.EKSpanThisEvent, True, None)
    if not success or error is not None:
        raise NativeError("calendar_save", "Native save did not return a successful acknowledgment")
    return event_model(event).model_dump_json()


def main() -> None:
    try:
        raw = sys.stdin.buffer.read(1_000_001)
        if len(raw) > 1_000_000:
            raise NativeError("input_limit", "Calendar payload exceeds bound")
        reply = NativeReply(result_json=create(EventPreview.model_validate_json(raw)))
    except Exception:
        # Parent has already journaled dispatch intent; it reports uncertainty if
        # failure occurred after a native save, rather than claiming zero effects.
        reply = NativeReply(
            failure=Failure(
                code="calendar_native_failure",
                message="Native calendar write did not yield a verified event",
            )
        )
    print(reply.model_dump_json())


if __name__ == "__main__":
    main()
