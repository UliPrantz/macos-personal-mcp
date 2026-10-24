import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from macos_personal_mcp.models import Accounts, CalendarScope, MailScope
from macos_personal_mcp.process import NativeError
from macos_personal_mcp.safety import MailSend, identify_attachment, preview_mail
from macos_personal_mcp.service import Service


def mail_payload(attachment: Path | None = None) -> MailSend:
    return MailSend(
        operation_id="synthetic_test_01",
        sender="sender@example.test",
        to=["recipient@example.test"],
        cc=["cc@example.test"],
        bcc=["bcc@example.test"],
        subject="Synthetic preview",
        body="Private preview content",
        attachments=[str(attachment)] if attachment is not None else [],
    )


@pytest.mark.parametrize("change", [{"limit": "2"}, {"unexpected": True}, {"limit": True}])
def test_strict_input_rejects_coercion_and_unknown_fields(change: dict[str, object]) -> None:
    payload: dict[str, object] = {
        "account_id": "synthetic",
        "mailbox_path": ["Inbox"],
        "since": "2026-10-01T00:00:00+01:00",
        "before": "2026-10-23T00:00:00+01:00",
        **change,
    }
    with pytest.raises(ValidationError):
        MailScope.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize(
    "start,end",
    [
        ("2026-10-01T00:00:00", "2026-10-23T00:00:00Z"),
        ("2026-10-23T00:00:00Z", "2026-10-01T00:00:00Z"),
    ],
)
def test_invalid_time_scope(start: str, end: str) -> None:
    with pytest.raises(ValidationError):
        MailScope.model_validate_json(
            json.dumps(
                {
                    "account_id": "synthetic",
                    "mailbox_path": ["Inbox"],
                    "since": start,
                    "before": end,
                }
            )
        )


def test_london_dst_uses_explicit_instants() -> None:
    scope = CalendarScope.model_validate_json(
        json.dumps(
            {
                "calendar_ids": ["synthetic"],
                "since": "2026-10-25T01:30:00+01:00",
                "before": "2026-10-25T01:30:00+00:00",
            }
        )
    )
    assert (scope.before - scope.since).total_seconds() == 3600


@pytest.mark.parametrize(
    "address",
    [
        "Alice",
        "Alice <a@example.test>",
        "a@example.test\nBcc:x@example.test",
        "a@example.test,b@example.test",
    ],
)
def test_recipient_alias_and_injection_rejected(address: str) -> None:
    data = mail_payload().model_dump()
    data["to"] = [address]
    with pytest.raises((ValidationError, ValueError)):
        MailSend.model_validate(data)


def test_duplicate_recipient_and_model_approval_rejected() -> None:
    with pytest.raises(ValidationError):
        MailSend.model_validate({**mail_payload().model_dump(), "bcc": ["recipient@example.test"]})
    with pytest.raises(ValidationError):
        MailSend.model_validate({**mail_payload().model_dump(), "approved": True})


def test_attachment_bytes_bound_to_concrete_preview(tmp_path: Path) -> None:
    attachment = tmp_path / "synthetic.txt"
    attachment.write_bytes(b"first bytes")
    first = preview_mail(mail_payload(attachment))
    attachment.write_bytes(b"replacement bytes")
    second = preview_mail(mail_payload(attachment))
    assert first.digest != second.digest
    assert first.attachment_identities[0].sha256 != second.attachment_identities[0].sha256
    assert first.payload.bcc == ["bcc@example.test"]
    assert first.payload.body == "Private preview content"
    assert not first.executable


def test_missing_relative_directory_and_symlink_attachments_rejected(tmp_path: Path) -> None:
    link = tmp_path / "link"
    link.symlink_to(tmp_path)
    for path in [str(tmp_path / "missing"), "relative.txt", str(tmp_path), str(link)]:
        with pytest.raises(NativeError):
            identify_attachment(path)


def test_sender_must_match_exactly_one_enabled_account() -> None:
    accounts = Accounts.model_validate_json(
        '{"accounts":[{"id":"a","name":"Synthetic","emails":["sender@example.test"],"enabled":true}]}'
    ).accounts
    Service.validate_sender("sender@example.test", accounts)
    with pytest.raises(NativeError):
        Service.validate_sender("other@example.test", accounts)
    with pytest.raises(NativeError):
        Service.validate_sender("sender@example.test", accounts + accounts)
