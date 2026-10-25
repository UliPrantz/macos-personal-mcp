"""Synthetic permission states only; never request access to the owner's apps."""

import io
from pathlib import Path

import pytest
from mcp import Client
from pydantic import ValidationError

from macos_personal_mcp.access import CONTACTS_HOST_REQUIREMENT, access_action
from macos_personal_mcp.models import (
    ContactsBackend,
    Doctor,
    Empty,
    Failure,
    HostContext,
    Model,
    NativeAccessResult,
    NativePermissions,
    NativeReply,
    PermissionDomain,
    PermissionRequest,
    PermissionResult,
)
from macos_personal_mcp.native_access import Completion, request_access
from macos_personal_mcp.process import NativeError
from macos_personal_mcp.server import create_server
from macos_personal_mcp.service import Service


class AccessFixture:
    def __init__(self, before: str, after: str, *, complete: bool = True) -> None:
        self.current = before
        self.after = after
        self.complete = complete
        self.calls: list[PermissionDomain] = []

    def status(self, domain: PermissionDomain) -> str:
        return self.current

    def request(self, domain: PermissionDomain, completion: Completion) -> None:
        self.calls.append(domain)
        if self.complete:
            self.current = self.after
            completion(True, None)


@pytest.mark.parametrize(
    ("domain", "before", "after", "granted"),
    [
        ("calendar", "not_determined", "full_access", True),
        ("calendar", "write_only", "full_access", True),
        ("calendar", "not_determined", "denied", False),
        ("contacts", "not_determined", "limited", True),
        ("contacts", "not_determined", "authorized", True),
        ("contacts", "not_determined", "denied", False),
        ("contacts", "not_determined", "not_determined", False),
    ],
)
def test_request_requires_observed_status_not_just_success_callback(
    domain: PermissionDomain, before: str, after: str, granted: bool
) -> None:
    backend = AccessFixture(before, after)
    result = request_access(PermissionRequest(domain=domain), backend, timeout=0)
    assert backend.calls == [domain]
    assert result.before == before and result.after == after
    assert result.request_attempted and result.request_completed
    assert result.granted is granted


@pytest.mark.parametrize("domain", ["calendar", "contacts"])
@pytest.mark.parametrize("status", ["denied", "restricted", "unknown"])
def test_repeated_request_cannot_override_denial_or_restrictions(
    domain: PermissionDomain, status: str
) -> None:
    backend = AccessFixture(status, "full_access")
    result = request_access(PermissionRequest(domain=domain), backend, timeout=0)
    assert not result.request_attempted and not result.granted
    assert backend.calls == []
    guidance = access_action(domain, status)
    assert (
        guidance.action
        == {"denied": "open_settings", "restricted": "administrator", "unknown": "diagnose_host"}[
            status
        ]
    )


@pytest.mark.parametrize("backend", ["framework", "contacts-app"])
@pytest.mark.parametrize("status", ["denied", "not_determined", "unknown"])
def test_contacts_host_limit_is_conditional_and_keeps_compatible_hosts_supported(
    backend: ContactsBackend, status: str
) -> None:
    action = access_action("contacts", status, backend)
    assert CONTACTS_HOST_REQUIREMENT in action.instructions
    text = " ".join(action.instructions)
    assert "compatible responsible app" in text and "macOS user grant" in text
    assert "com.apple.security.personal-information.addressbook" in text
    assert "NSContactsUsageDescription" in text
    assert "ChatGPT Desktop 26.1021.31345" in text
    assert "when macOS attributes access to that app" in text
    assert "Settings and Automation consent cannot add them" in text
    assert "A generic denied status alone does not identify missing declarations" in text
    if status != "not_determined":
        assert action.tool is None


def test_unknown_automation_is_not_reported_as_observed_denial() -> None:
    action = access_action("contacts", "unknown", "contacts-app")
    assert action.action == "diagnose_host" and action.settings_path is None
    text = " ".join(action.instructions)
    assert "Automation status is unknown" in text
    assert "Automation is not authorized" not in text


