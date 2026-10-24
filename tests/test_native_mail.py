"""Synthetic native-store tests. No owner's Mail, Spotlight or permissions."""

import asyncio
import json
import plistlib
import sqlite3
import struct
import time
from contextlib import ExitStack, closing
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path

import pytest
from pydantic import ValidationError

from macos_personal_mcp.mail_native.alphabet import ALPHABET
from macos_personal_mcp.mail_native.catalogue import Catalogue
from macos_personal_mcp.mail_native.checkpoint import Checkpoint
from macos_personal_mcp.mail_native.client import NativeSearchClient
from macos_personal_mcp.mail_native.common import Budget, leb, variable
from macos_personal_mcp.mail_native.contracts import NativeSearch
from macos_personal_mcp.mail_native.engine import Engine, Query
from macos_personal_mcp.mail_native.identities import Inventory, merge, page
from macos_personal_mcp.mail_native.terms import Segment, Term, encode, posting_chunk
from macos_personal_mcp.mime_body import decoded_bytes
from macos_personal_mcp.process import NativeError
from macos_personal_mcp.service import Service


def budget() -> Budget:
    return Budget(time.monotonic() + 10)


def vi(value: int) -> bytes:
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def prefix(value: int) -> bytes:
    if value < 128:
        return bytes([value])
    if value < 16384:
        return bytes([128 | (value >> 8), value & 255])
    raise ValueError("Fixture exceeds small prefix integer range")


def native_header(generation: int = 3, flags: int = 2) -> bytes:
    values = [2, 3, 4] + [0] * 27
    values[14:17] = [128, 128, 128]
    raw = b"".join(vi(v) for v in values)
    size = 24 + len(raw)
    return (
        struct.pack("<5I", 114, 0xC001D00D, flags, generation, size) + raw + struct.pack("<I", size)
    ).ljust(4096, b"\0")


def checkpoint_files(root: Path) -> None:
    root.mkdir(exist_ok=True)
    (root / "indexState").write_bytes(struct.pack("<7I", 5, 10, 9, 1, 0, 1, 0))
    for name in ("indexHead", "shadowIndexHead"):
        (root / f"0.{name}").write_bytes(native_header())
    for name in (
        "indexDirectory",
        "indexCompactDirectory",
        "indexArrays",
        "indexTermIds",
        "indexPostings",
        "indexPositions",
    ):
        (root / f"0.{name}").write_bytes(bytes(4096))
    (root / "0.shadowIndexGroups").write_bytes(bytes([0, 1, 0x20, 0]))
    (root / "0.indexIds").write_bytes(struct.pack(">4Q", 0, 101, 102, 0))


def mail_files(root: Path, count: int = 3) -> None:
    (root / "MailData").mkdir(parents=True)
    c = sqlite3.connect(root / "MailData/Envelope Index")
    c.executescript("""
    CREATE TABLE messages(ROWID INTEGER PRIMARY KEY,global_message_id,mailbox,subject_prefix,subject,
      sender,date_received,remote_id,conversation_id,read,flags,deleted,searchable_message);
    CREATE TABLE mailboxes(ROWID INTEGER PRIMARY KEY,url);
    CREATE TABLE subjects(ROWID INTEGER PRIMARY KEY,subject);
    CREATE TABLE addresses(ROWID INTEGER PRIMARY KEY,address);
    CREATE TABLE message_global_data(ROWID INTEGER PRIMARY KEY,message_id_header);
    CREATE TABLE searchable_messages(ROWID INTEGER PRIMARY KEY,message_body_indexed);
    INSERT INTO mailboxes VALUES(1,'imap://synthetic/Inbox');
    INSERT INTO subjects VALUES(1,'header-only-secret');
    INSERT INTO addresses VALUES(1,'sender@example.test');
    """)
    directory = root / "synthetic/Inbox.mbox/Data/Messages"
    directory.mkdir(parents=True)
    for key in range(1, count + 1):
        c.execute(
            "INSERT INTO messages VALUES(?,?,1,'',1,1,?,?,123,0,0,0,?)",
            (key, key, 100 + key, key, key),
        )
        c.execute(
            "INSERT INTO message_global_data VALUES(?,?)", (key, f"message-{key}@example.test")
        )
        c.execute("INSERT INTO searchable_messages VALUES(?,1)", (key,))
        message = EmailMessage()
        message["Message-ID"] = f"<message-{key}@example.test>"
        message.set_content(
            "Café don't merge labels. Tail secret marker"
            if key != 2
            else "Wrong marker secret tail"
        )
        raw = message.as_bytes()
        trailer = plistlib.dumps(
            {"remote-id": key, "date-received": 100 + key, "conversation-id": 123}
        )
        (directory / f"{key}.emlx").write_bytes(str(len(raw)).encode() + b" \n" + raw + trailer)
    c.commit()
    c.close()


