"""Concrete previews and a default-closed write gate. No model approval token."""

import hashlib
import os
import stat
from datetime import UTC, date, datetime, time
from email.headerregistry import Address
from pathlib import Path
from typing import Annotated, Self

from pydantic import Field, field_validator, model_validator

from macos_personal_mcp.models import AwareDatetime, Calendar, Model, Text
from macos_personal_mcp.process import NativeError


class MailSend(Model):
    operation_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{8,80}$")]
    sender: Text
    to: list[Text] = Field(min_length=1, max_length=100)
    cc: list[Text] = Field(default_factory=list, max_length=100)
    bcc: list[Text] = Field(default_factory=list, max_length=100)
    subject: str = Field(max_length=998)
    body: str = Field(max_length=1_000_000)
    attachments: list[Text] = Field(default_factory=list, max_length=20)

    @field_validator("subject")
    @classmethod
    def header_safe(cls, value: str) -> str:
        if "\r" in value or "\n" in value or "\x00" in value:
            raise ValueError("Subject cannot contain control delimiters")
        return value

    @model_validator(mode="after")
    def literal_addresses(self) -> Self:
        for value in [self.sender, *self.to, *self.cc, *self.bcc]:
            if any(c.isspace() for c in value) or "\x00" in value:
                raise ValueError("Use literal addresses without whitespace or aliases")
            address = Address(addr_spec=value)
            if not address.username or not address.domain or address.addr_spec != value:
                raise ValueError("Use one explicit email addr-spec per recipient")
        recipients = [v.casefold() for v in [*self.to, *self.cc, *self.bcc]]
        if len(recipients) != len(set(recipients)):
            raise ValueError("Recipient repeated across To/CC/BCC")
        return self


class EventCreate(Model):
    operation_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{8,80}$")]
    calendar_id: Text
    title: Text
    start: AwareDatetime | None = None
    end: AwareDatetime | None = None
    all_day_start: date | None = None
    all_day_end_exclusive: date | None = None
    timezone: str = "Europe/London"
    notes: str = Field(default="", max_length=100_000)
    location: str = Field(default="", max_length=4096)
    url: str = Field(default="", max_length=4096)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError("Unknown event timezone") from error
        if self.all_day_start is not None or self.all_day_end_exclusive is not None:
            if (
                self.start is not None
                or self.end is not None
                or self.all_day_start is None
                or self.all_day_end_exclusive is None
                or self.all_day_end_exclusive <= self.all_day_start
            ):
                raise ValueError("Use exclusive ordered all-day dates without timed instants")
        elif (
            self.start is None
            or self.end is None
            or self.end.astimezone(UTC) <= self.start.astimezone(UTC)
        ):
            raise ValueError("Require aware end > start, or exclusive all-day dates")
        self.instants()
        return self

    def instants(self) -> tuple[datetime, datetime]:
        from zoneinfo import ZoneInfo

        if self.start is not None and self.end is not None:
            return self.start, self.end
        if self.all_day_start is None or self.all_day_end_exclusive is None:
            raise ValueError("Missing event dates")
        zone = ZoneInfo(self.timezone)
        instants = tuple(
            datetime.combine(d, time(), zone)
            for d in (self.all_day_start, self.all_day_end_exclusive)
        )
        for instant in instants:
            if instant.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != instant.replace(
                tzinfo=None
            ):
                raise ValueError("All-day boundary does not exist in selected timezone")
        return instants[0], instants[1]


class AttachmentIdentity(Model):
    path: str
    bytes: int
    sha256: str


class MailPreview(Model):
    payload: MailSend
    attachment_identities: list[AttachmentIdentity]
    digest: str
    executable: bool = False
    blocker: str = "Preview only. Sending requires explicit local enablement; review follows the owner's native or host startup approval policy"


class EventPreview(Model):
    payload: EventCreate
    calendar: Calendar
    digest: str


type WritePreview = MailPreview | EventPreview


def preview_event(payload: EventCreate, calendar: Calendar) -> EventPreview:
    if (
        payload.calendar_id != calendar.id
        or not calendar.writable
        or calendar.subscribed
        or calendar.immutable
    ):
        raise NativeError(
            "calendar_not_writable",
            "Exact selected calendar must be writable and unchanged; no fallback",
        )
    digest = hashlib.sha256(
        ("calendar_create\0" + payload.model_dump_json() + calendar.model_dump_json()).encode()
    ).hexdigest()
    return EventPreview(payload=payload, calendar=calendar, digest=digest)


def identify_attachment(path_text: str) -> AttachmentIdentity:
    path = Path(path_text)
    if not path.is_absolute() or path.is_symlink():
        raise NativeError(
            "attachment_invalid", "Attachments must be absolute regular files, not symlinks"
        )
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > 20_000_000:
                raise NativeError("attachment_invalid", "Attachment is not a regular file <= 20 MB")
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
            after = os.fstat(stream.fileno())
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ):
                raise NativeError(
                    "attachment_changed", "Attachment changed while preparing preview"
                )
    except OSError as error:
        raise NativeError("attachment_unavailable", "Cannot read an attachment") from error
    return AttachmentIdentity(path=str(path), bytes=after.st_size, sha256=digest)


def preview_mail(payload: MailSend) -> MailPreview:
    identities = [identify_attachment(path) for path in payload.attachments]
    if sum(item.bytes for item in identities) > 50_000_000:
        raise NativeError("attachment_limit", "Total attachments exceed 50 MB")
    digest = hashlib.sha256(
        (
            payload.model_dump_json() + "".join(item.model_dump_json() for item in identities)
        ).encode()
    ).hexdigest()
    return MailPreview(payload=payload, attachment_identities=identities, digest=digest)


def refuse_write(*, read_only: bool) -> None:
    if read_only:
        raise NativeError(
            "read_only", "Source-mutating tools are absent and rejected in read-only mode"
        )
    raise NativeError(
        "approval_unavailable",
        "Native write executor disabled in this launch mode; no native mutation was dispatched",
    )
