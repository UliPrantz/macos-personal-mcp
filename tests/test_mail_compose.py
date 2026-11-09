import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client
from pydantic import ValidationError

from macos_personal_mcp import mail_compose
from macos_personal_mcp.mail_compose import (
    MailCompose,
    MailComposeResult,
    NativeMailComposer,
    compose_url,
)
from macos_personal_mcp.models import Failure
from macos_personal_mcp.process import NativeError
from macos_personal_mcp.service import Service


def test_mailto_preserves_unicode_delimiters_and_only_normalizes_line_endings() -> None:
    request = MailCompose(
        to=["first+tag@example.test", "second@example.test"],
        cc=["copy@example.test"],
        bcc=["hidden@example.test"],
        subject="Résumé & ?#%+ = 🐱",
        body="Hi Uli,\n\nUnicode £ 🐱\rNext\r\nhttps://example.test/?a=1&b=%20#x\nBcc: literal",
    )
    url = urlsplit(compose_url(request))
    assert url.scheme == "mailto" and not url.netloc and not url.fragment
    assert unquote(url.path) == ",".join(request.to)
    query = parse_qs(url.query, strict_parsing=True)
    assert query == {
        "cc": ["copy@example.test"],
        "bcc": ["hidden@example.test"],
        "subject": [request.subject],
        "body": [
            "Hi Uli,\r\n\r\nUnicode £ 🐱\r\nNext\r\n"
            "https://example.test/?a=1&b=%20#x\r\nBcc: literal"
        ],
    }
    assert not query["body"][0].startswith(("\r", "\n"))
    assert compose_url(MailCompose()) == "mailto:"
    # Intentional leading blank lines are retained, never stripped.
    assert parse_qs(urlsplit(compose_url(MailCompose(body="\nHello"))).query)["body"] == [
        "\r\nHello"
    ]