def test_query_contract_unicode_phrases_and_rejected_fts() -> None:
    assert Query('café "tail secret marker"').matches("CAFE\u0301\nTail secret marker")
    assert not Query('"tail secret marker"').matches("marker secret tail")
    assert Query("don't").matches("we DON'T merge")
    assert not Query("don't").matches("dont")
    for value in ['"unclosed', "body OR tail", "body*", "sender:someone", '""', "   "]:
        with pytest.raises(NativeError):
            Query(value)
    for values in (
        {"query": "a", "offset": 1},
        {"query": "a", "mailbox_path": ["Inbox"]},
        {"query": "a", "since": "2026-01-01T00:00:00"},
        {"query": "a", "search_fields": list[str]()},
        {"query": "a", "search_fields": ["body", "body"]},
        {"query": "a", "search_fields": ["recipient"]},
    ):
        with pytest.raises(ValidationError):
            NativeSearch.model_validate(values)


def test_combined_fields_phrases_excerpts_and_unavailable_bodies(tmp_path: Path) -> None:
    mail_files(tmp_path)
    engine = Engine(tmp_path, tmp_path / "no-index")
    combined = engine.search(NativeSearch(query="header café"), time.monotonic() + 10)
    assert combined.version == "native-mail-v2" and combined.total_matches == 2
    assert combined.header_matches == 0 and combined.searched_headers == 3
    assert combined.matches[0].matched_fields == ["subject", "body"]
    assert combined.matches[0].excerpt_field == "body"
    assert combined.matches[0].excerpt is not None and "café" in combined.matches[0].excerpt
    for query in ('"header café"', "header café absent"):
        result = engine.search(NativeSearch(query=query), time.monotonic() + 10)
        assert result.total_matches == 0 and result.execution_complete
    body_only = engine.search(
        NativeSearch(query="header café", search_fields=["body"]), time.monotonic() + 10
    )
    assert body_only.total_matches == 0 and body_only.searched_headers == 0
    sender = engine.search(
        NativeSearch(query='"sender@example.test"', search_fields=["sender"]),
        time.monotonic() + 10,
    )
    assert sender.total_matches == 3 and sender.backend == "catalogue-only"
    assert sender.matches[0].matched_fields == ["sender"] and sender.searched_bodies == 0
    for path in (tmp_path / "synthetic/Inbox.mbox/Data/Messages").glob("*.emlx"):
        path.unlink()
    # Two predicates can be proved in distinct headers without reading any body.
    header = engine.search(NativeSearch(query="header sender"), time.monotonic() + 10)
    assert header.total_matches == 3 and header.header_matches == 3
    assert header.searched_bodies == header.unavailable_bodies == 0
    assert header.matches[0].matched_fields == ["subject", "sender"]
    assert header.execution_complete and not header.exhaustive
    assert (
        engine.search(NativeSearch(query='"secret sender"'), time.monotonic() + 10).total_matches
        == 0
    )


