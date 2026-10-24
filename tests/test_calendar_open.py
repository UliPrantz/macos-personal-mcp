import json
import shutil
from pathlib import Path

import pytest
from pydantic import JsonValue

from macos_personal_mcp.calendar_open import NativeCalendarOpener
from macos_personal_mcp.models import CalendarKey, EventOpenResult, EventOpenTarget, Failure, Model
from macos_personal_mcp.process import NativeError, run_child
from macos_personal_mcp.service import Service

ROOT = Path(__file__).resolve().parents[1]


def target() -> EventOpenTarget:
    return EventOpenTarget.model_validate_json(
        json.dumps(
            {
                "calendar_item_id": "scripting-id",
                "event": {
                    "calendar_id": "synthetic-personal",
                    "uid": "native-event-id",
                    "title": "Synthetic selected event",
                    "start": "2026-10-24T09:00:00Z",
                    "end": "2026-10-24T09:05:00Z",
                    "all_day": False,
                    "location": "Synthetic location",
                    "notes": "Synthetic complete notes",
                    "url": "https://example.test/",
                    "recurrence": "",
                    "attendees": [],
                },
            }
        )
    )


async def fixture(scenario: str) -> dict[str, JsonValue]:
    node = shutil.which("node")
    assert node is not None
    raw = await run_child(
        [
            node,
            str(ROOT / "tests/calendar_open_fixture.cjs"),
            str(ROOT / "src/macos_personal_mcp/calendar_open.js"),
            scenario,
            target().model_dump_json(),
        ]
    )
    value: dict[str, JsonValue] = json.loads(raw)
    return value


async def test_native_show_receives_exact_validated_public_item() -> None:
    result = await fixture("normal")
    assert result["result"] == {"calendar_item_id": "scripting-id", "show_acknowledged": True}
    assert result["counters"] == {"shows": 1}
    assert result["captured"] == {"calendar_id": "synthetic-personal", "item_id": "scripting-id"}


@pytest.mark.parametrize("scenario", ["wrong-uid", "changed-date", "changed-notes", "recurring"])
async def test_changed_or_unsupported_target_cannot_show(scenario: str) -> None:
    result = await fixture(scenario)
    assert "error" in result and result["counters"] == {"shows": 0}


class TargetFixture:
    async def call[T: Model](self, operation: str, request: Model, output: type[T]) -> T:
        assert operation == "calendar_open_target"
        return output.model_validate_json(target().model_dump_json())


async def test_wrong_selected_calendar_fails_before_any_ui_dispatch() -> None:
    with pytest.raises(NativeError, match="identity does not match"):
        await NativeCalendarOpener(TargetFixture()).open(
            CalendarKey(calendar_id="different-calendar", event_uid="native-event-id")
        )


class OpenerFixture:
    def __init__(self) -> None:
        self.calls = 0

    async def open(self, key: CalendarKey) -> EventOpenResult:
        self.calls += 1
        return EventOpenResult(event=target().event)


async def test_ui_effect_requires_explicit_enablement_and_is_never_read_only() -> None:
    key = CalendarKey(calendar_id="synthetic-personal", event_uid="native-event-id")
    opener = OpenerFixture()
    readonly = await Service(calendar_opener=opener).call(
        "calendar_open_event", key.model_dump_json()
    )
    disabled = await Service(read_only=False).call("calendar_open_event", key.model_dump_json())
    assert isinstance(readonly, Failure) and readonly.code == "read_only"
    assert isinstance(disabled, Failure) and disabled.code == "open_disabled"
    assert opener.calls == 0
    enabled = Service(read_only=False, calendar_opener=opener)
    opened = await enabled.call("calendar_open_event", key.model_dump_json())
    assert isinstance(opened, EventOpenResult) and opened.show_acknowledged
    annotation = next(t for t in enabled.tools() if t.name == "calendar_open_event").annotations
    assert (
        annotation is not None
        and not annotation.read_only_hint
        and not annotation.destructive_hint
        and annotation.idempotent_hint
    )
