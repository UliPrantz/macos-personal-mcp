"""A public Calendar show command tied to an exact current EventKit item identity."""

from importlib.resources import files
from typing import Protocol

from macos_personal_mcp.models import CalendarKey, EventOpenResult, EventOpenTarget, Model
from macos_personal_mcp.native import Bridge
from macos_personal_mcp.process import NativeError, run_child


class ShowAcknowledgment(Model):
    calendar_item_id: str
    show_acknowledged: bool


class CalendarOpener(Protocol):
    async def open(self, key: CalendarKey) -> EventOpenResult: ...


class NativeCalendarOpener:
    def __init__(self, bridge: Bridge) -> None:
        self.bridge = bridge

    async def open(self, key: CalendarKey) -> EventOpenResult:
        target = await self.bridge.call("calendar_open_target", key, EventOpenTarget)
        if target.event.calendar_id != key.calendar_id or target.event.uid != key.event_uid:
            raise NativeError("event_identity", "Selected calendar/event identity does not match")
        if target.event.recurring or key.occurrence_start is not None:
            raise NativeError(
                "occurrence_open_unavailable",
                "Exact recurring occurrence opening is not verified; no UI command dispatched",
            )
        script = str(files("macos_personal_mcp").joinpath("calendar_open.js"))
        raw = await run_child(
            ["/usr/bin/osascript", "-l", "JavaScript", script], target.model_dump_json().encode()
        )
        result = ShowAcknowledgment.model_validate_json(raw)
        if not result.show_acknowledged or result.calendar_item_id != target.calendar_item_id:
            raise NativeError(
                "open_unconfirmed", "Native show did not acknowledge the exact selected item"
            )
        return EventOpenResult(event=target.event)
