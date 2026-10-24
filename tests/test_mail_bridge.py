"""Execute the fixed JXA reader against synthetic Mail objects only."""

import json
import sys
from importlib.resources import files
from typing import Literal

import pytest

from macos_personal_mcp.models import Failure, Message, MessageSource
from macos_personal_mcp.process import run_child

FAKE_MAIL = b"""
var fakeMessage = {
    id: function () { return 7; },
    messageId: function () { return 'exact@example.test'; },
    subject: function () { return 'Synthetic'; },
    sender: function () { return 'sender@example.test'; },
    dateReceived: function () { return new Date('2026-10-09T00:00:00Z'); },
    readStatus: function () { return false; },
    content: function () { return 'Synthetic body'; },
    allHeaders: function () { return 'Message-ID: <exact@example.test>'; },
    source: function () { return 'Message-ID: <exact@example.test>\\n\\nSynthetic body'; },
    mailAttachments: function () { return []; }
};
var syntheticApplication = function () {
    return {messages: {byId: function (id) {
        if (id !== 7) throw Error('Unexpected synthetic selector');
        return fakeMessage;
    }}};
};
"""


@pytest.mark.skipif(sys.platform != "darwin", reason="JXA requires macOS")
@pytest.mark.parametrize("operation", ["mail_get_message", "mail_get_source"])
@pytest.mark.parametrize(
    ("identity", "accepted"),
    [
        ("exact@example.test", True),
        ("<exact@example.test>", True),
        ("wrong@example.test", False),
        ("<<exact@example.test>>", False),
        (" exact@example.test", False),
        ("<exact@example.test", False),
    ],
)
async def test_native_search_identity_is_accepted_without_weakening_identity_checks(
    operation: Literal["mail_get_message", "mail_get_source"], identity: str, accepted: bool
) -> None:
    bridge = files("macos_personal_mcp").joinpath("bridge.js").read_bytes()
    # Replace the call sites, rather than relying on shadowing JXA's native
    # Application binding. These tests can never resolve an actual native app.
    source = FAKE_MAIL + bridge.replace(b"Application(", b"syntheticApplication(")
    request: dict[str, object] = {
        "account_id": "__local__",
        "mailbox_path": [],
        "local_id": 7,
        "expected_message_id": identity,
        "body_chars": 2000,
    }
    arguments = ["/usr/bin/osascript", "-l", "JavaScript", "-", operation, json.dumps(request)]
    raw = await run_child(arguments, source)
    if not accepted:
        assert Failure.model_validate_json(raw).code == "message_identity"
        return
    reply = (
        Message.model_validate_json(raw)
        if operation == "mail_get_message"
        else MessageSource.model_validate_json(raw)
    )
    assert reply.read_before is reply.read_after is False
    assert (reply.body if isinstance(reply, Message) else reply.source).endswith("Synthetic body")
