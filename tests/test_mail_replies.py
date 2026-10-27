import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from macos_personal_mcp.approval import review_text
from macos_personal_mcp.process import NativeError
from macos_personal_mcp.safety import MailPreview, MailSend, ReplyTarget, preview_mail
from macos_personal_mcp.sending import MailExecutor, OutcomeJournal
from tests.test_contracts import mail_payload
from tests.test_sending import DispatchFixture, HumanFixture


def target() -> ReplyTarget:
    return ReplyTarget(
        account_id="account-1",
        mailbox_path=["Inbox", "Nested"],
        local_id=123,
        expected_message_id="<original@example.test>",
    )


@pytest.mark.parametrize(
    "change",
    [
        {"local_id": "123"},
        {"local_id": True},
        {"local_id": 0},
        {"mailbox_path": []},
        {"expected_message_id": ""},
        {"reply_all": True},
    ],
)
def test_reply_target_is_exact_and_strict(change: dict[str, object]) -> None:
    data = target().model_dump()
    data.update(change)
    with pytest.raises(ValidationError):
        ReplyTarget.model_validate(data)


def test_reply_target_is_bound_to_review_and_digest() -> None:
    ordinary = mail_payload()
    reply = ordinary.model_copy(update={"reply_to_message": target()})
    preview = preview_mail(reply)
    assert preview.digest != preview_mail(ordinary).digest
    text = review_text(preview)
    for value in ["account-1", "Inbox / Nested", "123", "<original@example.test>", "read/replied"]:
        assert value in text


@pytest.mark.parametrize("with_attachment", [False, True])
async def test_upgrade_preserves_old_nonreply_journal_digest_and_no_retry(
    tmp_path: Path, with_attachment: bool
) -> None:
    attachment = tmp_path / "old-attachment.txt"
    attachment.write_bytes(b"approved attachment")
    payload = mail_payload(attachment if with_attachment else None)
    preview = preview_mail(payload)
    old_json = payload.model_dump_json(exclude={"reply_to_message"})
    old_digest = hashlib.sha256(
        (
            old_json + "".join(item.model_dump_json() for item in preview.attachment_identities)
        ).encode()
    ).hexdigest()
    assert preview_mail(payload).digest == old_digest
    journal = OutcomeJournal(tmp_path / "owned")
    legacy = MailPreview(
        payload=payload, attachment_identities=preview.attachment_identities, digest=old_digest
    )
    assert journal.reserve(legacy) is None
    journal.update(legacy, "dispatch_started")
    reviewer, dispatch = HumanFixture(True), DispatchFixture()
    result = await MailExecutor(journal, reviewer, dispatch).send(payload)
    assert result.replayed and result.status == "outcome_unknown"
    assert reviewer.calls == dispatch.calls == 0


async def test_reply_replay_and_changed_target_never_send_again(tmp_path: Path) -> None:
    payload = mail_payload().model_copy(update={"reply_to_message": target()})
    journal = OutcomeJournal(tmp_path / "owned")
    reviewer, dispatch = HumanFixture(True), DispatchFixture()
    executor = MailExecutor(journal, reviewer, dispatch)
    assert (await executor.send(payload)).status == "accepted"
    assert (await executor.send(payload)).replayed
    changed = payload.model_copy(
        update={"reply_to_message": target().model_copy(update={"local_id": 124})}
    )
    with pytest.raises(NativeError, match="already binds another payload"):
        await executor.send(changed)
    assert reviewer.calls == dispatch.calls == 1


async def test_denied_reply_never_dispatches(tmp_path: Path) -> None:
    data = mail_payload().model_dump()
    data["reply_to_message"] = target().model_dump()
    payload = MailSend.model_validate(data)
    reviewer, dispatch = HumanFixture(False), DispatchFixture()
    result = await MailExecutor(OutcomeJournal(tmp_path / "owned"), reviewer, dispatch).send(
        payload
    )
    assert result.status == "approval_denied"
    assert dispatch.calls == 0