def test_headers_have_no_body_cap_or_spotlight_dependency_and_bind_cursor(tmp_path: Path) -> None:
    mail_files(tmp_path)
    with closing(sqlite3.connect(tmp_path / "MailData/Envelope Index")) as connection, connection:
        # Metadata-only rows deliberately have no MIME files, RFC or native index.
        for key in range(4, 2105):
            connection.execute(
                "INSERT INTO messages VALUES(?,NULL,1,'',1,1,?,NULL,123,0,0,0,NULL)",
                (key, 100 + key),
            )
    engine = Engine(tmp_path, tmp_path / "no-index")
    request = NativeSearch(query="header", limit=1)
    result = engine.search(request, time.monotonic() + 10)
    assert result.total_matches == result.header_matches == 2104
    assert result.searched_headers == 2104 and result.backend == "catalogue-only"
    assert result.candidate_messages == result.searched_bodies == 0
    assert result.execution_complete and result.next_offset == 1
    page = engine.search(
        request.model_copy(update={"offset": 2001, "snapshot": result.snapshot}),
        time.monotonic() + 10,
    )
    assert page.matches[0].local_id == 103
    with pytest.raises(NativeError, match="Source or query changed"):
        engine.search(
            request.model_copy(
                update={"offset": 1, "snapshot": result.snapshot, "search_fields": ["subject"]}
            ),
            time.monotonic() + 10,
        )
    negative = engine.search(
        NativeSearch(query="absent", search_fields=["subject", "sender"]), time.monotonic() + 10
    )
    assert negative.total_matches == 0 and negative.execution_complete
    assert negative.backend == "catalogue-only"


def test_header_proof_survives_another_rows_body_failure(tmp_path: Path) -> None:
    mail_files(tmp_path)
    with closing(sqlite3.connect(tmp_path / "MailData/Envelope Index")) as connection, connection:
        connection.execute("INSERT INTO subjects VALUES(2,'tail')")
        connection.execute("UPDATE messages SET subject=2 WHERE ROWID=1")
    directory = tmp_path / "synthetic/Inbox.mbox/Data/Messages"
    (directory / "1.emlx").unlink()
    (directory / "2.emlx").unlink()
    result = Engine(tmp_path).search(NativeSearch(query="tail"), time.monotonic() + 10)
    assert {item.local_id for item in result.matches} == {1, 3}
    assert result.header_matches == 1 and result.searched_bodies == 1
    assert result.unavailable_bodies == 1 and not result.execution_complete
    assert result.matches[-1].matched_fields == ["subject"]


def test_fuzzy_header_evidence_and_unicode_excerpts_are_isolated(tmp_path: Path) -> None:
    mail_files(tmp_path)
    with closing(sqlite3.connect(tmp_path / "MailData/Envelope Index")) as connection, connection:
        connection.execute("INSERT INTO subjects VALUES(2,'tall Straße')")
        connection.execute("UPDATE messages SET subject=2 WHERE ROWID=1")
    engine = Engine(tmp_path)
    fuzzy = engine.search(NativeSearch(query="tall", fuzzy_distance=1), time.monotonic() + 10)
    assert fuzzy.total_matches == 3 and fuzzy.matched_spellings == ["tail", "tall"]
    assert fuzzy.header_matches == 1
    assert fuzzy.matches[-1].matched_fields == ["subject"]
    unicode = engine.search(NativeSearch(query="strasse"), time.monotonic() + 10)
    assert unicode.total_matches == 1 and unicode.matches[0].excerpt == "tall strasse"


