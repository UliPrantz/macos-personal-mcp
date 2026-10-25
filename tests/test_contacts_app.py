import json
import threading
from dataclasses import dataclass, field

import pytest
from Foundation import NSAppleEventDescriptor as Descriptor
from Foundation import NSError
from pydantic import JsonValue

from macos_personal_mcp.access import access_action
from macos_personal_mcp.contacts_app import COLUMNS, read_contacts
from macos_personal_mcp.models import (
    Contact,
    Contacts,
    Empty,
    Model,
    NativeAccessResult,
    NativeReply,
    PermissionResult,
)
from macos_personal_mcp.native import NativeBridge
from macos_personal_mcp.native_contacts_app import (
    automation_status,
    code,
    descriptor_value,
    read_reply,
    request_automation_access,
)
from macos_personal_mcp.process import NativeError
from macos_personal_mcp.service import Service


@dataclass
class Reader:
    columns: dict[tuple[str, str | None], list[JsonValue]]
    calls: list[tuple[str, str | None]] = field(default_factory=list[tuple[str, str | None]])
    change_ids: bool = False

    def read(self, property_code: str, element: str | None = None) -> list[JsonValue]:
        spec = (property_code, element)
        self.calls.append(spec)
        rows = self.columns[spec]
        if self.change_ids and spec == COLUMNS["id"] and self.calls.count(spec) == 2:
            return list(reversed(rows))
        return rows


def fixture() -> Reader:
    columns: dict[tuple[str, str | None], list[JsonValue]] = {}
    for spec in COLUMNS.values():
        columns[spec] = [[], []] if spec[1] is not None else ["", ""]
    columns[COLUMNS["id"]] = ["record-b", "record-a"]
    columns[COLUMNS["name"]] = ["Zoë 同名", "Zoë 同名"]
    columns[COLUMNS["first_name"]] = ["Zoë", "Zoë"]
    columns[COLUMNS["email_values"]] = [["first@example.test"], ["second@example.test"]]
    columns[COLUMNS["email_labels"]] = [["work"], ["home"]]
    columns[COLUMNS["phone_values"]] = [["+44 000 123"], []]
    columns[COLUMNS["phone_labels"]] = [["mobile"], []]
    columns[COLUMNS["address_labels"]] = [["home"], []]
    for name in ("street", "city", "state", "postal_code", "country", "country_code"):
        columns[COLUMNS[name]] = [["synthetic " + name], []]
    return Reader(columns)


def test_duplicate_candidates_unicode_details_and_pagination_preserve_identity() -> None:
    page = read_contacts("contacts_list", '{"limit":1}', fixture())
    assert isinstance(page, Contacts)
    assert page.complete and page.total_matches == 2 and page.next_offset == 1
    assert page.contacts[0].id == "contacts-app:record-a"
    assert page.contacts[0].emails[0].value == "second@example.test"
    second = read_contacts("contacts_list", '{"offset":1,"limit":1}', fixture())
    assert isinstance(second, Contacts)
    assert second.next_offset is None
    assert second.contacts[0].postal_addresses[0].street == "synthetic street"
    assert second.contacts[0].phones[0].label == "mobile"


@pytest.mark.parametrize("query", ["FIRST@EXAMPLE.TEST", "+44 000", "zoë"])
def test_name_email_and_phone_search(query: str) -> None:
    result = read_contacts("contacts_search", json.dumps({"query": query}), fixture())
    assert isinstance(result, Contacts) and result.total_matches > 0


def test_negative_is_a_successful_search_and_exact_get_rejects_other_backend_first() -> None:
    reader = fixture()
    result = read_contacts("contacts_search", '{"query":"absent token"}', reader)
    assert isinstance(result, Contacts) and result.complete and result.contacts == []
    assert len(reader.calls) == len(COLUMNS) + 1
    exact = read_contacts("contacts_get", '{"contact_id":"contacts-app:record-b"}', fixture())
    assert isinstance(exact, Contact) and exact.emails[0].value == "first@example.test"
    foreign = fixture()
    with pytest.raises(NativeError, match="another Contacts backend"):
        read_contacts("contacts_get", '{"contact_id":"native-unified-id"}', foreign)
    assert foreign.calls == []


@pytest.mark.parametrize(
    "failure", ["order", "missing_column", "nested_count", "duplicate_id", "scalar"]
)
def test_incomplete_or_changing_columns_fail_instead_of_empty_or_partial(failure: str) -> None:
    reader = fixture()
    if failure == "order":
        reader.change_ids = True
    elif failure == "missing_column":
        reader.columns[COLUMNS["name"]] = []
    elif failure == "nested_count":
        reader.columns[COLUMNS["email_labels"]] = [[], []]
    elif failure == "duplicate_id":
        reader.columns[COLUMNS["id"]] = ["same", "same"]
    else:
        reader.columns[COLUMNS["street"]] = [123, []]
    with pytest.raises(NativeError):
        read_contacts("contacts_list", "{}", reader)


