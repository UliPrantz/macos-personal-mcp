import asyncio
from contextlib import closing
from pathlib import Path

import pytest

from macos_personal_mcp.approval import review_text
from macos_personal_mcp.process import NativeError
from macos_personal_mcp.safety import MailPreview, MailSend, WritePreview, preview_mail
from macos_personal_mcp.sending import MailExecutor, OutcomeJournal
from tests.test_contracts import mail_payload


class HumanFixture:
    def __init__(
        self, allow: bool, *, change: Path | None = None, unavailable: bool = False
    ) -> None:
        self.allow = allow
        self.change = change
        self.unavailable = unavailable
        self.calls = 0

    async def approve(self, preview: MailPreview) -> bool:
        self.calls += 1
        if self.unavailable:
            raise NativeError("deadline", "Synthetic approval timeout")
        if self.change is not None:
            self.change.write_bytes(b"changed during review")
        return self.allow


class DispatchFixture:
    def __init__(self, *, uncertain: bool = False, cancel: bool = False) -> None:
        self.calls = 0
        self.uncertain = uncertain
        self.cancel = cancel
        self.attachment_paths: list[Path] = []
        self.bytes: list[bytes] = []

    async def dispatch(self, payload: MailSend) -> bool:
        self.calls += 1
        self.attachment_paths = [Path(p) for p in payload.attachments]
        self.bytes = [p.read_bytes() for p in self.attachment_paths]
        if self.cancel:
            raise asyncio.CancelledError
        if self.uncertain:
            raise NativeError("deadline", "Synthetic uncertain send")
        return True


@pytest.mark.parametrize("unavailable", [False, True])
async def test_denial_or_missing_approval_produces_zero_native_effects(
    tmp_path: Path, unavailable: bool
) -> None:
    reviewer = HumanFixture(False, unavailable=unavailable)
    dispatch = DispatchFixture()
    journal = OutcomeJournal(tmp_path / "owned")
    executor = MailExecutor(journal, reviewer, dispatch)
    result = await executor.send(mail_payload())
    assert result.status == ("not_dispatched" if unavailable else "approval_denied")
    assert not result.external_effects_dispatched and dispatch.calls == 0
    repeat = await MailExecutor(journal, reviewer, dispatch).send(mail_payload())
    assert repeat.replayed and reviewer.calls == 1 and dispatch.calls == 0
    assert list(journal.root.glob("attachments-*")) == []


async def test_changed_bytes_invalidate_human_review(tmp_path: Path) -> None:
    original = tmp_path / "approved.txt"
    original.write_bytes(b"original approved bytes")
    reviewer = HumanFixture(True, change=original)
    dispatch = DispatchFixture()
    executor = MailExecutor(OutcomeJournal(tmp_path / "owned"), reviewer, dispatch)
    result = await executor.send(mail_payload(original))
    assert result.status == "not_dispatched" and dispatch.calls == 0


async def test_frozen_bytes_and_durable_deduplication_across_executor_restart(
    tmp_path: Path,
) -> None:
    original = tmp_path / "approved.txt"
    original.write_bytes(b"original approved bytes")
    reviewer = HumanFixture(True)
    dispatch = DispatchFixture()
    journal = OutcomeJournal(tmp_path / "owned")
    result = await MailExecutor(journal, reviewer, dispatch).send(mail_payload(original))
    assert result.status == "accepted" and result.external_effects_dispatched
    assert dispatch.bytes == [b"original approved bytes"]
    assert dispatch.attachment_paths[0] != original
    assert dispatch.attachment_paths[0].name == original.name
    # Retain dispatched snapshots until explicit cleanup, including after acknowledgment.
    assert dispatch.attachment_paths[0].exists()
    repeat = await MailExecutor(journal, reviewer, dispatch).send(mail_payload(original))
    assert repeat.replayed and repeat.status == "accepted"
    assert dispatch.calls == reviewer.calls == 1
    changed = mail_payload(original).model_copy(update={"body": "different content"})
    with pytest.raises(NativeError, match="Operation ID already binds"):
        await MailExecutor(journal, reviewer, dispatch).send(changed)
    assert dispatch.calls == 1
    assert b"recipient@example.test" not in journal.path.read_bytes()
    assert b"Private preview content" not in journal.path.read_bytes()