@pytest.mark.parametrize("status", ["not_determined", "denied", "unknown", "full_access"])
def test_contacts_host_limitation_does_not_change_calendar_guidance(status: str) -> None:
    action = access_action("calendar", status)
    assert CONTACTS_HOST_REQUIREMENT not in action.instructions
    assert "Address Book" not in " ".join(action.instructions)


@pytest.mark.parametrize(
    ("domain", "status"),
    [("calendar", "full_access"), ("contacts", "authorized"), ("contacts", "limited")],
)
def test_existing_grant_does_not_prompt(domain: PermissionDomain, status: str) -> None:
    backend = AccessFixture(status, status)
    result = request_access(PermissionRequest(domain=domain), backend, timeout=0)
    assert result.granted and not result.request_attempted
    assert backend.calls == []


def test_callback_timeout_is_distinct_from_denied_access() -> None:
    backend = AccessFixture("not_determined", "authorized", complete=False)
    result = request_access(PermissionRequest(domain="contacts"), backend, timeout=0)
    assert result.request_attempted and not result.request_completed and not result.granted
    assert result.after == "not_determined"


class PermissionBridge:
    def __init__(
        self,
        calendar: str = "not_determined",
        contacts: str = "not_determined",
        result: NativeAccessResult | None = None,
        error: bool = False,
        contacts_backend: ContactsBackend = "framework",
        framework_contacts: str = "unknown",
        framework_error: bool = False,
    ) -> None:
        self.permissions = NativePermissions(
            calendar=calendar, contacts=contacts, contacts_backend=contacts_backend
        )
        self.framework_permissions = NativePermissions(
            calendar=calendar, contacts=framework_contacts
        )
        self.framework_error = framework_error
        self.result = result
        self.error = error
        self.calls: list[str] = []

    async def call[T: Model](self, operation: str, request: Model, output: type[T]) -> T:
        self.calls.append(operation)
        if self.error:
            raise NativeError("native_failure", "Synthetic native failure")
        if operation == "permissions":
            return output.model_validate_json(self.permissions.model_dump_json())
        if operation == "contacts_framework_permissions":
            if self.framework_error:
                raise NativeError("native_failure", "Synthetic framework inspection failure")
            return output.model_validate_json(self.framework_permissions.model_dump_json())
        if operation == "request_permissions" and self.result is not None:
            assert isinstance(request, PermissionRequest)
            return output.model_validate_json(self.result.model_dump_json())
        raise AssertionError("A permission operation must not read or mutate native data")


async def synthetic_host() -> HostContext:
    return HostContext(
        executable="/synthetic/python",
        process_id=10,
        parent_process_id=9,
        parent_command="/synthetic/host",
    )


async def test_doctor_is_nonprompting_and_not_determined_has_concrete_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("macos_personal_mcp.service.host_context", synthetic_host)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    bridge = PermissionBridge()
    monkeypatch.setattr("macos_personal_mcp.service.__version__", "loaded-test-version")
    result = await Service(bridge=bridge).call("doctor", "{}")
    assert isinstance(result, Doctor)
    assert result.server_version == "loaded-test-version"
    assert bridge.calls == ["permissions"]
    assert result.host is not None and result.host.parent_command == "/synthetic/host"
    for domain in ("calendar", "contacts"):
        action = next(a for a in result.next_actions if a.capability == domain)
        assert action.status == "not_determined" and action.action == "request_permission"
        assert action.tool == "request_permissions"
        assert action.arguments is not None and action.arguments.domain == domain
        assert action.settings_path is None
        assert "no Settings entry" in " ".join(action.instructions)
    missing = next(a for a in result.next_actions if a.capability == "mail_files")
    assert missing.status == "missing" and missing.settings_path is None
    assert not any(a.action == "open_settings" for a in result.next_actions)


