"""Public PyObjC reads and explicit access setup in a bounded disposable process."""

import sys
from datetime import UTC, date, datetime, timedelta
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo

import Contacts as CN
import EventKit as EK
from Foundation import NSDate, NSTimeZone

from macos_personal_mcp.access import permission_problem
from macos_personal_mcp.models import (
    Attendee,
    Calendar,
    CalendarKey,
    Calendars,
    CalendarScope,
    Contact,
    ContactKey,
    Contacts,
    ContactsBackend,
    ContactsScope,
    Event,
    EventOpenTarget,
    Events,
    Failure,
    LabeledValue,
    Model,
    NativeReply,
    Page,
    PermissionRequest,
    PostalAddress,
)
from macos_personal_mcp.native_access import (
    calendar_status,
    contacts_status,
    native_permissions,
    request_access,
)
from macos_personal_mcp.process import NativeError

MAX_CONTACTS = 50_000
MAX_EVENTS = 5_000


def require_calendar_read(status: int) -> None:
    if status != EK.EKAuthorizationStatusFullAccess:
        raise NativeError(
            "calendar_permission",
            "Full Calendar read access is not granted to this process. "
            + permission_problem("calendar", calendar_status(status)),
        )


def native_date(value: NSDate) -> datetime:
    return datetime.fromtimestamp(value.timeIntervalSince1970(), UTC)


def local_dates(start: datetime, end: datetime, timezone_name: str) -> tuple[date, date]:
    zone = ZoneInfo(timezone_name)
    return start.astimezone(zone).date(), end.astimezone(zone).date()


def selected_page[T: Model](rows: list[T], request: Page) -> tuple[list[T], int | None]:
    end = request.offset + request.limit
    return rows[request.offset : end], end if end < len(rows) else None


def contact_keys() -> list[str]:
    return [
        CN.CNContactIdentifierKey,
        CN.CNContactGivenNameKey,
        CN.CNContactMiddleNameKey,
        CN.CNContactFamilyNameKey,
        CN.CNContactOrganizationNameKey,
        CN.CNContactJobTitleKey,
        CN.CNContactEmailAddressesKey,
        CN.CNContactPhoneNumbersKey,
        CN.CNContactPostalAddressesKey,
    ]


def contact_model(value: CN.CNContact) -> Contact:
    first, middle, last = value.givenName(), value.middleName(), value.familyName()
    organization = value.organizationName()
    addresses: list[PostalAddress] = []
    for labeled in value.postalAddresses():
        address = labeled.value()
        addresses.append(
            PostalAddress(
                label=labeled.label() or "",
                street=address.street(),
                city=address.city(),
                state=address.state(),
                postal_code=address.postalCode(),
                country=address.country(),
                country_code=address.ISOCountryCode(),
            )
        )
    return Contact(
        id=value.identifier(),
        name=" ".join(part for part in [first, middle, last] if part) or organization,
        first_name=first,
        middle_name=middle,
        last_name=last,
        organization=organization,
        job_title=value.jobTitle(),
        emails=[
            LabeledValue(label=v.label() or "", value=v.value()) for v in value.emailAddresses()
        ],
        phones=[
            LabeledValue(label=v.label() or "", value=v.value().stringValue())
            for v in value.phoneNumbers()
        ],
        postal_addresses=addresses,
    )