@pytest.mark.parametrize("status", ["denied", "not_determined", "not_running", "unknown"])
def test_ungranted_read_stops_before_any_event_or_prompt(
    status: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from macos_personal_mcp import native_contacts_app as native

    monkeypatch.setattr(native, "automation_status", lambda: status)

    def unexpected(self: object, property_code: str, element: str | None = None) -> list[JsonValue]:
        pytest.fail("An ungranted read must not dispatch an Apple event")

    monkeypatch.setattr(native.AppleEventsReader, "read", unexpected)
    with pytest.raises(NativeError, match="ordinary reads do not prompt"):
        native.read_contacts("contacts_list", "{}")


@dataclass
class ReplyEvent:
    reply: Descriptor
    options: int = 0

    def sendEventWithOptions_timeout_error_(
        self, options: int, timeout: float, error: None
    ) -> tuple[Descriptor | None, NSError | None]:
        self.options = options
        assert timeout == 5.0
        return self.reply, None


def test_revocation_after_preflight_still_forbids_prompt_and_propagates_failure() -> None:
    reply = Descriptor.appleEventWithEventClass_eventID_targetDescriptor_returnID_transactionID_(
        code("aevt"), code("ansr"), Descriptor.nullDescriptor(), -1, 0
    )
    reply.setParamDescriptor_forKeyword_(Descriptor.descriptorWithInt32_(-1744), code("errn"))
    event = ReplyEvent(reply)
    with pytest.raises(NativeError, match="rejected a read"):
        read_reply(event)
    assert event.options & 0x00020000  # Apple's kAEDoNotPromptForUserConsent.
    assert event.options & 0x00000010  # kAENeverInteract.


def test_unexpected_descriptor_is_not_coerced_into_missing_data() -> None:
    with pytest.raises(NativeError, match="unexpected field type"):
        descriptor_value(Descriptor.descriptorWithInt32_(123))


def test_nonprompting_preflight_and_automation_specific_guidance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from macos_personal_mcp import native_contacts_app as native

    calls: list[bool] = []

    def preflight(ask: bool = False) -> int:
        calls.append(ask)
        return -1744

    monkeypatch.setattr(native, "permission_code", preflight)
    assert automation_status() == "not_determined" and calls == [False]
    action = access_action("contacts", "not_determined", "contacts-app")
    assert action.tool == "request_permissions"
    assert "Automation" in " ".join(action.instructions)
    denied = access_action("contacts", "denied", "contacts-app")
    assert denied.settings_path is not None and denied.settings_path.endswith("Automation")
    service = Service(contacts_backend="contacts-app")
    assert len(service.tools()) == 17
    description = next(t.description for t in service.tools() if t.name == "contacts_list")
    assert description is not None and "not unified" in description


async def test_selected_backend_reaches_bounded_worker_without_model_route_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def child(argv: list[str], payload: bytes, *, timeout: float) -> bytes:
        assert argv[-2:] == ["contacts_list", "contacts-app"] and timeout == 45
        result = Contacts(contacts=[], total_matches=0, next_offset=None, complete=True)
        return NativeReply(result_json=result.model_dump_json()).model_dump_json().encode()

    monkeypatch.setattr("macos_personal_mcp.native.run_child", child)
    result = await NativeBridge("contacts-app").call("contacts_list", Empty(), Contacts)
    assert result.complete


@pytest.mark.parametrize("before", ["authorized", "denied", "not_determined"])
def test_only_explicit_undecided_setup_requests_consent_off_main_thread(
    before: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from macos_personal_mcp import native_contacts_app as native

    state = {"code": {"authorized": 0, "denied": -1743, "not_determined": -1744}[before]}
    calls: list[bool] = []

    def preflight(ask: bool = False) -> int:
        calls.append(ask)
        if ask:
            assert threading.current_thread() is not threading.main_thread()
            state["code"] = 0
        return state["code"]

    monkeypatch.setattr(native, "permission_code", preflight)
    result = request_automation_access()
    assert result.route == "contacts-app" and result.before == before
    assert result.request_attempted == (before == "not_determined")
    assert calls.count(True) == (1 if before == "not_determined" else 0)


class SetupBridge:
    async def call[T: Model](self, operation: str, request: Model, output: type[T]) -> T:
        result = NativeAccessResult(
            domain="contacts",
            route="contacts-app",
            before="authorized",
            after="authorized",
            request_attempted=False,
            request_completed=False,
            granted=True,
        )
        return output.model_validate_json(result.model_dump_json())


async def test_service_retains_permission_route_instead_of_defaulting_to_framework() -> None:
    result = await Service(contacts_backend="contacts-app", bridge=SetupBridge()).call(
        "request_permissions", '{"domain":"contacts"}'
    )
    assert isinstance(result, PermissionResult) and result.route == "contacts-app"
    assert "Automation" in " ".join(result.guidance.instructions)