@pytest.mark.parametrize(
    "data",
    [
        {"subject": "Hello\r\nBcc: other@example.test"},
        {"subject": "Hello\u2028Bcc: other@example.test"},
        {"subject": "Hello\tthere"},
        {"body": "Hello\x00there"},
        {"to": "person@example.test"},
        {"to": ["Person <person@example.test>"]},
        {"to": ["person@example.test\nBcc: other@example.test"]},
        {"to": ["person@example.test,other@example.test"]},
        {"to": ["person@example.test"], "cc": ["PERSON@example.test"]},
        {"attachments": ["/synthetic/unsupported-file"]},
        {"sender": "sender@example.test"},
        {"send": True},
    ],
)
def test_invalid_or_unsupported_fields_rejected(data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        MailCompose.model_validate_json(json.dumps(data))


async def test_encoded_limit_prevents_native_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    async def forbidden(argv: list[str], payload: bytes, **kwargs: object) -> bytes:
        raise AssertionError("Oversized URL must not launch a worker")

    monkeypatch.setattr(mail_compose, "run_child", forbidden)
    with pytest.raises(NativeError, match="64,000"):
        await NativeMailComposer().open(MailCompose(body="🐱" * 6000))


async def test_native_adapter_uses_fixed_argv_stdin_and_truthful_acknowledgment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = MailCompose(subject="Synthetic", body="Literal `$(command)` & ?#%")

    async def child(argv: list[str], payload: bytes, **kwargs: object) -> bytes:
        assert argv == [sys.executable, "-m", "macos_personal_mcp.mail_compose"]
        assert MailCompose.model_validate_json(payload) == request
        assert kwargs == {"timeout": 15, "max_bytes": 8192}
        return MailComposeResult().model_dump_json().encode()

    monkeypatch.setattr(mail_compose, "run_child", child)
    result = await NativeMailComposer().open(request)
    assert result.open_acknowledged and not result.saved_by_mcp and not result.sent_by_mcp


@pytest.mark.parametrize("failure", [False, True])
async def test_worker_failure_or_deadline_never_reports_opened(
    monkeypatch: pytest.MonkeyPatch, failure: bool
) -> None:
    async def child(argv: list[str], payload: bytes, **kwargs: object) -> bytes:
        if failure:
            return (
                Failure(code="compose_failed", message="Synthetic refusal")
                .model_dump_json()
                .encode()
            )
        raise NativeError("deadline", "Synthetic timeout")

    monkeypatch.setattr(mail_compose, "run_child", child)
    with pytest.raises(NativeError) as error:
        await NativeMailComposer().open(MailCompose())
    assert error.value.code == ("compose_failed" if failure else "compose_unconfirmed")


class ComposerFixture:
    def __init__(self) -> None:
        self.requests: list[MailCompose] = []

    async def open(self, request: MailCompose) -> MailComposeResult:
        self.requests.append(request)
        return MailComposeResult()


async def test_compose_effect_requires_enablement_and_has_nonidempotent_ui_annotations() -> None:
    composer = ComposerFixture()
    readonly = Service(mail_composer=composer)
    assert "mail_compose" not in {t.name for t in readonly.tools()}
    rejected = await readonly.call("mail_compose", "{}")
    assert isinstance(rejected, Failure) and rejected.code == "read_only"
    disabled = await Service(read_only=False).call("mail_compose", "{}")
    assert isinstance(disabled, Failure) and disabled.code == "compose_disabled"
    assert composer.requests == []
    enabled = Service(read_only=False, mail_composer=composer)
    invalid = await enabled.call("mail_compose", '{"send":true}')
    assert isinstance(invalid, Failure) and invalid.code == "invalid_input"
    assert composer.requests == []
    result = await enabled.call("mail_compose", '{"body":"Hello"}')
    assert isinstance(result, MailComposeResult)
    assert composer.requests == [MailCompose(body="Hello")]
    annotations = next(t for t in enabled.tools() if t.name == "mail_compose").annotations
    assert annotations is not None
    assert not annotations.read_only_hint and not annotations.destructive_hint
    assert not annotations.idempotent_hint and annotations.open_world_hint
    policy = next(t for t in enabled.approval_report().tools if t.tool == "mail_compose")
    assert policy.executor_enabled and not policy.server_dialog


async def test_sdk_compose_discovery_and_validation_never_open_native_ui(tmp_path: Path) -> None:
    config = tmp_path / "permissions.toml"
    config.write_text('[approval]\ndefault="native"\n')
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "macos_personal_mcp.cli",
            "serve",
            "--enable-mail-compose",
            "--config",
            str(config),
        ],
        env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
        cwd=tmp_path,
    )
    async with Client(stdio_client(params), read_timeout_seconds=10) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
        assert "mail_compose" in tools
        assert tools["mail_compose"].input_schema == MailCompose.model_json_schema()
        assert tools["mail_compose"].output_schema == MailComposeResult.model_json_schema()
        rejected = await client.call_tool("mail_compose", {"sender": "unsupported@example.test"})
        assert rejected.is_error
        assert rejected.structured_content is not None
        assert rejected.structured_content["code"] == "invalid_input"
        oversized = await client.call_tool("mail_compose", {"body": "🐱" * 6000})
        assert oversized.is_error
        assert oversized.structured_content is not None
        assert oversized.structured_content["code"] == "compose_url_limit"


def test_readonly_cannot_combine_with_compose_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    from macos_personal_mcp.cli import main

    monkeypatch.setattr(sys, "argv", ["mcp", "schemas", "--read-only", "--enable-mail-compose"])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2


@pytest.mark.parametrize("accepted", [True, False])
def test_native_workspace_acknowledgment_is_required(
    monkeypatch: pytest.MonkeyPatch, accepted: bool
) -> None:
    from Foundation import NSURL

    opened: list[str] = []

    class WorkspaceFixture:
        @staticmethod
        def sharedWorkspace() -> WorkspaceFixture:
            return WorkspaceFixture()

        def openURL_(self, url: NSURL) -> bool:
            opened.append(url.absoluteString())
            return accepted

    monkeypatch.setattr("AppKit.NSWorkspace", WorkspaceFixture)
    request = MailCompose(body="Hello\n\nUnicode 🐱")
    if accepted:
        result = mail_compose.open_native(request)
        assert result.open_acknowledged and not result.sent_by_mcp
    else:
        with pytest.raises(NativeError, match="did not acknowledge"):
            mail_compose.open_native(request)
    assert opened == [compose_url(request)]


async def test_invalid_worker_acknowledgment_is_uncertain(monkeypatch: pytest.MonkeyPatch) -> None:
    async def child(argv: list[str], payload: bytes, **kwargs: object) -> bytes:
        return b'{"open_acknowledged":false}'

    monkeypatch.setattr(mail_compose, "run_child", child)
    with pytest.raises(NativeError) as error:
        await NativeMailComposer().open(MailCompose())
    assert error.value.code == "compose_unconfirmed"
