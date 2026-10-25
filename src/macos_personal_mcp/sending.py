"""Policy-selected review, frozen attachments and durable no-blind-retry Mail dispatch."""

import asyncio
import os
import shutil
import sqlite3
import stat
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Literal, Protocol

from macos_personal_mcp.approval import reviewer_for
from macos_personal_mcp.models import Model
from macos_personal_mcp.permissions import ApprovalMode
from macos_personal_mcp.process import NativeError, run_child
from macos_personal_mcp.safety import (
    MailPreview,
    MailSend,
    WritePreview,
    identify_attachment,
    preview_mail,
)

type OutcomeStatus = Literal[
    "preparing",
    "approval_denied",
    "not_dispatched",
    "dispatch_started",
    "accepted",
    "outcome_unknown",
]


class SendOutcome(Model):
    operation_id: str
    digest: str
    status: OutcomeStatus
    external_effects_dispatched: bool
    replayed: bool = False
    approval_mode: ApprovalMode | None = None
    detail: str
    failure_code: str | None = None


class Acceptance(Model):
    accepted: bool
    failure_code: Literal["native_message_changed"] | None = None


class Reviewer(Protocol):
    async def approve(self, preview: MailPreview) -> bool: ...


class Dispatcher(Protocol):
    async def dispatch(self, payload: MailSend) -> bool: ...


class NativeMailDispatcher:
    async def dispatch(self, payload: MailSend) -> bool:
        source = files("macos_personal_mcp").joinpath("mail_write.js")
        raw = await run_child(
            ["/usr/bin/osascript", "-l", "JavaScript", str(source)],
            payload.model_dump_json().encode(),
            timeout=20,
        )
        result = Acceptance.model_validate_json(raw)
        if result.failure_code is not None:
            raise NativeError(result.failure_code, "Native draft failed payload verification")
        return result.accepted


def private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise NativeError("private_storage", "Application data directory must be owner-only")


