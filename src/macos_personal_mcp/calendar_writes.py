"""Policy-reviewed native creation in one exact writable calendar; never invites."""

import asyncio
import sys
from pathlib import Path
from typing import Protocol

from macos_personal_mcp.approval import reviewer_for
from macos_personal_mcp.models import Calendar, Calendars, Empty, Event, NativeReply
from macos_personal_mcp.native import Bridge
from macos_personal_mcp.permissions import ApprovalMode
from macos_personal_mcp.process import NativeError, run_child
from macos_personal_mcp.safety import EventCreate, EventPreview, preview_event
from macos_personal_mcp.sending import OutcomeJournal, OutcomeStatus, SendOutcome


class EventOutcome(SendOutcome):
    event: Event | None = None


class EventReviewer(Protocol):
    async def approve(self, preview: EventPreview) -> bool: ...


class EventDispatcher(Protocol):
    async def create(self, preview: EventPreview) -> Event: ...


class NativeEventDispatcher:
    async def create(self, preview: EventPreview) -> Event:
        raw = await run_child(
            [sys.executable, "-m", "macos_personal_mcp.calendar_write_worker"],
            preview.model_dump_json().encode(),
        )
        reply = NativeReply.model_validate_json(raw)
        if reply.failure is not None:
            raise NativeError(reply.failure.code, reply.failure.message)
        if reply.result_json is None:
            raise NativeError("calendar_result", "Native event outcome unavailable")
        return Event.model_validate_json(reply.result_json)


class CalendarExecutor:
    def __init__(
        self,
        journal: OutcomeJournal,
        bridge: Bridge,
        reviewer: EventReviewer,
        dispatcher: EventDispatcher,
        *,
        approval_mode: ApprovalMode = "native",
    ) -> None:
        self.approval_mode: ApprovalMode = approval_mode
        self.journal, self.bridge, self.reviewer, self.dispatcher = (
            journal,
            bridge,
            reviewer,
            dispatcher,
        )

    async def selected(self, identifier: str) -> Calendar:
        calendars = await self.bridge.call("calendar_list_calendars", Empty(), Calendars)
        matches = [c for c in calendars.calendars if c.id == identifier]
        if len(matches) != 1:
            raise NativeError(
                "calendar_not_found", "Exact selected calendar is absent or ambiguous; no fallback"
            )
        return matches[0]

    async def create(self, request: EventCreate) -> EventOutcome:
        preview = preview_event(request, await self.selected(request.calendar_id))
        previous = self.journal.reserve(preview)
        if previous is not None:
            return EventOutcome.model_validate(previous.model_dump())
        dispatched = False
        status: OutcomeStatus = "not_dispatched"
        detail = "No calendar write dispatched"
        event: Event | None = None
        try:
            if not await self.reviewer.approve(preview):
                status, detail = "approval_denied", "Human declined; no calendar write dispatched"
            else:
                current = preview_event(request, await self.selected(request.calendar_id))
                if current.digest != preview.digest:
                    raise NativeError(
                        "calendar_changed", "Calendar selection/source changed after review"
                    )
                self.journal.update(preview, "dispatch_started")
                dispatched = True
                event = await self.dispatcher.create(preview)
                start, end = request.instants()
                if (
                    event.calendar_id != request.calendar_id
                    or event.title != request.title
                    or event.start != start
                    or event.end != end
                    or event.all_day != (request.all_day_start is not None)
                    or event.all_day_start != request.all_day_start
                    or event.all_day_end_exclusive != request.all_day_end_exclusive
                    or event.timezone_name != request.timezone
                    or event.location != request.location
                    or event.notes != request.notes
                    or event.url != request.url
                    or event.attendees
                ):
                    raise NativeError(
                        "calendar_result", "Saved event differs from the prepared payload"
                    )
                status, detail = (
                    "accepted",
                    "EventKit saved the prepared event in the selected calendar; provider synchronization is outside this acknowledgment",
                )
        except asyncio.CancelledError:
            self.journal.update(preview, "outcome_unknown" if dispatched else "not_dispatched")
            raise
        except Exception:
            status = "outcome_unknown" if dispatched else "not_dispatched"
            detail = (
                "Calendar write attempted; outcome unknown. Do not retry"
                if dispatched
                else "Review or calendar validation failed; no calendar write dispatched"
            )
            event = None
        try:
            self.journal.update(preview, status)
        except Exception:
            if dispatched:
                status, detail = (
                    "outcome_unknown",
                    "Calendar write attempted; final outcome persistence failed. Do not retry",
                )
        return EventOutcome(
            operation_id=request.operation_id,
            digest=preview.digest,
            status=status,
            external_effects_dispatched=dispatched,
            detail=detail,
            approval_mode=self.approval_mode,
            event=event,
        )


def native_calendar_executor(bridge: Bridge, mode: ApprovalMode = "native") -> CalendarExecutor:
    root = Path.home() / "Library/Application Support/macos-personal-mcp"
    return CalendarExecutor(
        OutcomeJournal(root),
        bridge,
        reviewer_for(mode),
        NativeEventDispatcher(),
        approval_mode=mode,
    )
