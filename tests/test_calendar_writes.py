import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from macos_personal_mcp.approval import NativeReviewer, review_text
from macos_personal_mcp.calendar_writes import CalendarExecutor
from macos_personal_mcp.models import Calendar, Calendars, Event, Failure, Model
from macos_personal_mcp.process import NativeError
from macos_personal_mcp.safety import EventCreate, EventPreview, preview_event
from macos_personal_mcp.sending import OutcomeJournal
from macos_personal_mcp.service import Service


def calendar() -> Calendar:
    return Calendar(
        id="personal",
        name="Personal",
        writable=True,
        source_id="account",
        source_name="Owner",
        subscribed=False,
        immutable=False,
    )


def request() -> EventCreate:
    return EventCreate.model_validate_json(
        json.dumps(
            {
                "operation_id": "synthetic_calendar_01",
                "calendar_id": "personal",
                "title": "Synthetic event",
                "start": "2026-10-24T10:00:00+01:00",
                "end": "2026-10-24T10:05:00+01:00",
                "notes": "Full synthetic notes",
                "location": "Synthetic location",
                "url": "https://example.test/event",
            }
        )
    )


class CalendarFixture:
    def __init__(self, values: list[Calendar] | None = None) -> None:
        self.values = values if values is not None else [calendar()]
        self.calls = 0

    async def call[T: Model](self, operation: str, request: Model, output: type[T]) -> T:
        assert operation == "calendar_list_calendars"
        self.calls += 1
        return output.model_validate_json(Calendars(calendars=self.values).model_dump_json())


class ReviewerFixture:
    def __init__(
        self, allow: bool, *, change: CalendarFixture | None = None, timeout: bool = False
    ) -> None:
        self.allow, self.change, self.timeout, self.calls = allow, change, timeout, 0

    async def approve(self, preview: EventPreview) -> bool:
        self.calls += 1
        if self.timeout:
            raise NativeError("deadline", "Synthetic human review timeout")
        if self.change is not None:
            self.change.values = [calendar().model_copy(update={"source_id": "different-account"})]
        return self.allow


class DispatcherFixture:
    def __init__(
        self, *, uncertain: bool = False, cancel: bool = False, wrong: bool = False
    ) -> None:
        self.calls, self.uncertain, self.cancel, self.wrong = 0, uncertain, cancel, wrong

    async def create(self, preview: EventPreview) -> Event:
        self.calls += 1
        if self.cancel:
            raise asyncio.CancelledError
        if self.uncertain:
            raise NativeError("deadline", "Synthetic uncertain save")
        payload = preview.payload
        start, end = payload.instants()
        return Event(
            calendar_id=payload.calendar_id,
            uid="native-synthetic-id",
            title=payload.title,
            start=start,
            end=end,
            all_day=payload.all_day_start is not None,
            all_day_start=payload.all_day_start,
            all_day_end_exclusive=payload.all_day_end_exclusive,
            timezone_name=payload.timezone,
            location=payload.location,
            notes=payload.notes,
            url=payload.url,
            recurrence="",
            attendees=[],
        ).model_copy(update={"all_day": True} if self.wrong else {})


@pytest.mark.parametrize("timeout", [False, True])
async def test_calendar_denial_and_timeout_never_dispatch(tmp_path: Path, timeout: bool) -> None:
    native, human, dispatch = (
        CalendarFixture(),
        ReviewerFixture(False, timeout=timeout),
        DispatcherFixture(),
    )
    journal = OutcomeJournal(tmp_path)
    result = await CalendarExecutor(journal, native, human, dispatch).create(request())
    assert result.status == ("not_dispatched" if timeout else "approval_denied")
    assert not result.external_effects_dispatched and dispatch.calls == 0
    repeat = await CalendarExecutor(journal, native, human, dispatch).create(request())
    assert repeat.replayed and human.calls == 1 and dispatch.calls == 0


@pytest.mark.parametrize(
    "values",
    [
        [],
        [calendar(), calendar()],
        [calendar().model_copy(update={"id": "other"})],
        [calendar().model_copy(update={"writable": False})],
        [calendar().model_copy(update={"subscribed": True})],
        [calendar().model_copy(update={"immutable": True})],
    ],
)
async def test_exact_calendar_required_without_fallback(
    tmp_path: Path, values: list[Calendar]
) -> None:
    human, dispatch = ReviewerFixture(True), DispatcherFixture()
    with pytest.raises(NativeError):
        await CalendarExecutor(
            OutcomeJournal(tmp_path), CalendarFixture(values), human, dispatch
        ).create(request())
    assert human.calls == dispatch.calls == 0


async def test_calendar_source_change_invalidates_review(tmp_path: Path) -> None:
    native, dispatch = CalendarFixture(), DispatcherFixture()
    human = ReviewerFixture(True, change=native)
    result = await CalendarExecutor(OutcomeJournal(tmp_path), native, human, dispatch).create(
        request()
    )
    assert result.status == "not_dispatched" and dispatch.calls == 0


async def test_saved_event_and_durable_replay(tmp_path: Path) -> None:
    native, human, dispatch = CalendarFixture(), ReviewerFixture(True), DispatcherFixture()
    journal = OutcomeJournal(tmp_path)
    result = await CalendarExecutor(journal, native, human, dispatch).create(request())
    assert result.status == "accepted" and result.event is not None
    assert result.event.title == request().title
    repeat = await CalendarExecutor(journal, native, human, dispatch).create(request())
    assert repeat.replayed and repeat.status == "accepted" and repeat.event is None
    assert human.calls == dispatch.calls == 1
    assert b"Full synthetic notes" not in journal.path.read_bytes()