def read_contacts(operation: str, payload: str) -> Model:
    status = CN.CNContactStore.authorizationStatusForEntityType_(0)
    if status not in {CN.CNAuthorizationStatusAuthorized, CN.CNAuthorizationStatusLimited}:
        raise NativeError(
            "contacts_permission",
            "Contacts read access is not granted to this process. "
            + permission_problem("contacts", contacts_status(status)),
        )
    store = CN.CNContactStore.alloc().init()
    if operation == "contacts_get":
        key = ContactKey.model_validate_json(payload)
        contact, error = store.unifiedContactWithIdentifier_keysToFetch_error_(
            key.contact_id, contact_keys(), None
        )
        if error is not None or contact is None:
            raise NativeError(
                "contact_not_found", "Exact contact is unavailable in the granted scope"
            )
        return contact_model(contact)
    if operation not in {"contacts_list", "contacts_search"}:
        raise NativeError("unknown_operation", "Unknown Contacts operation")
    request = ContactsScope.model_validate_json(payload)
    fetch = CN.CNContactFetchRequest.alloc().initWithKeysToFetch_(contact_keys())
    fetch.setUnifyResults_(True)
    rows: list[Contact] = []
    over_limit = False

    def receive(contact: CN.CNContact, stop: object) -> None:
        nonlocal over_limit
        if len(rows) >= MAX_CONTACTS:
            over_limit = True
            return
        rows.append(contact_model(contact))

    success, error = store.enumerateContactsWithFetchRequest_error_usingBlock_(fetch, None, receive)
    if not success or error is not None:
        raise NativeError("contacts_read_failed", "Contacts enumeration failed; no complete result")
    if over_limit:
        raise NativeError(
            "candidate_limit", "Visible Contacts exceed the bounded enumeration limit"
        )
    needle = request.query.casefold()
    if needle:
        rows = [
            c
            for c in rows
            if any(
                needle in v.casefold()
                for v in [
                    c.name,
                    c.organization,
                    *[e.value for e in c.emails],
                    *[p.value for p in c.phones],
                ]
            )
        ]
    rows.sort(key=lambda c: (c.name.casefold(), c.id))
    page, next_offset = selected_page(rows, request)
    return Contacts(
        contacts=page,
        total_matches=len(rows),
        next_offset=next_offset,
        complete=status == CN.CNAuthorizationStatusAuthorized,
        coverage="Contacts exposed by CNContactStore at this enumeration; limited access"
        if status == CN.CNAuthorizationStatusLimited
        else "All contacts exposed by CNContactStore at this enumeration; provider synchronization is outside this scope",
    )


def calendar_model(value: EK.EKCalendar) -> Calendar:
    source = value.source()
    return Calendar(
        id=value.calendarIdentifier(),
        name=value.title(),
        writable=value.allowsContentModifications(),
        source_id=source.sourceIdentifier(),
        source_name=source.title(),
        source_type=source.sourceType(),
        calendar_type=value.type(),
        subscribed=value.isSubscribed(),
        immutable=value.isImmutable(),
    )


def event_model(value: EK.EKEvent) -> Event:
    identifier = value.eventIdentifier()
    if not identifier:
        raise NativeError(
            "event_identity", "EventKit returned an event without a selectable identity"
        )
    zone = value.timeZone()
    zone_name = zone.name() if zone is not None else NSTimeZone.localTimeZone().name()
    start, end = native_date(value.startDate()), native_date(value.endDate())
    all_day = value.isAllDay()
    all_start, all_end = local_dates(start, end, zone_name)
    url = value.URL()
    attendees: list[Attendee] = []
    for participant in value.attendees() or []:
        participant_url = participant.URL().absoluteString()
        parsed = urlsplit(participant_url)
        attendees.append(
            Attendee(
                name=participant.name() or "",
                email=unquote(parsed.path) if parsed.scheme.lower() == "mailto" else "",
                status=str(participant.participantStatus()),
                url=participant_url,
                role=participant.participantRole(),
            )
        )
    recurring = bool(value.recurrenceRules()) or value.isDetached()
    return Event(
        calendar_id=value.calendar().calendarIdentifier(),
        uid=identifier,
        title=value.title() or "",
        start=start,
        end=end,
        all_day=all_day,
        location=value.location() or "",
        notes=value.notes() or "",
        url=url.absoluteString() if url is not None else "",
        recurrence="EventKit occurrence expansion" if recurring else "",
        attendees=attendees,
        external_id=value.calendarItemExternalIdentifier(),
        timezone_name=zone_name,
        timezone_source="native" if zone is not None else "system_floating",
        recurring=recurring,
        all_day_start=all_start if all_day else None,
        all_day_end_exclusive=all_end if all_day else None,
    )


