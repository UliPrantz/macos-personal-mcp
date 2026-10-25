import json
from pathlib import Path

import pytest
from mcp import Client

from macos_personal_mcp.body_index import BodyIndex
from macos_personal_mcp.mail_native.client import NativeSearchClient
from macos_personal_mcp.mail_native.contracts import NativeSearch, NativeSearchResult
from macos_personal_mcp.models import Failure, Model
from macos_personal_mcp.process import NativeError
from macos_personal_mcp.server import create_server
from macos_personal_mcp.service import READS, SETUP, WRITES, Service
from tests.test_contracts import mail_payload


class FixtureBridge:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def call[T: Model](self, operation: str, request: Model, output: type[T]) -> T:
        self.calls.append(operation)
        if operation == "mail_list_accounts":
            return output.model_validate_json(
                '{"accounts":[{"id":"a","name":"Synthetic","emails":["sender@example.test"],"enabled":true}]}'
            )
        raise AssertionError("Unexpected native call: " + operation)


async def test_discovery_and_dispatch_read_only_both_enforced() -> None:
    bridge = FixtureBridge()
    service = Service(bridge=bridge)
    assert {t.name for t in service.tools()} == {d.name for d in READS + SETUP}
    for definition in WRITES:
        result = await service.call(definition.name, "{}")
        assert isinstance(result, Failure) and result.code == "read_only"
    assert bridge.calls == []


async def test_write_mode_alone_cannot_send_or_retry() -> None:
    bridge = FixtureBridge()
    service = Service(read_only=False, bridge=bridge)
    for _ in range(2):
        result = await service.call("mail_send", mail_payload().model_dump_json())
        assert isinstance(result, Failure) and result.code == "approval_unavailable"
    assert bridge.calls == []


@pytest.mark.parametrize("read_only", [True, False])
async def test_attendee_creation_is_excluded_in_every_mode(read_only: bool) -> None:
    bridge = FixtureBridge()
    service = Service(read_only=read_only, bridge=bridge)
    assert "calendar_create_invitation" not in {t.name for t in service.tools()}
    for _ in range(2):
        invite = await service.call(
            "calendar_create_invitation",
            json.dumps(
                {
                    "operation_id": "synthetic_invite",
                    "calendar_id": "synthetic",
                    "title": "Synthetic",
                    "start": "2026-10-23T13:00:00+01:00",
                    "end": "2026-10-23T13:30:00+01:00",
                    "invitees": ["recipient@example.test"],
                }
            ),
        )
        assert isinstance(invite, Failure) and invite.code == "unknown_tool"
    assert bridge.calls == []


async def test_enabled_legacy_search_does_not_silently_substitute_headers(tmp_path: Path) -> None:
    bridge = FixtureBridge()
    service = Service(
        bridge=bridge,
        body_index=BodyIndex(tmp_path / "owned"),
        enable_legacy_mail_search=True,
    )
    result = await service.call(
        "mail_search_legacy",
        json.dumps(
            {
                "account_id": "synthetic",
                "mailbox_path": ["Inbox"],
                "query": "body only needle",
                "since": "2026-10-01T00:00:00Z",
                "before": "2026-10-23T00:00:00Z",
            }
        ),
    )
    assert isinstance(result, Failure) and result.code == "body_source_unavailable"
    assert not result.complete and bridge.calls == []


@pytest.mark.parametrize("read_only", [True, False])
@pytest.mark.parametrize("legacy", [True, False])
async def test_search_registry_has_one_primary_and_opt_in_legacy(
    read_only: bool, legacy: bool
) -> None:
    bridge = FixtureBridge()
    service = Service(read_only=read_only, bridge=bridge, enable_legacy_mail_search=legacy)
    tools = {tool.name: tool for tool in service.tools()}
    assert len(tools) == (17 if read_only else 20) + int(legacy)
    assert "mail_search_native" not in tools
    assert ("mail_search_legacy" in tools) is legacy
    assert tools["mail_search"].input_schema == NativeSearch.model_json_schema()
    assert tools["mail_search"].output_schema == NativeSearchResult.model_json_schema()
    assert "query" in tools["mail_search"].input_schema["required"]
    assert "account_id" not in tools["mail_search"].input_schema["required"]
    assert "search_fields" in tools["mail_search"].input_schema["properties"]
    instructions = create_server(service).create_initialization_options().instructions
    assert instructions is not None and "Use mail_search " in instructions
    assert ("mail_search_legacy" in instructions) is legacy
    missing_alias = await service.call("mail_search_native", '{"query":"private"}')
    assert isinstance(missing_alias, Failure) and missing_alias.code == "unknown_tool"
    if not legacy:
        hidden = await service.call("mail_search_legacy", '{"query":"private"}')
        assert isinstance(hidden, Failure) and hidden.code == "unknown_tool"
    approval = next(t for t in service.approval_report().tools if t.tool == "mail_search_legacy")
    assert approval.exposed is legacy and approval.executor_enabled is legacy
    assert not approval.server_dialog
    assert bridge.calls == []


async def test_primary_search_dispatches_native_without_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    requests: list[NativeSearch] = []

    async def unavailable(self: NativeSearchClient, request: NativeSearch) -> NativeSearchResult:
        requests.append(request)
        raise NativeError("native_profile", "Synthetic native profile unavailable")

    monkeypatch.setattr(NativeSearchClient, "search", unavailable)
    bridge = FixtureBridge()
    service = Service(
        bridge=bridge,
        body_index=BodyIndex(tmp_path / "owned"),
        enable_legacy_mail_search=True,
    )
    result = await service.call("mail_search", '{"query":"needle","search_fields":["body"]}')
    assert isinstance(result, Failure) and result.code == "native_profile"
    assert len(requests) == 1 and requests[0].query == "needle"
    assert requests[0].search_fields == ["body"]
    assert bridge.calls == [] and not service.body_index.path.exists()


async def test_real_sdk_client_schemas_read_and_redacted_errors() -> None:
    bridge = FixtureBridge()
    async with Client(create_server(Service(bridge=bridge))) as client:
        tools = await client.list_tools()
        assert {t.name for t in tools.tools} == {d.name for d in READS + SETUP}
        for tool in tools.tools:
            assert tool.annotations is not None
            assert tool.annotations.read_only_hint is (tool.name != "request_permissions")
            assert tool.annotations.destructive_hint is False
            assert tool.input_schema["additionalProperties"] is False
        result = await client.call_tool("mail_list_accounts", {})
        assert not result.is_error
        assert result.structured_content is not None
        assert result.structured_content["accounts"][0]["id"] == "a"
        error = await client.call_tool("mail_list_accounts", {"secret": "do not echo"})
        assert error.is_error
        assert "do not echo" not in error.model_dump_json()
        for hidden_name in ("mail_search_legacy", "mail_search_native"):
            hidden = await client.call_tool(hidden_name, {"query": "needle"})
            assert hidden.is_error
            assert hidden.structured_content is not None
            assert hidden.structured_content["code"] == "unknown_tool"
    assert bridge.calls == ["mail_list_accounts"]


@pytest.mark.parametrize("name", ["mail_send", "calendar_create_event"])
def test_write_annotations_are_conservative(name: str) -> None:
    tool = next(t for t in Service(read_only=False).tools() if t.name == name)
    assert tool.annotations is not None
    assert not tool.annotations.read_only_hint
    assert tool.annotations.destructive_hint
    assert not tool.annotations.idempotent_hint
    assert tool.annotations.open_world_hint
