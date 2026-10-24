import json
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

import pytest

from macos_personal_mcp.body_index import BodyIndex
from macos_personal_mcp.mime_body import decoded_body
from macos_personal_mcp.models import IndexRequest, MailScope, Metadata, Model, SourceKey
from macos_personal_mcp.process import NativeError


def scope(query: str = "") -> MailScope:
    return MailScope(
        account_id="synthetic",
        mailbox_path=["Inbox"],
        since=datetime(2026, 10, 1, tzinfo=UTC),
        before=datetime(2026, 11, 1, tzinfo=UTC),
        query=query,
    )


def message(identifier: int) -> Metadata:
    return Metadata(
        local_id=identifier,
        message_id=f"synthetic-{identifier}@example.test",
        subject="Header without the secret",
        sender="synthetic@example.test",
        received_at=datetime(2026, 10, 20, tzinfo=UTC),
        read=False,
    )


def mime(identifier: int, body: str) -> str:
    value = EmailMessage()
    value["Message-ID"] = f"<synthetic-{identifier}@example.test>"
    value.set_content(body, charset="utf-8", cte="quoted-printable")
    return value.as_string()


class FixtureSource:
    def __init__(self) -> None:
        self.messages = [message(1), message(2)]
        self.bodies = {
            1: mime(1, "café Unicode " + "long prefix " * 5000 + " tail secret marker"),
            2: mime(2, "Another body distinct content"),
        }
        self.unavailable: set[int] = set()
        self.calls: list[str] = []

    async def call[T: Model](self, operation: str, request: Model, output: type[T]) -> T:
        self.calls.append(operation)
        if operation == "mail_inventory":
            return output.model_validate_json(
                json.dumps(
                    {
                        "messages": [m.model_dump(mode="json") for m in self.messages],
                        "total_matches": len(self.messages),
                        "next_offset": None,
                        "observed_at": datetime.now(UTC).isoformat(),
                        "complete": True,
                        "scope": "synthetic",
                    }
                )
            )
        assert operation == "mail_get_source" and isinstance(request, SourceKey)
        if request.local_id in self.unavailable:
            raise NativeError("deadline", "Synthetic unavailable complete body")
        return output.model_validate_json(
            json.dumps(
                {
                    "message_id": request.expected_message_id,
                    "source": self.bodies[request.local_id],
                    "read_before": False,
                    "read_after": False,
                }
            )
        )


async def test_resumable_complete_long_unicode_phrase_negative_and_read_only_search(
    tmp_path: Path,
) -> None:
    source = FixtureSource()
    index = BodyIndex(tmp_path / "owned")
    first = await index.refresh(IndexRequest(scope=scope(), max_messages=1), source)
    assert first.indexed == 1 and first.pending == 1 and not first.complete
    with pytest.raises(NativeError, match="incomplete"):
        await index.search(scope('"tail secret marker"'), source)
    final = await index.refresh(IndexRequest(scope=scope(), max_messages=1), source)
    assert final.complete and final.indexed == 2
    before = index.path.stat().st_mtime_ns
    result = await index.search(scope('"tail secret marker"'), source)
    assert result.complete and result.total_matches == 1 and result.messages[0].local_id == 1
    assert (await index.search(scope("CAFE"), source)).total_matches == 1
    assert (await index.search(scope("nonexistentzzzz"), source)).total_matches == 0
    assert index.path.stat().st_mtime_ns == before
    assert source.calls.count("mail_get_source") == 2


async def test_missing_bodies_and_new_mail_cannot_produce_false_complete_zero(
    tmp_path: Path,
) -> None:
    source = FixtureSource()
    source.unavailable = {2}
    index = BodyIndex(tmp_path / "owned")
    progress = await index.refresh(IndexRequest(scope=scope()), source)
    assert progress.unavailable == 1 and not progress.complete
    with pytest.raises(NativeError, match="incomplete"):
        await index.search(scope("nonexistent"), source)
    source.unavailable.clear()
    assert (await index.refresh(IndexRequest(scope=scope()), source)).complete
    source.messages.append(message(3))
    source.bodies[3] = mime(3, "new body")
    with pytest.raises(NativeError, match="inventory changed"):
        await index.search(scope("new"), source)
    assert (await index.refresh(IndexRequest(scope=scope()), source)).complete
    assert (await index.search(scope("new"), source)).total_matches == 1
    source.messages = [message(3)]
    assert (await index.refresh(IndexRequest(scope=scope()), source)).indexed == 1
    assert (await index.search(scope("tail"), source)).total_matches == 0


async def test_expired_snapshot_fails_before_native_reads(tmp_path: Path) -> None:
    source = FixtureSource()
    index = BodyIndex(tmp_path / "owned")
    await index.refresh(IndexRequest(scope=scope()), source)
    with index.connection(write=True) as connection:
        connection.execute(
            "UPDATE scopes SET indexed_at=?",
            ((datetime.now(UTC) - timedelta(hours=2)).isoformat(),),
        )
        connection.commit()
    count = len(source.calls)
    with pytest.raises(NativeError, match="freshness window"):
        await index.search(scope("anything"), source)
    assert len(source.calls) == count


def test_mime_alternatives_nested_attachment_and_html_only() -> None:
    value = EmailMessage()
    value["Message-ID"] = "<synthetic@example.test>"
    value.set_content("plain café", charset="utf-8", cte="base64")
    value.add_alternative(
        "<html><style>hidden-css</style><p>HTML &amp; résumé</p><script>hidden-code</script></html>",
        subtype="html",
    )
    value.add_attachment(
        b"attachment-only-needle", maintype="text", subtype="plain", filename="test.txt"
    )
    text = decoded_body(value.as_string(), "synthetic@example.test")
    assert "plain café" in text and "HTML & résumé" in text
    assert all(
        needle not in text for needle in ["hidden-css", "hidden-code", "attachment-only-needle"]
    )
    html = EmailMessage()
    html.set_content("<p>Only HTML</p>", subtype="html")
    assert "Only HTML" in decoded_body(html.as_string())


@pytest.mark.parametrize(
    "source",
    [
        "Content-Type: text/plain; charset=unknown-charset\n\nbody",
        "Content-Type: application/pkcs7-mime\n\nencrypted",
        "Message-ID: <wrong@example.test>\n\nbody",
    ],
)
def test_undecodable_encrypted_or_identity_mismatch_is_not_an_empty_body(source: str) -> None:
    with pytest.raises(NativeError):
        decoded_body(source, "synthetic@example.test")


async def test_rebuild_rechecks_body_bytes_and_does_not_duplicate_rebuilt_local_ids(
    tmp_path: Path,
) -> None:
    source = FixtureSource()
    index = BodyIndex(tmp_path / "owned")
    await index.refresh(IndexRequest(scope=scope()), source)
    source.bodies[1] = mime(1, "replacement body after explicit rebuild")
    await index.refresh(IndexRequest(scope=scope(), rebuild=True, max_messages=1), source)
    assert (await index.refresh(IndexRequest(scope=scope()), source)).complete
    assert (await index.search(scope('"replacement body"'), source)).total_matches == 1
    source.messages = [message(3), message(2)]
    source.bodies[3] = mime(3, "moved local identity")
    final = await index.refresh(IndexRequest(scope=scope()), source)
    assert final.complete and final.indexed == 2
    assert (await index.search(scope('"replacement body"'), source)).total_matches == 0