def read_calendar(operation: str, payload: str) -> Model:
    require_calendar_read(EK.EKEventStore.authorizationStatusForEntityType_(0))
    store = EK.EKEventStore.alloc().init()
    calendars = list(store.calendarsForEntityType_(0))
    if operation == "calendar_list_calendars":
        return Calendars(calendars=[calendar_model(c) for c in calendars])
    if operation in {"calendar_get_event", "calendar_open_target"}:
        key = CalendarKey.model_validate_json(payload)
        if operation == "calendar_open_target" and key.occurrence_start is not None:
            raise NativeError(
                "occurrence_open_unavailable",
                "Exact recurring occurrence opening is not verified; no UI command dispatched",
            )
        selected = [c for c in calendars if c.calendarIdentifier() == key.calendar_id]
        if len(selected) != 1:
            raise NativeError(
                "calendar_not_found", "Selected calendar is absent or ambiguous; no fallback"
            )
        if key.occurrence_start is not None:
            before = NSDate.dateWithTimeIntervalSince1970_(key.occurrence_start.timestamp())
            after = NSDate.dateWithTimeIntervalSince1970_(
                (key.occurrence_start + timedelta(seconds=1)).timestamp()
            )
            predicate = store.predicateForEventsWithStartDate_endDate_calendars_(
                before, after, selected
            )
            matches = [
                e
                for e in store.eventsMatchingPredicate_(predicate)
                if e.eventIdentifier() == key.event_uid
                and native_date(e.startDate()) == key.occurrence_start
            ]
            if len(matches) != 1:
                raise NativeError("event_identity", "Exact event occurrence is absent or ambiguous")
            return event_model(matches[0])
        event = store.eventWithIdentifier_(key.event_uid)
        if event is None or event.calendar().calendarIdentifier() != key.calendar_id:
            raise NativeError("event_not_found", "Exact event is absent from the selected calendar")
        if event.recurrenceRules() or event.isDetached():
            raise NativeError(
                "occurrence_required",
                "Recurring event reads require occurrence_start from the listed row",
            )
        if operation == "calendar_open_target":
            return EventOpenTarget(
                event=event_model(event), calendar_item_id=event.calendarItemIdentifier()
            )
        return event_model(event)
    if operation not in {"calendar_list_events", "calendar_search_events"}:
        raise NativeError("unknown_operation", "Unknown Calendar operation")
    request = CalendarScope.model_validate_json(payload)
    selected = [c for c in calendars if c.calendarIdentifier() in request.calendar_ids]
    if len(selected) != len(request.calendar_ids):
        raise NativeError("calendar_not_found", "A selected calendar is absent; no fallback")
    since = NSDate.dateWithTimeIntervalSince1970_(request.since.timestamp())
    before = NSDate.dateWithTimeIntervalSince1970_(request.before.timestamp())
    native_events = store.eventsMatchingPredicate_(
        store.predicateForEventsWithStartDate_endDate_calendars_(since, before, selected)
    )
    if len(native_events) > MAX_EVENTS:
        raise NativeError("candidate_limit", "Too many occurrences; narrow the calendar/date scope")
    rows = [event_model(e) for e in native_events]
    needle = request.query.casefold()
    rows = [
        e
        for e in rows
        if e.start < request.before
        and e.end > request.since
        and any(needle in text.casefold() for text in [e.title, e.notes, e.location])
    ]
    rows.sort(key=lambda e: (e.start, e.calendar_id, e.uid))
    page, next_offset = selected_page(rows, request)
    return Events(events=page, total_matches=len(rows), next_offset=next_offset, complete=True)


def main() -> None:
    try:
        operation = sys.argv[1]
        backend: ContactsBackend = "framework"
        if len(sys.argv) > 2:
            if sys.argv[2] not in {"framework", "contacts-app"}:
                raise NativeError("contacts_backend", "Unknown startup Contacts backend")
            backend = "contacts-app" if sys.argv[2] == "contacts-app" else "framework"
        payload = sys.stdin.buffer.read(2_000_001).decode()
        if len(payload) > 2_000_000:
            raise NativeError("input_limit", "Native worker input exceeds its bound")
        if operation == "permissions":
            result: Model = native_permissions()
            if backend == "contacts-app":
                from macos_personal_mcp.native_contacts_app import automation_status

                try:
                    contacts_authorization = automation_status()
                except NativeError, OSError:
                    contacts_authorization = "unknown"
                result = result.model_copy(
                    update={"contacts": contacts_authorization, "contacts_backend": backend}
                )
        elif operation == "request_permissions":
            request = PermissionRequest.model_validate_json(payload)
            if request.domain == "contacts" and backend == "contacts-app":
                from macos_personal_mcp.native_contacts_app import request_automation_access

                result = request_automation_access()
            else:
                result = request_access(request)
        elif operation.startswith("calendar_"):
            result = read_calendar(operation, payload)
        elif operation.startswith("contacts_"):
            if backend == "contacts-app":
                from macos_personal_mcp.native_contacts_app import (
                    read_contacts as read_scripted_contacts,
                )

                result = read_scripted_contacts(operation, payload)
            else:
                result = read_contacts(operation, payload)
        else:
            raise NativeError("unknown_operation", "Unknown native worker operation")
        reply = NativeReply(result_json=result.model_dump_json())
    except NativeError as error:
        reply = NativeReply(failure=Failure(code=error.code, message=error.detail))
    except Exception:
        # Do not echo native exceptions: fields and provider diagnostics can be private.
        reply = NativeReply(
            failure=Failure(
                code="native_failure", message="Public native operation failed; no complete result"
            )
        )
    print(reply.model_dump_json())


if __name__ == "__main__":
    main()
