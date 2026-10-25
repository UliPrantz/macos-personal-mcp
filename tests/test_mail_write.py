import json
import shutil
from pathlib import Path

import pytest
from pydantic import JsonValue

from macos_personal_mcp.process import run_child

ROOT = Path(__file__).resolve().parents[1]


async def dispatch_fixture(scenario: str) -> dict[str, JsonValue]:
    node = shutil.which("node")
    assert node is not None
    payload = {
        "sender": "sender@example.test",
        "to": ["one@example.test", "two@example.test"],
        "cc": ["cc@example.test"],
        "bcc": ["bcc@example.test"],
        "subject": "Synthetic",
        "body": "literal café 🐈 '); throw Error('injection')",
        "attachments": ["/synthetic/attachment.txt"],
    }
    raw = await run_child(
        [
            node,
            str(ROOT / "tests/mail_write_fixture.cjs"),
            str(ROOT / "src/macos_personal_mcp/mail_write.js"),
            scenario,
            json.dumps(payload),
        ]
    )
    result: dict[str, JsonValue] = json.loads(raw)
    return result


async def test_fixed_writer_preserves_literal_body_all_recipients_and_attachments() -> None:
    result = await dispatch_fixture("normal")
    assert result["result"] == {"accepted": True}
    assert result["counters"] == {"drafts": 1, "sends": 1}
    captured = result["captured"]
    assert isinstance(captured, dict)
    assert captured["bcc"] == ["bcc@example.test"]
    assert captured["to"] == ["one@example.test", "two@example.test"]
    assert captured["attachments"] == ["/synthetic/attachment.txt"]
    assert captured["content"] == "literal café 🐈 '); throw Error('injection')"


async def test_ambiguous_sender_cannot_even_create_a_draft() -> None:
    result = await dispatch_fixture("ambiguous")
    assert result["counters"] == {"drafts": 0, "sends": 0}


async def test_native_body_change_cannot_send_unreviewed_content() -> None:
    result = await dispatch_fixture("changed-content")
    assert result["counters"] == {"drafts": 1, "sends": 0}
    assert result["result"] == {"accepted": False, "failure_code": "native_message_changed"}


async def test_native_single_appended_space_can_send_reviewed_body() -> None:
    result = await dispatch_fixture("trailing-space")
    assert result["result"] == {"accepted": True}
    assert result["counters"] == {"drafts": 1, "sends": 1}


@pytest.mark.parametrize("scenario", ["two-spaces", "trailing-newline"])
async def test_other_whitespace_changes_do_not_pass_review(scenario: str) -> None:
    result = await dispatch_fixture(scenario)
    assert result["result"] == {"accepted": False, "failure_code": "native_message_changed"}
    assert result["counters"] == {"drafts": 1, "sends": 0}