def test_small_scope_filters_pagination_fresh_arrival_delete_and_flags(tmp_path: Path) -> None:
    mail_files(tmp_path)
    engine = Engine(tmp_path, tmp_path / "absent-spotlight")
    request = NativeSearch(
        query='"tail secret marker"',
        since=datetime.fromtimestamp(101, UTC),
        before=datetime.fromtimestamp(104, UTC),
        limit=1,
    )
    first = engine.search(request, time.monotonic() + 10)
    assert first.backend == "direct-mime" and first.catalogue_messages == 3
    assert first.total_matches == 2 and first.matches[0].local_id == 3 and first.next_offset == 1
    assert first.execution_complete and first.flags_unchanged and not first.exhaustive
    second = engine.search(
        request.model_copy(update={"offset": 1, "snapshot": first.snapshot}), time.monotonic() + 10
    )
    assert second.matches[0].local_id == 1
    negative = engine.search(
        NativeSearch(query='"header-only-secret"', search_fields=["body"]), time.monotonic() + 10
    )
    assert negative.total_matches == 0 and negative.execution_complete
    connection = sqlite3.connect(tmp_path / "MailData/Envelope Index")
    assert connection.execute("SELECT SUM(read),SUM(flags) FROM messages").fetchone() == (0, 0)
    connection.execute("UPDATE messages SET deleted=1 WHERE ROWID=3")
    connection.commit()
    with pytest.raises(NativeError, match="Source or query changed"):
        engine.search(
            request.model_copy(update={"offset": 1, "snapshot": first.snapshot}),
            time.monotonic() + 10,
        )
    refreshed = engine.search(request, time.monotonic() + 10)
    assert refreshed.catalogue_messages == 2 and refreshed.total_matches == 1
    connection.execute("UPDATE messages SET deleted=0 WHERE ROWID=3")
    connection.commit()
    connection.close()
    assert engine.search(request, time.monotonic() + 10).total_matches == 2


def test_native_binding_missing_rfc_tampered_uid_and_unavailable(tmp_path: Path) -> None:
    mail_files(tmp_path)
    c = sqlite3.connect(tmp_path / "MailData/Envelope Index")
    c.execute("UPDATE message_global_data SET message_id_header=NULL WHERE ROWID=1")
    c.commit()
    cat = Catalogue(tmp_path, budget())
    rows = cat.rows(NativeSearch(query="tail"))
    one = next(r for r in rows if r.local_id == 1)
    assert "Tail secret marker" in cat.body(one)[0]
    cat.close()
    c.execute("UPDATE messages SET remote_id=99 WHERE ROWID=1")
    c.commit()
    cat = Catalogue(tmp_path, budget())
    one = next(r for r in cat.rows(NativeSearch(query="tail")) if r.local_id == 1)
    with pytest.raises(NativeError, match="Native UID/date/conversation mismatch"):
        cat.body(one)
    cat.close()
    c.close()
    (tmp_path / "synthetic/Inbox.mbox/Data/Messages/2.emlx").unlink()
    result = Engine(tmp_path).search(NativeSearch(query="tail"), time.monotonic() + 10)
    assert result.unavailable_bodies == 2 and not result.execution_complete
    assert result.error_counts == {"message_identity": 1, "body_unavailable": 1}


def test_partial_mime_visibility_adjacent_links_attachments_and_charsets(tmp_path: Path) -> None:
    message = EmailMessage()
    message["Message-ID"] = "<original@example.test>"
    message.set_content("<style>hidden</style><p><a>one</a><a>two</a> don't</p>", subtype="html")
    embedded = EmailMessage()
    embedded.set_content("attached-rfc-secret")
    message.add_attachment(embedded)
    text = decoded_bytes(message.as_bytes(), "original@example.test")
    assert Query('"one two"').matches(text) and Query("don't").matches(text)
    assert "hidden" not in text and "attached-rfc-secret" not in text
    raw = b"Message-ID: <latin@example.test>\nContent-Type: text/plain; charset=iso-8859-1\nContent-Transfer-Encoding: 8bit\n\ncaf\xe9"
    assert decoded_bytes(raw, "latin@example.test") == "café"
    with pytest.raises(NativeError, match="differs"):
        decoded_bytes(raw, "wrong@example.test")
    mail_files(tmp_path)
    path = tmp_path / "synthetic/Inbox.mbox/Data/Messages/1.emlx"
    path.rename(path.with_name("1.partial.emlx"))
    result = Engine(tmp_path).search(NativeSearch(query="tail"), time.monotonic() + 10)
    assert result.partial_bodies == 1 and not result.exhaustive