async def test_doctor_denied_and_limited_states_remain_distinct(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("macos_personal_mcp.service.host_context", synthetic_host)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    result = await Service(bridge=PermissionBridge(calendar="denied", contacts="limited")).doctor()
    calendar = next(a for a in result.next_actions if a.capability == "calendar")
    contacts = next(a for a in result.next_actions if a.capability == "contacts")
    assert calendar.action == "open_settings" and calendar.tool is None
    assert calendar.settings_path is not None and calendar.settings_path.endswith("Calendars")
    assert contacts.action == "ready" and contacts.status == "limited"
    assert "selected contacts" in " ".join(contacts.instructions)


@pytest.mark.parametrize("framework_status", ["denied", "not_determined", "unknown", "restricted"])
async def test_automation_grant_does_not_claim_contacts_data_is_ready(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, framework_status: str
) -> None:
    monkeypatch.setattr("macos_personal_mcp.service.host_context", synthetic_host)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    bridge = PermissionBridge(
        calendar="full_access",
        contacts="authorized",
        contacts_backend="contacts-app",
        framework_contacts=framework_status,
    )
    service = Service(bridge=bridge, contacts_backend="contacts-app")
    result = await service.doctor()
    assert bridge.calls == ["permissions", "contacts_framework_permissions"]
    assert "contacts_framework_permissions" not in {t.name for t in service.tools()}
    assert result.permissions == bridge.permissions
    contacts = next(a for a in result.next_actions if a.capability == "contacts")
    assert contacts.status == "authorized" and contacts.action == "diagnose_host"
    assert contacts.tool is None and contacts.arguments is None and contacts.settings_path is None
    text = " ".join(contacts.instructions)
    assert "Underlying Contacts framework status: " + framework_status in text
    assert "Repeating Automation setup does not supply" in text
    assert "not a universal prerequisite" in text
    contacts_capability = next(
        c for c in result.capabilities if c.capability == "contacts_permission"
    )
    assert contacts_capability.state == "unverified"
    assert "Underlying Contacts framework status: " + framework_status in contacts_capability.detail
    calendar = next(a for a in result.next_actions if a.capability == "calendar")
    assert calendar.action == "ready" and calendar.status == "full_access"
    calendar_capability = next(
        c for c in result.capabilities if c.capability == "calendar_permission"
    )
    assert calendar_capability.state == "available"


@pytest.mark.parametrize("framework_status", ["authorized", "limited"])
async def test_contacts_diagnostic_grants_still_require_a_real_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, framework_status: str
) -> None:
    monkeypatch.setattr("macos_personal_mcp.service.host_context", synthetic_host)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    bridge = PermissionBridge(
        contacts="authorized", contacts_backend="contacts-app", framework_contacts=framework_status
    )
    result = await Service(bridge=bridge, contacts_backend="contacts-app").doctor()
    contacts = next(a for a in result.next_actions if a.capability == "contacts")
    assert contacts.action == "ready"
    assert "does not certify a successful data read" in " ".join(contacts.instructions)
    assert "selected contacts" in " ".join(contacts.instructions)
    assert (
        next(c for c in result.capabilities if c.capability == "native_reads").state == "unverified"
    )
    assert bridge.calls == ["permissions", "contacts_framework_permissions"]