class OutcomeJournal:
    """Owned SQLite metadata only: no recipients, subject, body, paths or credentials."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.path = root / "write-outcomes.sqlite3"

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection]:
        private_directory(self.root)
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise NativeError("private_storage", "Outcome journal must be an owner-only file")
        finally:
            os.close(descriptor)
        connection = sqlite3.connect(self.path, timeout=1)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS outcomes "
                "(operation_id TEXT PRIMARY KEY, digest TEXT NOT NULL, status TEXT NOT NULL, "
                "updated_at TEXT NOT NULL)"
            )
            # Preserve the original four-column table: an older still-running
            # client may use INSERT ... VALUES without column names.
            connection.execute(
                "CREATE TABLE IF NOT EXISTS outcome_failures "
                "(operation_id TEXT PRIMARY KEY, failure_code TEXT NOT NULL)"
            )
            connection.commit()
            yield connection
        finally:
            connection.close()

    def reserve(self, preview: WritePreview) -> SendOutcome | None:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT o.digest, o.status, f.failure_code FROM outcomes o "
                "LEFT JOIN outcome_failures f ON f.operation_id=o.operation_id WHERE o.operation_id = ?",
                (preview.payload.operation_id,),
            ).fetchone()
            if row is not None:
                digest, status_text = str(row[0]), str(row[1])
                failure_code = str(row[2]) if row[2] is not None else None
                if digest != preview.digest:
                    raise NativeError(
                        "operation_conflict", "Operation ID already binds another payload"
                    )
                # Strictly validate journal values rather than trusting untyped SQLite rows.
                result = SendOutcome.model_validate(
                    {
                        "operation_id": preview.payload.operation_id,
                        "digest": digest,
                        "status": "outcome_unknown"
                        if status_text == "dispatch_started"
                        else status_text,
                        "external_effects_dispatched": status_text
                        in {"dispatch_started", "accepted", "outcome_unknown"},
                        "replayed": True,
                        "failure_code": failure_code,
                        "detail": "Recorded operation; no new approval or native dispatch. "
                        + (
                            "The draft failed verification before the send command. Inspect it before any further action."
                            if failure_code == "native_message_changed"
                            else "Never blindly retry an uncertain write."
                        ),
                    }
                )
                return result
            connection.execute(
                "INSERT INTO outcomes (operation_id,digest,status,updated_at) VALUES (?, ?, ?, ?)",
                (
                    preview.payload.operation_id,
                    preview.digest,
                    "preparing",
                    datetime.now(UTC).isoformat(),
                ),
            )
            connection.commit()
        return None

    def update(
        self, preview: WritePreview, status: OutcomeStatus, failure_code: str | None = None
    ) -> None:
        with self.connection() as connection:
            cursor = connection.execute(
                "UPDATE outcomes SET status = ?, updated_at = ? WHERE operation_id = ? AND digest = ?",
                (
                    status,
                    datetime.now(UTC).isoformat(),
                    preview.payload.operation_id,
                    preview.digest,
                ),
            )
            if cursor.rowcount != 1:
                raise NativeError("journal_identity", "Outcome journal identity mismatch")
            if failure_code is None:
                connection.execute(
                    "DELETE FROM outcome_failures WHERE operation_id = ?",
                    (preview.payload.operation_id,),
                )
            else:
                connection.execute(
                    "INSERT OR REPLACE INTO outcome_failures (operation_id,failure_code) VALUES (?,?)",
                    (preview.payload.operation_id, failure_code),
                )
            connection.commit()


@dataclass
class Snapshot:
    payload: MailSend
    retain: bool = False


@contextmanager
def frozen_attachments(preview: MailPreview, root: Path) -> Generator[Snapshot]:
    private_directory(root)
    temporary = Path(
        tempfile.mkdtemp(prefix=f"attachments-{preview.payload.operation_id}-", dir=root)
    )
    snapshot: Snapshot | None = None
    try:
        paths: list[str] = []
        for index, identity in enumerate(preview.attachment_identities):
            folder = Path(temporary) / str(index)
            folder.mkdir(mode=0o700)
            destination = folder / Path(identity.path).name
            descriptor = os.open(identity.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as source:
                info = os.fstat(source.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size != identity.bytes:
                    raise NativeError("attachment_changed", "Attachment changed before approval")
                # A bounded copy avoids reading an endlessly growing source file.
                with destination.open("xb") as target:
                    remaining = identity.bytes + 1
                    while remaining:
                        block = source.read(min(65536, remaining))
                        if not block:
                            break
                        target.write(block)
                        remaining -= len(block)
            destination.chmod(0o400)
            frozen = identify_attachment(str(destination))
            if frozen.bytes != identity.bytes or frozen.sha256 != identity.sha256:
                raise NativeError(
                    "attachment_changed", "Frozen attachment differs from reviewed bytes"
                )
            paths.append(str(destination))
        snapshot = Snapshot(preview.payload.model_copy(update={"attachments": paths}))
        yield snapshot
    finally:
        # Mail may still be consuming files after accepting the command. Retain
        # dispatched snapshots, including uncertain outcomes, until explicit cleanup.
        if snapshot is None or not snapshot.retain:
            shutil.rmtree(temporary)


class MailExecutor:
    def __init__(
        self,
        journal: OutcomeJournal,
        reviewer: Reviewer,
        dispatcher: Dispatcher,
        *,
        approval_mode: ApprovalMode = "native",
    ) -> None:
        self.journal = journal
        self.reviewer = reviewer
        self.dispatcher = dispatcher
        self.approval_mode: ApprovalMode = approval_mode

    async def send(self, payload: MailSend) -> SendOutcome:
        preview = preview_mail(payload)
        previous = self.journal.reserve(preview)
        if previous is not None:
            return previous
        dispatched = False
        status: OutcomeStatus = "not_dispatched"
        detail = "No native write dispatched"
        failure_code: str | None = None
        try:
            with frozen_attachments(preview, self.journal.root) as frozen:
                if not await self.reviewer.approve(preview):
                    status, detail = "approval_denied", "Human declined; no native write dispatched"
                else:
                    if preview_mail(payload).digest != preview.digest:
                        raise NativeError(
                            "attachment_changed", "Payload or attachment changed after review"
                        )
                    # Durable intent precedes even draft creation. Crashes/cancellation cannot
                    # become an automatic repeat send on the next connection.
                    self.journal.update(preview, "dispatch_started")
                    frozen.retain = True
                    dispatched = True
                    accepted = await self.dispatcher.dispatch(frozen.payload)
                    status = "accepted" if accepted else "outcome_unknown"
                    detail = (
                        "Apple Mail accepted the send command; delivery and attachment receipt are not yet verified"
                        if accepted
                        else "Native write attempted; external outcome unknown. Do not retry automatically"
                    )
        except asyncio.CancelledError:
            self.journal.update(preview, "outcome_unknown" if dispatched else "not_dispatched")
            raise
        except NativeError as error:
            status = "outcome_unknown" if dispatched else "not_dispatched"
            failure_code = error.code
            if error.code == "native_message_changed":
                detail = (
                    "Mail created a draft but its fields differed from the reviewed payload; "
                    "the send command was not called. Inspect the draft before any further action."
                )
            else:
                detail = (
                    "Native Mail step failed (" + error.code + "). A draft may remain; "
                    "delivery is unknown. Inspect Drafts, Outbox, Sent and the recipient before retrying."
                    if dispatched
                    else "Approval, validation or preparation failed ("
                    + error.code
                    + "); no native write dispatched"
                )
        except Exception:
            status = "outcome_unknown" if dispatched else "not_dispatched"
            detail = (
                "Native write attempted; external outcome unknown. Do not retry automatically"
                if dispatched
                else "Approval, validation or preparation failed; no native write dispatched"
            )
        try:
            self.journal.update(preview, status, failure_code)
        except Exception:
            # The earlier dispatch_started record remains a no-retry barrier even if
            # the final journal write fails. Never report failure-before-dispatch here.
            if dispatched:
                status, detail = (
                    "outcome_unknown",
                    "Native write attempted; final outcome persistence failed. Do not retry",
                )
        return SendOutcome(
            operation_id=payload.operation_id,
            digest=preview.digest,
            status=status,
            external_effects_dispatched=dispatched,
            failure_code=failure_code,
            detail=detail,
            approval_mode=self.approval_mode,
        )


def native_executor(mode: ApprovalMode = "native") -> MailExecutor:
    root = Path.home() / "Library/Application Support/macos-personal-mcp"
    return MailExecutor(
        OutcomeJournal(root), reviewer_for(mode), NativeMailDispatcher(), approval_mode=mode
    )