def test_checkpoint_lag_changes_corruption_and_active_slots(tmp_path: Path) -> None:
    checkpoint_files(tmp_path)
    view = Checkpoint(tmp_path, budget())
    with ExitStack() as stack:
        segment = Segment(view.paths["0"], view.headers["0"], budget(), stack)
        assert segment.active_oids() == {101}
    (tmp_path / "0.indexHead").write_bytes(native_header(generation=4))
    with pytest.raises(NativeError):
        view.check()
    with pytest.raises(NativeError, match="lags"):
        Checkpoint(tmp_path, budget())
    (tmp_path / "0.indexHead").write_bytes(native_header())
    (tmp_path / "indexState").write_bytes(struct.pack("<7I", 5, 10, 9, 1, 0, 0, 0))
    with pytest.raises(NativeError, match="prefix"):
        Checkpoint(tmp_path, budget())
    (tmp_path / "indexState").write_bytes(b"broken")
    with pytest.raises(NativeError):
        Checkpoint(tmp_path, budget())


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (bytes([20, 3, 5, 0]), {20, 17, 12}),
        (bytes([10, 20, 0x11, 2]), {19, 15, 10}),
        (bytes([10, 20, 0, 3, 5, 0]), set(range(10, 20)) - {17, 12}),
        (bytes([20, 20, 2, 3, 0]), {20, 17}),
    ],
)
def test_posting_forms(data: bytes, expected: set[int]) -> None:
    result, pos, stop = posting_chunk(data, 0, len(data), 100, budget())
    assert result == expected and pos == len(data) and not stop


def test_truncated_integer_invalid_posting_and_deadline() -> None:
    for function in (leb, variable):
        with pytest.raises(NativeError):
            function(b"\xff", 0)
    with pytest.raises(NativeError):
        posting_chunk(bytes([20, 30, 255]), 0, 3, 25, budget())
    with pytest.raises(NativeError, match="deadline"):
        Budget(time.monotonic() - 1).check()
    with pytest.raises(NativeError, match="budget"):
        Budget(time.monotonic() + 1, 0).check()


def test_dictionary_fat_bucket_alias_nfd_bounds_and_cycles(tmp_path: Path) -> None:
    checkpoint_files(tmp_path)
    target = encode("café")
    assert target == encode("cafe\u0301") and len(set(ALPHABET)) == 256
    word = encode("tail")
    directory = bytearray(4096)
    # Fat root selects a front-coded bucket containing the remainder.
    struct.pack_into("<I", directory, 1028 + 4 + word[0] * 4, 2)
    entries = prefix(len(word) - 1) + b"\0" + word[1:] + b"\x01"
    arrays = bytearray(4096)
    struct.pack_into("<H", arrays, 64, len(entries))
    arrays[72 : 72 + len(entries)] = entries
    (tmp_path / "0.indexDirectory").write_bytes(directory)
    (tmp_path / "0.indexArrays").write_bytes(arrays)
    view = Checkpoint(tmp_path, budget())
    with ExitStack() as stack:
        segment = Segment(view.paths["0"], view.headers["0"], budget(), stack)
        assert segment.terms("tail") == {Term(1, False)}
        assert segment.terms("absent") == set()
        with pytest.raises(NativeError):
            segment.bucket(999999, b"")


def test_metadata_lz4_raw_reference_record_and_cache_conflict(tmp_path: Path) -> None:
    payload = b"synthetic data"
    raw = b"bv4-" + struct.pack("<I", len(payload)) + payload + b"bv4$"
    header = b"2pbd" + struct.pack("<4I", 20 + len(raw), 20 + len(raw), 0x1009, len(payload))
    assert page(header + raw, budget()) == payload
    with pytest.raises(NativeError):
        page(header + raw[:-4], budget())
    destination = {1: (100, 2)}
    merge(destination, {1: (99, 1)})
    assert destination == {1: (100, 2)}
    with pytest.raises(NativeError, match="Conflicting"):
        merge(destination, {1: (101, 2)})
    assert Inventory().blocks == {}