async def test_framework_diagnostic_failure_preserves_observed_automation_grant(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("macos_personal_mcp.service.host_context", synthetic_host)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    bridge = PermissionBridge(
        contacts="authorized", contacts_backend="contacts-app", framework_error=True
    )
    result = await Service(bridge=bridge, contacts_backend="contacts-app").doctor()
    assert result.permissions == bridge.permissions
    contacts = next(a for a in result.next_actions if a.capability == "contacts")
    assert contacts.action == "diagnose_host" and contacts.tool is None
    assert "Underlying Contacts framework status: unknown" in " ".join(contacts.instructions)


async def test_automation_setup_grant_means_event_delivery_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("macos_personal_mcp.service.host_context", synthetic_host)
    native = NativeAccessResult(
        domain="contacts",
        route="contacts-app",
        before="authorized",
        after="authorized",
        request_attempted=False,
        request_completed=False,
        granted=True,
    )
    bridge = PermissionBridge(result=native)
    result = await Service(bridge=bridge, contacts_backend="contacts-app").call(
        "request_permissions", '{"domain":"contacts"}'
    )
    assert isinstance(result, PermissionResult) and result.granted
    assert result.route == "contacts-app"
    assert "Apple Events delivery only" in " ".join(result.guidance.instructions)
    assert "Run doctor" in " ".join(result.guidance.instructions)
    assert result.guidance.tool is None
    assert bridge.calls == ["request_permissions"]


def test_framework_diagnostic_worker_preserves_existing_permission_wire_schema(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from macos_personal_mcp import native_worker

    expected = NativePermissions(calendar="full_access", contacts="denied")
    monkeypatch.setattr(native_worker, "native_permissions", lambda: expected)

    def forbidden_automation() -> str:
        raise AssertionError("Framework diagnostic must not request Automation authorization")

    def forbidden_read(operation: str, payload: str) -> Model:
        raise AssertionError("Framework diagnostic must not read contact data")

    monkeypatch.setattr(
        "macos_personal_mcp.native_contacts_app.automation_status", forbidden_automation
    )
    monkeypatch.setattr("macos_personal_mcp.native_contacts_app.read_contacts", forbidden_read)
    monkeypatch.setattr(native_worker, "read_contacts", forbidden_read)
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(b"{}")))
    monkeypatch.setattr(
        "sys.argv", ["native_worker", "contacts_framework_permissions", "contacts-app"]
    )
    native_worker.main()
    reply = NativeReply.model_validate_json(capsys.readouterr().out)
    assert reply.failure is None and reply.result_json is not None
    observed = NativePermissions.model_validate_json(reply.result_json)
    assert observed == expected
    assert set(observed.model_dump()) == {"calendar", "contacts", "contacts_backend"}


async def test_framework_diagnostic_bridge_uses_nonprompting_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from macos_personal_mcp.native import NativeBridge

    calls: list[list[str]] = []
    expected = NativePermissions(calendar="full_access", contacts="denied")

    async def synthetic_child(argv: list[str], payload: bytes, *, timeout: float) -> bytes:
        calls.append(argv)
        assert timeout == 45
        assert Empty.model_validate_json(payload) == Empty()
        return NativeReply(result_json=expected.model_dump_json()).model_dump_json().encode()

    monkeypatch.setattr("macos_personal_mcp.native.run_child", synthetic_child)
    observed = await NativeBridge(contacts_backend="contacts-app").call(
        "contacts_framework_permissions", Empty(), NativePermissions
    )
    assert observed == expected
    assert calls[0][-3:] == [
        "macos_personal_mcp.native_worker",
        "contacts_framework_permissions",
        "contacts-app",
    ]


