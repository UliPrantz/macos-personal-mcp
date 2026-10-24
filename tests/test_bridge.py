import json
import shutil
from pathlib import Path

from pydantic import JsonValue

from macos_personal_mcp.models import Failure, Message, MessagePage
from macos_personal_mcp.process import run_child

ROOT = Path(__file__).resolve().parents[1]


async def fixture_call(
    scenario: str, operation: str, payload: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    node = shutil.which("node")
    assert node is not None, "Node is required only for the synthetic fixed-bridge test harness"
    raw = await run_child(
        [
            node,
            str(ROOT / "tests" / "bridge_fixture.cjs"),
            str(ROOT / "src" / "macos_personal_mcp" / "bridge.js"),
            scenario,
            operation,
            json.dumps(payload),
        ]
    )
    result: dict[str, JsonValue] = json.loads(raw)
    return result


def key(expected: str = "synthetic-id@example.test") -> dict[str, JsonValue]:
    return {
        "account_id": "synthetic",
        "mailbox_path": ["Inbox"],
        "local_id": 12,
        "expected_message_id": expected,
        "body_chars": 500,
    }


async def test_identity_mismatch_prevents_body_or_header_read() -> None:
    result = await fixture_call("normal", "mail_get_message", key("different@example.test"))
    assert Failure.model_validate_json(json.dumps(result["result"])).code == "message_identity"
    assert result["counters"] == {"body": 0, "headers": 0}


async def test_unread_preservation_truncation_and_non_ascii_body() -> None:
    result = await fixture_call("normal", "mail_get_message", key())
    message = Message.model_validate_json(json.dumps(result["result"]))
    assert message.read_before is False and message.read_after is False
    assert message.body_truncated and message.body_characters > 10000
    assert "café 🐈" in message.body


async def test_observed_flag_change_is_error_with_no_restoration() -> None:
    result = await fixture_call("flags-changed", "mail_get_message", key())
    assert "read state change" in str(result.get("error"))
    assert "result" not in result


async def test_header_negative_query_is_empty_without_body_reads() -> None:
    result = await fixture_call(
        "negative",
        "mail_search_headers",
        {
            "account_id": "synthetic",
            "mailbox_path": ["Inbox"],
            "query": "absent needle",
            "since": "2026-10-01T00:00:00+01:00",
            "before": "2026-10-23T00:00:00+01:00",
            "unread_only": True,
            "offset": 0,
            "limit": 10,
        },
    )
    page = MessagePage.model_validate_json(json.dumps(result["result"]))
    assert page.total_matches == 0 and page.messages == [] and page.next_offset is None
    assert result["counters"] == {"body": 0, "headers": 0}
    filters = json.dumps(result["capturedFilter"])
    assert "_greaterThanEquals" in filters and "_lessThan" in filters
    assert "readStatus" in filters and "content" not in filters


async def test_complete_bulk_inventory_contains_all_identities_without_body_reads() -> None:
    result = await fixture_call(
        "normal",
        "mail_inventory",
        {
            "account_id": "synthetic",
            "mailbox_path": ["Inbox"],
            "since": "2026-10-01T00:00:00Z",
            "before": "2026-11-01T00:00:00Z",
            "query": "",
            "unread_only": False,
            "offset": 0,
            "limit": 1,
        },
    )
    page = MessagePage.model_validate_json(json.dumps(result["result"]))
    assert page.complete and page.total_matches == len(page.messages) == 1
    assert page.next_offset is None and result["counters"] == {"body": 0, "headers": 0}


async def test_raw_source_read_checks_identity_and_flags() -> None:
    from macos_personal_mcp.models import MessageSource

    mismatch = await fixture_call("normal", "mail_get_source", key("wrong@example.test"))
    assert mismatch["counters"] == {"body": 0, "headers": 0}
    assert Failure.model_validate_json(json.dumps(mismatch["result"])).code == "message_identity"
    raw = await fixture_call("normal", "mail_get_source", key())
    source = MessageSource.model_validate_json(json.dumps(raw["result"]))
    assert "Complete raw source body" in source.source
    assert source.read_before is False and source.read_after is False
    changed = await fixture_call("flags-changed", "mail_get_source", key())
    assert "error" in changed and "result" not in changed