async def test_native_registry_validation_and_cancellation_before_lock() -> None:
    service = Service(read_only=True)
    native = next(t for t in service.tools() if t.name == "mail_search")
    assert native.annotations is not None and native.annotations.read_only_hint
    result = await service.call("mail_search", json.dumps({"query": "secret", "offset": 1}))
    assert result.model_dump()["code"] == "invalid_input"
    client = NativeSearchClient()
    await client.lock.acquire()
    task = asyncio.create_task(client.search(NativeSearch(query="secret")))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert client.lock.locked() and client.process is None
    client.lock.release()


async def test_worker_reuse_death_oversize_deadline_and_reaping() -> None:
    import sys

    command = (sys.executable, str(Path(__file__).with_name("native_reader_fixture.py")))
    client = NativeSearchClient(command, timeout=1)
    try:
        for _ in range(2):
            with pytest.raises(NativeError, match="Synthetic failure"):
                await client.search(NativeSearch(query="normal"))
            assert client.process is not None and client.process.returncode is None
        assert client.process is not None
        pid = client.process.pid
        for query in ("exit", "oversize", "hang"):
            with pytest.raises(NativeError):
                await client.search(NativeSearch(query=query))
            assert client.process is None
        with pytest.raises(NativeError, match="Synthetic failure"):
            await client.search(NativeSearch(query="normal"))
        assert client.process is not None and client.process.pid != pid
        process = client.process
        task = asyncio.create_task(client.search(NativeSearch(query="hang")))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert client.process is None and process.returncode is not None
    finally:
        await client.close()


def metadata_files(root: Path, rowid: str = "101", version: int = 5) -> None:
    root.mkdir(exist_ok=True)
    definitions = [
        b"\x0b\x00_kMDItemBundleID\0",
        b"\x0b\x00kMDItemContentType\0",
        b"\x0b\x00_kMDItemExternalID\0",
    ]
    for number in (1, 2, 4, 5):
        raw = bytearray(b"\0\0")
        offsets = [0]
        if number == 1:
            for definition in definitions:
                offsets.append(len(raw))
                raw.extend(prefix(len(definition)) + definition)
        header = bytearray(56)
        header[:8] = b"\x00PataD\x00\x00"
        struct.pack_into("<I", header, 20, len(raw))
        struct.pack_into("<I", header, 28, len(offsets))
        (root / f"dbStr-{number}.map.header").write_bytes(header)
        (root / f"dbStr-{number}.map.data").write_bytes(raw)
        (root / f"dbStr-{number}.map.offsets").write_bytes(
            struct.pack("<" + "I" * len(offsets), *offsets)
        )
    record = prefix(101) + b"\0" + b"\0\0" + prefix(version)
    for value in ("com.apple.mail", "public.email-message", rowid):
        encoded = value.encode() + b"\0"
        record += b"\x01" + prefix(len(encoded)) + encoded
    payload = struct.pack("<I", len(record)) + record
    raw_page = b"bv4-" + struct.pack("<I", len(payload)) + payload + b"bv4$"
    raw_page = (
        b"2pbd"
        + struct.pack("<4I", 20 + len(raw_page), 20 + len(raw_page), 0x1009, len(payload))
        + raw_page
    )
    head = bytearray(4096)
    head[:4] = b"8tsd"
    struct.pack_into("<2I", head, 36, 4096, 4096)
    directory = bytearray(4096)
    directory[:4] = b"1mbd"
    struct.pack_into("<2I", directory, 4, 4096, 1)
    struct.pack_into("<QII", directory, 20, 0, 2, 0)
    (root / "store.db").write_bytes(head + directory + raw_page)


