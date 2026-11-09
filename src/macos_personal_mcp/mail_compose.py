"""Open a bounded mailto composer without Mail's scripted content setter."""

import sys
import unicodedata
from email.headerregistry import Address
from typing import Literal, Protocol, Self
from urllib.parse import quote

from pydantic import Field, TypeAdapter, ValidationError, field_validator, model_validator

from macos_personal_mcp.models import Failure, Model, Text
from macos_personal_mcp.process import NativeError, run_child

MAX_COMPOSE_URL = 64_000


class MailCompose(Model):
    to: list[Text] = Field(default_factory=list, max_length=100)
    cc: list[Text] = Field(default_factory=list, max_length=100)
    bcc: list[Text] = Field(default_factory=list, max_length=100)
    subject: str = Field(default="", max_length=998)
    body: str = Field(
        default="",
        max_length=50_000,
        description="Unicode plain text. Existing CR/LF line breaks become CRLF; no leading newline is added. The complete percent-encoded mailto URL must fit 64,000 ASCII characters.",
    )

    @field_validator("subject")
    @classmethod
    def safe_subject(cls, value: str) -> str:
        if any(unicodedata.category(c) in {"Cc", "Cs", "Zl", "Zp"} for c in value):
            raise ValueError("Subject cannot contain control characters or line breaks")
        return value

    @field_validator("body")
    @classmethod
    def safe_body(cls, value: str) -> str:
        if any(unicodedata.category(c) in {"Cc", "Cs"} and c not in "\t\r\n" for c in value):
            raise ValueError("Body contains unsupported control characters")
        return value

    @model_validator(mode="after")
    def literal_recipients(self) -> Self:
        recipients = [*self.to, *self.cc, *self.bcc]
        for value in recipients:
            if any(c.isspace() or unicodedata.category(c).startswith("C") for c in value):
                raise ValueError("Use literal recipient addresses without control characters")
            address = Address(addr_spec=value)
            if not address.username or not address.domain or address.addr_spec != value:
                raise ValueError("Use one explicit email addr-spec per recipient")
        if len(recipients) != len({v.casefold() for v in recipients}):
            raise ValueError("Recipient repeated across To/CC/BCC")
        return self


class MailComposeResult(Model):
    open_acknowledged: Literal[True] = True
    saved_by_mcp: Literal[False] = False
    sent_by_mcp: Literal[False] = False
    detail: str = (
        "macOS accepted the compose URL for the default email app. "
        "Review the composer and choose the sender, attachments and whether to send. "
        "The MCP did not save or send a message; the email app may autosave."
    )


def compose_url(request: MailCompose) -> str:
    body = request.body.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
    recipients = ",".join(quote(value, safe="") for value in request.to)
    fields = [
        ("cc", ",".join(request.cc)),
        ("bcc", ",".join(request.bcc)),
        ("subject", request.subject),
        ("body", body),
    ]
    query = "&".join(name + "=" + quote(value, safe="") for name, value in fields if value)
    url = "mailto:" + recipients + ("?" + query if query else "")
    if len(url) > MAX_COMPOSE_URL:
        raise NativeError(
            "compose_url_limit", "Encoded compose URL exceeds 64,000 characters; no URL opened"
        )
    return url


class MailComposer(Protocol):
    async def open(self, request: MailCompose) -> MailComposeResult: ...


class NativeMailComposer:
    async def open(self, request: MailCompose) -> MailComposeResult:
        # Check the encoded bound before starting any native operation. Payloads
        # travel over stdin, never argv, executable code, logs or returned URLs.
        compose_url(request)
        try:
            raw = await run_child(
                [sys.executable, "-m", "macos_personal_mcp.mail_compose"],
                request.model_dump_json().encode(),
                timeout=15,
                max_bytes=8192,
            )
        except NativeError as error:
            raise NativeError(
                "compose_unconfirmed",
                "Compose opening could not be confirmed; it may already be open. "
                "Check the email app before retrying. No send was requested.",
            ) from error
        adapter: TypeAdapter[MailComposeResult | Failure] = TypeAdapter(MailComposeResult | Failure)
        try:
            result = adapter.validate_json(raw)
        except ValidationError as error:
            raise NativeError(
                "compose_unconfirmed",
                "Invalid compose acknowledgment; check the email app before retrying. "
                "No send was requested.",
            ) from error
        if isinstance(result, Failure):
            raise NativeError(result.code, result.message)
        return result


def open_native(request: MailCompose) -> MailComposeResult:
    # AppKit is imported only in the bounded worker, on its main thread.
    from AppKit import NSWorkspace
    from Foundation import NSURL

    url = NSURL.URLWithString_(compose_url(request))
    if url is None or not NSWorkspace.sharedWorkspace().openURL_(url):
        raise NativeError("compose_failed", "macOS did not acknowledge opening the compose URL")
    return MailComposeResult()


def main() -> None:
    try:
        request = MailCompose.model_validate_json(sys.stdin.buffer.read(2_000_000))
        result: Model = open_native(request)
    except NativeError as error:
        result = Failure(code=error.code, message=error.detail)
    except Exception:
        # Native/validation exceptions may contain private compose fields.
        result = Failure(code="compose_failed", message="Compose opening could not be confirmed")
    print(result.model_dump_json())


if __name__ == "__main__":
    main()
