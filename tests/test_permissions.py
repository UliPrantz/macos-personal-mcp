import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from macos_personal_mcp import approval, permissions
from macos_personal_mcp.approval import Decision, HostReviewer, NativeReviewer, reviewer_for
from macos_personal_mcp.calendar_writes import CalendarExecutor
from macos_personal_mcp.models import Failure
from macos_personal_mcp.permissions import (
    ApprovalPolicy,
    ApprovalReport,
    LoadedConfig,
    LocalConfig,
    load_config,
)
from macos_personal_mcp.process import NativeError, run_child
from macos_personal_mcp.safety import EventPreview
from macos_personal_mcp.sending import MailExecutor, OutcomeJournal
from macos_personal_mcp.service import Service
from tests.test_calendar_writes import CalendarFixture, DispatcherFixture, request
from tests.test_contracts import mail_payload
from tests.test_sending import DispatchFixture
from tests.test_service import FixtureBridge


def policy_file(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "permissions.toml"
    path.write_text(text)
    path.chmod(0o600)
    return path


def loaded(policy: ApprovalPolicy, tmp_path: Path) -> LoadedConfig:
    return LoadedConfig(LocalConfig(approval=policy), tmp_path / "permissions.toml", True)


def test_missing_default_is_native_and_explicit_missing_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "missing.toml"
    monkeypatch.setattr(permissions, "default_config_path", lambda: missing)
    result = load_config()
    assert not result.loaded and result.config.approval.mode_for("mail_send") == "native"
    with pytest.raises(NativeError, match="missing"):
        load_config(missing)


def test_global_domain_and_tool_precedence(tmp_path: Path) -> None:
    config = load_config(
        policy_file(
            tmp_path,
            '[approval]\ndefault="host"\nmail="native"\ncalendar="native"\ncontacts="host"\n[approval.tools]\nmail_send="host"\n',
        )
    )
    policy = config.config.approval
    assert config.loaded and policy.default == "host"
    assert policy.mode_for("mail_send") == "host"
    assert policy.mode_for("mail_prepare_send") == "native"
    assert policy.mode_for("calendar_create_event") == "native"
    assert policy.mode_for("contacts_get") == "host"
    assert isinstance(reviewer_for(policy.mode_for("mail_send")), HostReviewer)
    assert isinstance(reviewer_for(policy.mode_for("calendar_create_event")), NativeReviewer)


@pytest.mark.parametrize(
    "text",
    [
        '[approval]\ndefault="yolo"',
        "[approval]\ndefault=true",
        "[approval]\ndefault=2026-10-23",
        "[approval]\ndefault=2026-10-23T10:00:00Z",
        '[approvals]\ndefault="host"',
        '[approval]\ncalender="host"',
        "[approval]\ndefault=",
    ],
)
def test_invalid_or_misspelled_config_never_delegates(tmp_path: Path, text: str) -> None:
    with pytest.raises(NativeError, match="Invalid approval"):
        load_config(policy_file(tmp_path, text))


def test_unknown_tool_override_fails_before_native_access(tmp_path: Path) -> None:
    policy = load_config(policy_file(tmp_path, '[approval.tools]\nmail_sned="host"'))
    bridge = FixtureBridge()
    with pytest.raises(NativeError, match="Unknown tool"):
        Service(bridge=bridge, approval_config=policy)
    assert not bridge.calls


def test_policy_is_a_startup_snapshot_until_reloaded(tmp_path: Path) -> None:
    path = policy_file(tmp_path, '[approval]\ndefault="native"')
    original = load_config(path)
    path.write_text('[approval]\ndefault="host"')
    assert original.config.approval.mode_for("mail_send") == "native"
    assert load_config(path).config.approval.mode_for("mail_send") == "host"


def test_executor_must_match_reported_policy(tmp_path: Path) -> None:
    config = loaded(ApprovalPolicy(default="host"), tmp_path)
    native = MailExecutor(OutcomeJournal(tmp_path / "owned"), NativeReviewer(), DispatchFixture())
    with pytest.raises(NativeError, match="disagree"):
        Service(read_only=False, mail_executor=native, approval_config=config)


def test_unsafe_or_excessive_policy_files_fail(tmp_path: Path) -> None:
    path = policy_file(tmp_path, '[approval]\ndefault="host"')
    link = tmp_path / "link.toml"
    link.symlink_to(path)
    with pytest.raises(NativeError):
        load_config(link)
    path.chmod(0o622)
    with pytest.raises(NativeError):
        load_config(path)
    path.chmod(0o600)
    path.write_bytes(b"#" + b"a" * 65_536)
    with pytest.raises(NativeError, match="64 KiB"):
        load_config(path)
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    with pytest.raises(NativeError):
        load_config(fifo)
    with pytest.raises(NativeError, match="absolute"):
        load_config(Path("relative.toml"))


async def test_delegation_skips_ui_but_preserves_attachments_and_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def no_ui(
        argv: list[str], payload: bytes = b"", *, timeout: float = 15, max_bytes: int = 8_000_000
    ) -> bytes:
        raise AssertionError("A delegated policy must not launch native approval UI")

    monkeypatch.setattr(approval, "run_child", no_ui)
    attachment = tmp_path / "original.txt"
    attachment.write_bytes(b"synthetic frozen bytes")
    dispatcher = DispatchFixture()
    journal = OutcomeJournal(tmp_path / "owned")
    executor = MailExecutor(journal, reviewer_for("host"), dispatcher, approval_mode="host")
    outcome = await executor.send(mail_payload(attachment))
    assert outcome.status == "accepted" and outcome.approval_mode == "host"
    assert dispatcher.calls == 1 and dispatcher.bytes == [b"synthetic frozen bytes"]
    assert dispatcher.attachment_paths[0] != attachment
    # Changing the policy must not turn an old operation into a fresh send/dialog.
    repeated = await MailExecutor(journal, reviewer_for("native"), dispatcher).send(
        mail_payload(attachment)
    )
    assert repeated.replayed and repeated.approval_mode is None and dispatcher.calls == 1


async def test_delegated_uncertain_send_still_cannot_retry(tmp_path: Path) -> None:
    dispatch = DispatchFixture(uncertain=True)
    executor = MailExecutor(
        OutcomeJournal(tmp_path), HostReviewer(), dispatch, approval_mode="host"
    )
    result = await executor.send(mail_payload())
    repeat = await executor.send(mail_payload())
    assert result.status == repeat.status == "outcome_unknown"
    assert repeat.replayed and dispatch.calls == 1


async def test_calendar_host_mode_runs_without_ui_and_native_mode_denial_remains(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dialogs = 0

    async def deny(
        argv: list[str], payload: bytes = b"", *, timeout: float = 15, max_bytes: int = 8_000_000
    ) -> bytes:
        nonlocal dialogs
        dialogs += 1
        preview = EventPreview.model_validate_json(payload)
        return Decision(digest=preview.digest, allow=False).model_dump_json().encode()

    monkeypatch.setattr(approval, "run_child", deny)
    bridge, dispatcher = CalendarFixture(), DispatcherFixture()
    delegated = await CalendarExecutor(
        OutcomeJournal(tmp_path / "host"),
        bridge,
        reviewer_for("host"),
        dispatcher,
        approval_mode="host",
    ).create(request())
    denied = await CalendarExecutor(
        OutcomeJournal(tmp_path / "native"), bridge, reviewer_for("native"), dispatcher
    ).create(request())
    assert delegated.status == "accepted" and delegated.approval_mode == "host"
    assert denied.status == "approval_denied" and denied.approval_mode == "native"
    assert dispatcher.calls == dialogs == 1


async def test_delegation_cannot_enable_writes_or_accept_model_consent(tmp_path: Path) -> None:
    config = loaded(ApprovalPolicy(default="host"), tmp_path)
    bridge, dispatch = FixtureBridge(), DispatchFixture()
    executor = MailExecutor(
        OutcomeJournal(tmp_path / "owned"), HostReviewer(), dispatch, approval_mode="host"
    )
    service = Service(bridge=bridge, mail_executor=executor, approval_config=config)
    denied = await service.call("mail_send", mail_payload().model_dump_json())
    assert isinstance(denied, Failure) and denied.code == "read_only"
    enabled = Service(
        read_only=False, bridge=bridge, mail_executor=executor, approval_config=config
    )
    invalid = await enabled.call(
        "mail_send", json.dumps({**mail_payload().model_dump(), "approved": True})
    )
    assert isinstance(invalid, Failure) and invalid.code == "invalid_input"
    assert bridge.calls == [] and dispatch.calls == 0 and not executor.journal.path.exists()
    closed = await Service(read_only=False, bridge=bridge, approval_config=config).call(
        "mail_send", mail_payload().model_dump_json()
    )
    assert isinstance(closed, Failure) and closed.code == "approval_unavailable"
    assert not bridge.calls


def test_reports_and_annotations_are_truthful_under_delegation(tmp_path: Path) -> None:
    service = Service(
        read_only=False,
        approval_config=loaded(ApprovalPolicy(default="host", calendar="native"), tmp_path),
        calendar_executor=CalendarExecutor(
            OutcomeJournal(tmp_path / "cal"),
            CalendarFixture(),
            NativeReviewer(),
            DispatcherFixture(),
        ),
    )
    report = {item.tool: item for item in service.approval_report().tools}
    assert report["mail_send"].mode == "host" and not report["mail_send"].server_dialog
    assert (
        report["calendar_create_event"].mode == "native"
        and report["calendar_create_event"].server_dialog
    )
    assert not report["contacts_get"].server_dialog and not report["mail_send"].executor_enabled
    tool = next(t for t in service.tools() if t.name == "mail_send")
    assert (
        tool.annotations
        and tool.annotations.destructive_hint
        and not tool.annotations.read_only_hint
    )
    assert tool.description is not None and "no server dialog" in tool.description


async def test_policy_cli_is_offline_and_bad_startup_has_no_protocol_output(tmp_path: Path) -> None:
    path = policy_file(tmp_path, '[approval]\ndefault="host"\ncalendar="native"')
    raw = await run_child(
        [
            sys.executable,
            "-m",
            "macos_personal_mcp.cli",
            "policy",
            "--config",
            str(path),
            "--enable-mail-send",
            "--enable-calendar-create",
        ]
    )
    value = ApprovalReport.model_validate_json(raw)
    assert value.config_loaded and not value.read_only
    tools = {v.tool: v for v in value.tools}
    assert tools["mail_send"].mode == "host" and tools["mail_send"].executor_enabled
    assert tools["calendar_create_event"].mode == "native"
    path.write_text('[approval]\ndefault="invalid"')
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "macos_personal_mcp.cli",
        "serve",
        "--config",
        str(path),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await child.communicate()
    assert child.returncode == 2 and not stdout and b"permission_config" in stderr
