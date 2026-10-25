import os
import sys
from pathlib import Path
from typing import Literal

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client

from macos_personal_mcp.models import ContactsBackend
from macos_personal_mcp.process import run_child
from macos_personal_mcp.service import READS, SETUP


@pytest.mark.parametrize("mode", ["auto", "legacy"])
@pytest.mark.parametrize("backend", ["framework", "contacts-app"])
async def test_real_stdio_sdk_discovery_validation_and_closed_write_gate(
    mode: Literal["auto", "legacy"],
    backend: ContactsBackend,
    tmp_path: Path,
) -> None:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "macos_personal_mcp.cli",
            "serve",
            "--read-only",
            "--contacts-backend",
            backend,
            "--config",
            str(tmp_path / "permissions.toml"),
        ],
        env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
        cwd=tmp_path,
    )
    (tmp_path / "permissions.toml").write_text('[approval]\ndefault="native"\n')
    async with Client(stdio_client(parameters), mode=mode, read_timeout_seconds=10) as client:
        tools = await client.list_tools()
        assert {t.name for t in tools.tools} == {d.name for d in READS + SETUP}
        for tool in tools.tools:
            if tool.name.startswith("contacts_") or tool.name == "request_permissions":
                assert tool.description is not None
                assert "com.apple.security.personal-information.addressbook" in tool.description
                assert "NSContactsUsageDescription" in tool.description
                assert "ChatGPT Desktop 26.1021.31345" in tool.description
                if backend == "contacts-app":
                    assert "Automation" in tool.description
        # Blocked/invalid tools never contact the owner's native apps in default tests.
        invalid = await client.call_tool("mail_get_message", {"local_id": "1"})
        assert invalid.is_error
        denied = await client.call_tool("mail_send", {})
        assert denied.is_error
        assert denied.structured_content is not None
        assert denied.structured_content["code"] == "read_only"
        for hidden_name in ("mail_search_legacy", "mail_search_native"):
            hidden = await client.call_tool(hidden_name, {"query": "needle"})
            assert hidden.is_error
            assert hidden.structured_content is not None
            assert hidden.structured_content["code"] == "unknown_tool"


async def test_eof_exits_without_protocol_noise(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parents[1] / "src"))
    config = tmp_path / "permissions.toml"
    config.write_text('[approval]\ndefault="native"\n')
    result = await run_child(
        [sys.executable, "-m", "macos_personal_mcp.cli", "serve", "--config", str(config)],
        timeout=5,
    )
    assert result == b""
    assert "PYTHONPATH" in os.environ