async def test_uncertain_send_is_never_blindly_retried(tmp_path: Path) -> None:
    reviewer = HumanFixture(True)
    dispatch = DispatchFixture(uncertain=True)
    journal = OutcomeJournal(tmp_path / "owned")
    result = await MailExecutor(journal, reviewer, dispatch).send(mail_payload())
    assert result.status == "outcome_unknown" and result.external_effects_dispatched
    repeat = await MailExecutor(journal, reviewer, dispatch).send(mail_payload())
    assert repeat.replayed and repeat.status == "outcome_unknown"
    assert dispatch.calls == reviewer.calls == 1


async def test_cancellation_after_dispatch_persists_no_retry_barrier(tmp_path: Path) -> None:
    reviewer = HumanFixture(True)
    dispatch = DispatchFixture(cancel=True)
    journal = OutcomeJournal(tmp_path / "owned")
    with pytest.raises(asyncio.CancelledError):
        await MailExecutor(journal, reviewer, dispatch).send(mail_payload())
    repeat = await MailExecutor(journal, reviewer, dispatch).send(mail_payload())
    assert repeat.status == "outcome_unknown" and repeat.replayed
    assert dispatch.calls == reviewer.calls == 1


async def test_crash_marker_is_reported_unknown_without_approval_or_dispatch(
    tmp_path: Path,
) -> None:
    journal = OutcomeJournal(tmp_path / "owned")
    preview = preview_mail(mail_payload())
    assert journal.reserve(preview) is None
    journal.update(preview, "dispatch_started")
    reviewer, dispatch = HumanFixture(True), DispatchFixture()
    repeat = await MailExecutor(journal, reviewer, dispatch).send(mail_payload())
    assert repeat.status == "outcome_unknown" and repeat.replayed
    assert reviewer.calls == dispatch.calls == 0


def test_review_contains_every_recipient_full_body_and_attachment_identity(tmp_path: Path) -> None:
    attachment = tmp_path / "reviewed.txt"
    attachment.write_bytes(b"synthetic")
    preview = preview_mail(mail_payload(attachment))
    text = review_text(preview)
    for value in [
        preview.payload.sender,
        *preview.payload.to,
        *preview.payload.cc,
        *preview.payload.bcc,
        preview.payload.body,
        preview.payload.subject,
        str(attachment),
        preview.attachment_identities[0].sha256,
        preview.digest,
    ]:
        assert value in text


async def test_read_only_rejects_send_even_with_configured_executor(tmp_path: Path) -> None:
    from macos_personal_mcp.models import Failure
    from macos_personal_mcp.service import Service
    from tests.test_service import FixtureBridge

    reviewer, dispatch = HumanFixture(True), DispatchFixture()
    executor = MailExecutor(OutcomeJournal(tmp_path / "owned"), reviewer, dispatch)
    bridge = FixtureBridge()
    service = Service(read_only=True, bridge=bridge, mail_executor=executor)
    result = await service.call("mail_send", mail_payload().model_dump_json())
    assert isinstance(result, Failure) and result.code == "read_only"
    assert bridge.calls == [] and reviewer.calls == dispatch.calls == 0
    assert not executor.journal.path.exists()


