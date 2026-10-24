"""Opt-in reads only; an inaccessible app is a failure, never a passing capability."""

import os

import pytest

from macos_personal_mcp.models import Failure
from macos_personal_mcp.service import Service

pytestmark = [
    pytest.mark.macos,
    pytest.mark.live_read,
    pytest.mark.skipif(
        os.environ.get("MACOS_PERSONAL_MCP_LIVE_READ") != "1",
        reason="Live reads require explicit opt-in",
    ),
]


@pytest.mark.parametrize("name", ["mail_list_accounts", "calendar_list_calendars", "contacts_list"])
async def test_native_live_read(name: str) -> None:
    result = await Service().call(name, "{}")
    assert not isinstance(result, Failure), result.model_dump_json()