def test_metadata_inventory_cache_changes_diagnostics_and_missing_store(tmp_path: Path) -> None:
    metadata_files(tmp_path)
    inventory = Inventory()
    identities, _ = inventory.refresh(tmp_path, budget())
    assert identities == {101: (101, 5)} and inventory.decoded_blocks == 1 and inventory.errors == 0
    assert inventory.refresh(tmp_path, budget())[0] == identities and inventory.decoded_blocks == 0
    metadata_files(tmp_path, rowid="102", version=6)
    assert (
        inventory.refresh(tmp_path, budget())[0] == {101: (102, 6)}
        and inventory.decoded_blocks == 1
    )
    metadata_files(tmp_path, rowid="bad")
    assert inventory.refresh(tmp_path, budget())[0] == {} and inventory.errors == 1
    assert (
        inventory.refresh(tmp_path, budget())[0] == {}
        and inventory.errors == 1
        and inventory.decoded_blocks == 0
    )
    previous = dict(inventory.blocks)
    (tmp_path / "store.db").unlink()
    with pytest.raises(NativeError, match="unavailable"):
        inventory.refresh(tmp_path, budget())
    assert inventory.blocks == previous


def test_large_scope_native_candidates_exceptions_and_bounded_negative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mail = tmp_path / "mail"
    native = tmp_path / "native"
    mail_files(mail, count=502)
    checkpoint_files(native)
    metadata_files(native, rowid="1")
    word = encode("tail")
    directory = bytearray(4096)
    struct.pack_into("<I", directory, 1028 + 4 + word[0] * 4, 2)
    entries = prefix(len(word) - 1) + b"\0" + word[1:] + b"\x01"
    arrays = bytearray(4096)
    struct.pack_into("<H", arrays, 64, len(entries))
    arrays[72 : 72 + len(entries)] = entries
    (native / "0.indexDirectory").write_bytes(directory)
    (native / "0.indexArrays").write_bytes(arrays)
    term_ids = bytearray(4096)
    struct.pack_into("<Q", term_ids, 8, 16)
    (native / "0.indexTermIds").write_bytes(term_ids)
    postings = bytearray(4096)
    postings[16:18] = bytes([0, 3])
    (native / "0.indexPostings").write_bytes(postings)
    engine = Engine(mail, native)
    result = engine.search(NativeSearch(query="tail"), time.monotonic() + 10)
    assert result.backend == "native-spotlight" and result.native_covered == 1
    assert result.total_matches == 501 and result.exception_messages == 501
    assert result.unsearched_candidates == 1 and not result.execution_complete
    assert result.error_counts == {"exception_limit": 1} and result.flags_unchanged
    negative = engine.search(NativeSearch(query="absent"), time.monotonic() + 10)
    assert negative.total_matches == 0 and negative.unsearched_candidates == 1
    assert not negative.execution_complete and not negative.exhaustive
    assert engine.inventory.decoded_blocks == 0
    anchored = engine.search(NativeSearch(query="tail café"), time.monotonic() + 10)
    assert anchored.total_matches == 501
    # A rarer header posting points elsewhere. It must not become a required
    # body candidate when that predicate is already proved from the catalogue.
    from macos_personal_mcp.mail_native.terms import Terms

    def candidates(self: Terms, word: str) -> set[int]:
        return {999} if word == "header" else {101} if word == "tail" else set()

    monkeypatch.setattr(Terms, "candidates", candidates)
    mixed = engine.search(NativeSearch(query="header tail"), time.monotonic() + 10)
    assert mixed.backend == "native-spotlight" and mixed.total_matches == 501
    assert any(
        item.local_id == 1
        for item in engine.search(
            NativeSearch(query="header tail", offset=500, snapshot=mixed.snapshot),
            time.monotonic() + 10,
        ).matches
    )