async def test_final_journal_failure_never_claims_zero_effects(tmp_path: Path) -> None:
    from typing import override

    from macos_personal_mcp.sending import OutcomeStatus

    class FinalFailure(OutcomeJournal):
        @override
        def update(
            self, preview: WritePreview, status: OutcomeStatus, failure_code: str | None = None
        ) -> None:
            if status == "accepted":
                raise OSError("Synthetic final persistence failure")
            super().update(preview, status, failure_code)

    reviewer, dispatch = HumanFixture(True), DispatchFixture()
    journal = FinalFailure(tmp_path / "owned")
    result = await MailExecutor(journal, reviewer, dispatch).send(mail_payload())
    assert result.status == "outcome_unknown" and result.external_effects_dispatched
    retry = await MailExecutor(journal, reviewer, dispatch).send(mail_payload())
    assert retry.status == "outcome_unknown" and retry.replayed
    assert reviewer.calls == dispatch.calls == 1


async def test_draft_verification_diagnostic_survives_restart_without_resending(
    tmp_path: Path,
) -> None:
    class ChangedDraft:
        def __init__(self) -> None:
            self.calls = 0

        async def dispatch(self, payload: MailSend) -> bool:
            self.calls += 1
            raise NativeError("native_message_changed", "Untrusted private error text")

    reviewer = HumanFixture(True)
    dispatcher = ChangedDraft()
    journal = OutcomeJournal(tmp_path / "owned")
    result = await MailExecutor(journal, reviewer, dispatcher).send(mail_payload())
    assert result.status == "outcome_unknown" and result.external_effects_dispatched
    assert result.failure_code == "native_message_changed"
    assert "send command was not called" in result.detail
    assert "Untrusted private" not in result.detail
    replay = await MailExecutor(journal, reviewer, dispatcher).send(mail_payload())
    assert replay.replayed and replay.failure_code == "native_message_changed"
    assert "draft failed verification before the send command" in replay.detail
    assert reviewer.calls == dispatcher.calls == 1


def test_old_outcome_journal_migration_preserves_uncertain_no_retry_barrier(tmp_path: Path) -> None:
    import sqlite3

    payload = mail_payload()
    preview = preview_mail(payload)
    root = tmp_path / "owned"
    root.mkdir(mode=0o700)
    path = root / "write-outcomes.sqlite3"
    with closing(sqlite3.connect(path)) as db:
        db.execute(
            "CREATE TABLE outcomes (operation_id TEXT PRIMARY KEY,digest TEXT NOT NULL,status TEXT NOT NULL,updated_at TEXT NOT NULL)"
        )
        db.execute(
            "INSERT INTO outcomes VALUES (?,?,?,?)",
            (payload.operation_id, preview.digest, "dispatch_started", "2026-10-01T00:00:00Z"),
        )
        db.commit()
    path.chmod(0o600)
    result = OutcomeJournal(root).reserve(preview)
    assert result is not None and result.replayed and result.status == "outcome_unknown"
    assert result.failure_code is None and result.external_effects_dispatched
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT count(*) FROM outcomes").fetchone()[0] == 1
        assert {row[1] for row in db.execute("PRAGMA table_info(outcomes)")} == {
            "operation_id",
            "digest",
            "status",
            "updated_at",
        }
        assert db.execute("SELECT count(*) FROM outcome_failures").fetchone()[0] == 0
        # Old live clients can still insert their original four-column records.
        db.execute(
            "INSERT INTO outcomes VALUES (?,?,?,?)",
            ("old_client", "synthetic", "preparing", "2026-10-01T00:00:00Z"),
        )
        db.commit()


async def test_native_dispatcher_reports_safe_structured_draft_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from macos_personal_mcp.sending import NativeMailDispatcher

    async def synthetic_child(argv: list[str], payload: bytes, *, timeout: float) -> bytes:
        assert timeout == 20
        return b'{"accepted":false,"failure_code":"native_message_changed"}'

    monkeypatch.setattr("macos_personal_mcp.sending.run_child", synthetic_child)
    with pytest.raises(NativeError) as error:
        await NativeMailDispatcher().dispatch(mail_payload())
    assert error.value.code == "native_message_changed"
