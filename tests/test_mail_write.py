import json
import shutil
from pathlib import Path

import pytest
from pydantic import JsonValue

from macos_personal_mcp.process import run_child

ROOT = Path(__file__).resolve().parents[1]


async def dispatch_fixture(scenario: str, *, reply: bool = False) -> dict[str, JsonValue]:
    node = shutil.which("node")
    assert node is not None
    payload: dict[str, JsonValue] = {
        "sender": "sender@example.test",
        "to": ["one@example.test", "two@example.test"],
        "cc": ["cc@example.test"],
        "bcc": ["bcc@example.test"],
        "subject": "Synthetic",
        "body": "literal café 🐈 '); throw Error('injection')",
        "attachments": ["/synthetic/attachment.txt"],
    }
    if reply:
        payload["reply_to_message"] = {
            "account_id": "account-1",
            "mailbox_path": ["Inbox"],
            "local_id": 123,
            "expected_message_id": "<original@example.test>",
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


async def test_writer_verifies_native_draft_body_all_recipients_and_attachments() -> None:
    result = await dispatch_fixture("normal")
    assert result["result"] == {"accepted": True}
    assert result["counters"] == {"drafts": 1, "sends": 1, "replies": 0}
    captured = result["captured"]
    assert isinstance(captured, dict)
    assert captured["bcc"] == ["bcc@example.test"]
    assert captured["to"] == ["one@example.test", "two@example.test"]
    assert captured["attachments"] == ["/synthetic/attachment.txt"]
    assert captured["content"] == "literal café 🐈 '); throw Error('injection')"


async def test_ambiguous_sender_cannot_even_create_a_draft() -> None:
    result = await dispatch_fixture("ambiguous")
    assert result["counters"] == {"drafts": 0, "sends": 0, "replies": 0}


async def test_native_body_change_cannot_send_unreviewed_content() -> None:
    result = await dispatch_fixture("changed-content")
    assert result["counters"] == {"drafts": 1, "sends": 0, "replies": 0}
    assert result["result"] == {"accepted": False, "failure_code": "native_message_changed"}


async def test_native_single_appended_space_can_send_reviewed_body() -> None:
    result = await dispatch_fixture("trailing-space")
    assert result["result"] == {"accepted": True}
    assert result["counters"] == {"drafts": 1, "sends": 1, "replies": 0}


@pytest.mark.parametrize("scenario", ["two-spaces", "trailing-newline", "leading-newline"])
async def test_other_whitespace_changes_do_not_pass_review(scenario: str) -> None:
    result = await dispatch_fixture(scenario)
    assert result["result"] == {"accepted": False, "failure_code": "native_message_changed"}
    assert result["counters"] == {"drafts": 1, "sends": 0, "replies": 0}


async def test_native_reply_replaces_all_inherited_recipients_and_body() -> None:
    result = await dispatch_fixture("normal", reply=True)
    assert result["result"] == {"accepted": True}
    assert result["counters"] == {"drafts": 1, "sends": 1, "replies": 1}
    captured = result["captured"]
    assert isinstance(captured, dict)
    assert captured["to"] == ["one@example.test", "two@example.test"]
    assert captured["cc"] == ["cc@example.test"]
    assert captured["bcc"] == ["bcc@example.test"]
    assert captured["content"] == "literal café 🐈 '); throw Error('injection')"


@pytest.mark.parametrize("scenario", ["stale-reply", "changed-reply"])
async def test_native_reply_identity_checked_before_and_after_creation(scenario: str) -> None:
    result = await dispatch_fixture(scenario, reply=True)
    assert result["result"] == {"accepted": False, "failure_code": "native_reply_identity"}
    counters = result["counters"]
    assert isinstance(counters, dict)
    assert counters["sends"] == 0
    assert counters["replies"] == (0 if scenario == "stale-reply" else 1)


async def test_native_reply_body_mismatch_prevents_send() -> None:
    result = await dispatch_fixture("changed-content", reply=True)
    assert result["result"] == {"accepted": False, "failure_code": "native_message_changed"}


async def test_native_reply_keeps_single_trailing_space_send_fix() -> None:
    result = await dispatch_fixture("trailing-space", reply=True)
    assert result["result"] == {"accepted": True}


async def test_native_reply_accepts_mails_null_empty_attachment_collection() -> None:
    result = await dispatch_fixture("null-attachments", reply=True)
    assert result["result"] == {"accepted": True}


@pytest.mark.parametrize("scenario", ["missing-account", "missing-mailbox"])
async def test_native_reply_never_falls_back_to_another_scope(scenario: str) -> None:
    result = await dispatch_fixture(scenario, reply=True)
    assert result["counters"] == {"drafts": 0, "sends": 0, "replies": 0}
    assert "error" in result


async def test_native_reply_inherited_attachment_prevents_send() -> None:
    result = await dispatch_fixture("inherited-attachment", reply=True)
    assert result["result"] == {"accepted": False, "failure_code": "native_message_changed"}
    counters = result["counters"]
    assert isinstance(counters, dict)
    assert counters["sends"] == 0