def test_native_fuzzy_spelling_is_bounded_and_not_semantic(tmp_path: Path) -> None:
    from macos_personal_mcp.mail_native.terms import fuzzy_terms

    assert Query("prepaod", 1).matches("existing prepaid credits")
    assert not Query("prepaod", 1).matches("different words")
    assert not Query("prepod", 1).matches("prepaid")
    assert Query("prepod", 2).matches("prepaid")
    for query in ('"prepaid credits"', "café", "abc"):
        with pytest.raises(ValidationError):
            NativeSearch(query=query, fuzzy_distance=1)
    checkpoint_files(tmp_path)
    word = encode("prepaid")
    directory = bytearray(4096)
    struct.pack_into("<I", directory, 1028 + 4 + word[0] * 4, 2)
    entries = prefix(len(word) - 1) + b"\0" + word[1:] + b"\x01"
    arrays = bytearray(4096)
    struct.pack_into("<H", arrays, 64, len(entries))
    arrays[72 : 72 + len(entries)] = entries
    (tmp_path / "0.indexDirectory").write_bytes(directory)
    (tmp_path / "0.indexArrays").write_bytes(arrays)
    view = Checkpoint(tmp_path, budget())
    with ExitStack() as stack:
        segment = Segment(view.paths["0"], view.headers["0"], budget(), stack)
        assert fuzzy_terms(segment, "prepaod", 1) == {"prepaid": {Term(1, False)}}
        assert fuzzy_terms(segment, "zzqxnonexistent", 1) == {}
    mail = tmp_path / "mail"
    mail_files(mail)
    result = Engine(mail).search(
        NativeSearch(query="tall", fuzzy_distance=1), time.monotonic() + 10
    )
    assert result.total_matches == 3 and result.matched_spellings == ["tail"]


def test_malformed_separator_remains_explicitly_partial(tmp_path: Path) -> None:
    from macos_personal_mcp.mime_body import decoded_bytes

    raw = b"Message-ID: <message-1@example.test>\nThis malformed line starts visible body\nTail secret marker"
    with pytest.raises(NativeError, match="structural"):
        decoded_bytes(raw, "message-1@example.test")
    assert "Tail secret marker" in decoded_bytes(
        raw, "message-1@example.test", allow_separator_defect=True
    )
    mail_files(tmp_path)
    path = tmp_path / "synthetic/Inbox.mbox/Data/Messages/1.emlx"
    path.write_bytes(str(len(raw)).encode() + b"\n" + raw)
    result = Engine(tmp_path).search(NativeSearch(query="tail"), time.monotonic() + 10)
    assert (
        result.total_matches == 3 and result.partial_bodies == 1 and result.unavailable_bodies == 0
    )


def test_compacted_and_compact_node_dictionary_forms(tmp_path: Path) -> None:
    checkpoint_files(tmp_path)
    for name in ("indexHead", "shadowIndexHead"):
        (tmp_path / f"0.{name}").write_bytes(native_header(flags=6))
    word = encode("tail")
    fat = bytearray(4096)
    struct.pack_into("<I", fat, 1028 + 4 + word[0] * 4, 5)  # compact node at word offset one
    compact = bytearray(4096)
    bitmap = 1 << word[1]
    compact[8:40] = bitmap.to_bytes(32, "little")
    struct.pack_into("<I", compact, 42, 2)  # rank-zero child: flat bucket one
    entries = prefix(len(word) - 2) + b"\0" + word[2:] + prefix(16) + b"\0"
    arrays = bytearray(4096)
    struct.pack_into("<H", arrays, 64, len(entries))
    arrays[72 : 72 + len(entries)] = entries
    (tmp_path / "0.indexDirectory").write_bytes(fat)
    (tmp_path / "0.indexCompactDirectory").write_bytes(compact)
    (tmp_path / "0.indexArrays").write_bytes(arrays)
    postings = bytearray(4096)
    postings[16:18] = bytes([0, 3])
    (tmp_path / "0.indexPostings").write_bytes(postings)
    view = Checkpoint(tmp_path, budget())
    with ExitStack() as stack:
        segment = Segment(view.paths["0"], view.headers["0"], budget(), stack)
        assert segment.terms("tail") == {Term(16, True)}
        assert segment.postings(Term(16, True)) == {1}
    # Source replacement with byte-identical contents must still invalidate a view.
    original = tmp_path / "0.indexHead"
    replacement = tmp_path / "replacement"
    replacement.write_bytes(original.read_bytes())
    replacement.replace(original)
    with pytest.raises(NativeError, match="file changed"):
        view.check()