async def test_permission_inspection_failure_does_not_invent_denial(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("macos_personal_mcp.service.host_context", synthetic_host)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    result = await Service(bridge=PermissionBridge(error=True)).doctor()
    assert result.permissions is None
    assert all(
        a.action == "diagnose_host" and a.status == "unknown" for a in result.next_actions[:2]
    )


async def test_setup_tool_is_explicit_nondestructive_and_usable_in_read_only_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("macos_personal_mcp.service.host_context", synthetic_host)
    result = NativeAccessResult(
        domain="contacts",
        before="not_determined",
        after="limited",
        request_attempted=True,
        request_completed=True,
        granted=True,
    )
    bridge = PermissionBridge(result=result)
    service = Service(bridge=bridge)
    tool = next(t for t in service.tools() if t.name == "request_permissions")
    assert tool.annotations is not None
    assert not tool.annotations.read_only_hint and not tool.annotations.destructive_hint
    assert not tool.annotations.idempotent_hint
    assert "mail_send" not in {t.name for t in service.tools()}
    async with Client(create_server(service)) as client:
        valid = await client.call_tool("request_permissions", {"domain": "contacts"})
        assert not valid.is_error and valid.structured_content is not None
        assert valid.structured_content["granted"] is True
        for args in ({}, {"domain": "mail"}, {"domain": "contacts", "approved": True}):
            invalid = await client.call_tool("request_permissions", args)
            assert invalid.is_error
    assert bridge.calls == ["request_permissions"]
    record = next(t for t in service.approval_report().tools if t.tool == "request_permissions")
    assert record.exposed and record.executor_enabled and not record.server_dialog


async def test_request_timeout_says_resolve_dialog_before_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("macos_personal_mcp.service.host_context", synthetic_host)
    native = NativeAccessResult(
        domain="calendar",
        before="not_determined",
        after="not_determined",
        request_attempted=True,
        request_completed=False,
        granted=False,
    )
    result = await Service(bridge=PermissionBridge(result=native)).call(
        "request_permissions", '{"domain":"calendar"}'
    )
    assert isinstance(result, PermissionResult)
    assert result.guidance.action == "diagnose_host"
    assert "pending macOS dialog" in " ".join(result.guidance.instructions)
    assert result.guidance.tool is None


async def test_request_native_failure_provides_host_remediation() -> None:
    result = await Service(bridge=PermissionBridge(error=True)).call(
        "request_permissions", '{"domain":"calendar"}'
    )
    assert isinstance(result, Failure) and result.code == "permission_request_failed"
    assert "privacy usage descriptions" in result.message
    assert "assume a Settings entry" in result.message


def test_result_cannot_claim_granted_for_not_determined_status() -> None:
    with pytest.raises(ValidationError):
        NativeAccessResult(
            domain="contacts",
            before="not_determined",
            after="not_determined",
            request_attempted=True,
            request_completed=True,
            granted=True,
        )


async def test_completed_request_without_decision_does_not_repeat_or_invent_denial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("macos_personal_mcp.service.host_context", synthetic_host)
    native = NativeAccessResult(
        domain="contacts",
        before="not_determined",
        after="not_determined",
        request_attempted=True,
        request_completed=True,
        granted=False,
        error_code=100,
    )
    result = await Service(bridge=PermissionBridge(result=native)).call(
        "request_permissions", '{"domain":"contacts"}'
    )
    assert isinstance(result, PermissionResult) and not result.granted
    assert result.guidance.action == "diagnose_host" and result.guidance.tool is None
    assert result.error_code == 100


async def test_permission_bridge_uses_same_worker_with_human_response_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from macos_personal_mcp.models import NativeReply
    from macos_personal_mcp.native import NativeBridge

    calls: list[list[str]] = []

    async def synthetic_child(argv: list[str], payload: bytes, *, timeout: float) -> bytes:
        calls.append(argv)
        assert timeout == 105
        assert PermissionRequest.model_validate_json(payload).domain == "calendar"
        result = NativeAccessResult(
            domain="calendar",
            before="full_access",
            after="full_access",
            request_attempted=False,
            request_completed=False,
            granted=True,
        )
        return NativeReply(result_json=result.model_dump_json()).model_dump_json().encode()

    monkeypatch.setattr("macos_personal_mcp.native.run_child", synthetic_child)
    result = await NativeBridge().call(
        "request_permissions", PermissionRequest(domain="calendar"), NativeAccessResult
    )
    assert result.granted and not result.request_attempted
    assert calls[0][-3:] == ["macos_personal_mcp.native_worker", "request_permissions", "framework"]


async def test_first_contacts_refusal_without_prompt_guides_host_diagnosis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("macos_personal_mcp.service.host_context", synthetic_host)
    native = NativeAccessResult(
        domain="contacts",
        before="not_determined",
        after="denied",
        request_attempted=True,
        request_completed=True,
        granted=False,
        error_code=100,
    )
    bridge = PermissionBridge(result=native)
    result = await Service(bridge=bridge).call("request_permissions", '{"domain":"contacts"}')
    assert isinstance(result, PermissionResult) and not result.granted
    assert result.guidance.action == "diagnose_host" and result.guidance.tool is None
    text = " ".join(result.guidance.instructions)
    assert "does not prove the user declined" in text
    assert "com.apple.security.personal-information.addressbook" in text
    assert "NSContactsUsageDescription" in text
    assert "If the user actually declined" in text
    assert bridge.calls == ["request_permissions"]


def test_denial_and_stale_catalog_guidance_does_not_invent_user_choice_or_entry() -> None:
    from macos_personal_mcp.access import permission_problem

    denied = permission_problem("contacts", "denied")
    assert "does not prove the user declined" in denied
    assert "only if the responsible app/helper has an entry" in denied
    assert "diagnose the host" in denied
    undecided = permission_problem("contacts", "not_determined")
    assert "request_permissions tool is missing" in undecided
    assert "restart the existing MCP connection" in undecided