@pytest.mark.parametrize("wrong", [False, True])
async def test_uncertain_or_changed_saved_payload_is_never_retried(
    tmp_path: Path, wrong: bool
) -> None:
    native, human = CalendarFixture(), ReviewerFixture(True)
    dispatch = DispatcherFixture(wrong=wrong, uncertain=not wrong)
    journal = OutcomeJournal(tmp_path)
    result = await CalendarExecutor(journal, native, human, dispatch).create(request())
    assert result.status == "outcome_unknown" and result.external_effects_dispatched
    repeat = await CalendarExecutor(journal, native, human, dispatch).create(request())
    assert repeat.replayed and repeat.status == "outcome_unknown" and dispatch.calls == 1


async def test_calendar_cancellation_keeps_no_retry_barrier(tmp_path: Path) -> None:
    native, human, dispatch = (
        CalendarFixture(),
        ReviewerFixture(True),
        DispatcherFixture(cancel=True),
    )
    journal = OutcomeJournal(tmp_path)
    with pytest.raises(asyncio.CancelledError):
        await CalendarExecutor(journal, native, human, dispatch).create(request())
    repeat = await CalendarExecutor(journal, native, human, dispatch).create(request())
    assert repeat.replayed and repeat.status == "outcome_unknown" and dispatch.calls == 1


def test_event_review_contains_concrete_calendar_and_payload() -> None:
    preview = preview_event(request(), calendar())
    text = review_text(preview)
    for value in [
        "Personal",
        "Owner",
        "personal",
        "Synthetic event",
        "10:00:00+01:00",
        "10:05:00+01:00",
        "Europe/London",
        "Attendees: none",
        "Full synthetic notes",
        "Synthetic location",
        "https://example.test/event",
        preview.digest,
    ]:
        assert value in text


@pytest.mark.parametrize(
    "change",
    [
        {"start": "2026-10-24T10:00:00"},
        {"end": "2026-10-23T10:00:00Z"},
        {"invitees": ["recipient@example.test"]},
        {"approved": True},
        {"timezone": "Invalid/Zone"},
        {"all_day_start": "2026-10-24"},
    ],
)
def test_event_rejects_invalid_time_and_unapproved_invitation_fields(
    change: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        EventCreate.model_validate_json(json.dumps({**request().model_dump(mode="json"), **change}))


async def test_all_day_civil_dates_cross_london_dst(tmp_path: Path) -> None:
    payload = EventCreate.model_validate_json(
        json.dumps(
            {
                "operation_id": "synthetic_all_day",
                "calendar_id": "personal",
                "title": "All day",
                "all_day_start": "2026-10-25",
                "all_day_end_exclusive": "2026-10-26",
            }
        )
    )
    start, end = payload.instants()
    assert (end.astimezone(UTC) - start.astimezone(UTC)).total_seconds() == 25 * 3600
    assert "2026-10-26 (exclusive end)" in review_text(preview_event(payload, calendar()))
    result = await CalendarExecutor(
        OutcomeJournal(tmp_path), CalendarFixture(), ReviewerFixture(True), DispatcherFixture()
    ).create(payload)
    assert result.status == "accepted" and result.event is not None and result.event.all_day


async def test_diagnostic_review_cannot_authorize_real_dispatch() -> None:
    with pytest.raises(NativeError, match="inert diagnostic"):
        await NativeReviewer(denial_test=True).approve(preview_event(request(), calendar()))


def test_folded_wall_clock_dates_are_ordered_by_instant() -> None:
    zone = ZoneInfo("Europe/London")
    payload = EventCreate(
        operation_id="synthetic_dst_fold",
        calendar_id="personal",
        title="DST fold",
        start=datetime(2026, 10, 25, 1, 30, tzinfo=zone, fold=0),
        end=datetime(2026, 10, 25, 1, 30, tzinfo=zone, fold=1),
    )
    start, end = payload.instants()
    assert (end.astimezone(UTC) - start.astimezone(UTC)).total_seconds() == 3600


def test_nonexistent_all_day_boundary_is_rejected() -> None:
    with pytest.raises(ValidationError):
        EventCreate.model_validate_json(
            json.dumps(
                {
                    "operation_id": "synthetic_skipped_date",
                    "calendar_id": "personal",
                    "title": "Skipped date",
                    "timezone": "Pacific/Apia",
                    "all_day_start": "2011-12-30",
                    "all_day_end_exclusive": "2011-12-31",
                }
            )
        )


async def test_creation_requires_explicit_executor_and_read_only_blocks_it(tmp_path: Path) -> None:
    native, human, dispatch = CalendarFixture(), ReviewerFixture(True), DispatcherFixture()
    executor = CalendarExecutor(OutcomeJournal(tmp_path), native, human, dispatch)
    read_only = await Service(bridge=native, calendar_executor=executor).call(
        "calendar_create_event", request().model_dump_json()
    )
    closed = await Service(read_only=False, bridge=native).call(
        "calendar_create_event", request().model_dump_json()
    )
    assert isinstance(read_only, Failure) and read_only.code == "read_only"
    assert isinstance(closed, Failure) and closed.code == "approval_unavailable"
    assert native.calls == human.calls == dispatch.calls == 0
