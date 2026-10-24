"""Validated read-only Envelope Index and exact local MIME identities."""

import hashlib
import os
import plistlib
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

from pydantic import ConfigDict, Field

from macos_personal_mcp.mail_native.common import Budget, Signature, signature
from macos_personal_mcp.mail_native.contracts import NativeMatch, NativeSearch
from macos_personal_mcp.mime_body import decoded_bytes
from macos_personal_mcp.models import Model
from macos_personal_mcp.process import NativeError


class Row(Model):
    local_id: int = Field(gt=0)
    message_id: str | None = Field(max_length=4096)
    mailbox_url: str = Field(max_length=4096)
    date_received: int
    remote_id: int | str | None
    conversation_id: int
    read: int
    flags: int
    body_indexed: int
    subject: str = Field(max_length=4096)
    sender: str = Field(max_length=4096)

    def selectors(self) -> tuple[str, list[str]]:
        url = urlsplit(self.mailbox_url)
        if url.scheme not in {"imap", "ews", "local"}:
            raise NativeError("native_format", "Unsupported native mailbox URL")
        account = url.netloc if url.scheme != "local" else "__local__"
        parts = [unquote(p) for p in url.path.split("/") if p]
        if url.scheme == "local" and url.netloc:
            parts.insert(0, unquote(url.netloc))
        return account, parts

    def match(self) -> NativeMatch:
        account, boxes = self.selectors()
        return NativeMatch(
            local_id=self.local_id,
            message_id=self.message_id,
            account_id=account,
            mailbox_path=boxes,
            subject=self.subject,
            sender=self.sender,
            received_at=datetime.fromtimestamp(self.date_received, UTC),
            read=bool(self.read),
        )


SQL = """SELECT m.ROWID local_id,g.message_id_header message_id,b.url mailbox_url,
 m.date_received,m.remote_id,m.conversation_id,m.read,m.flags,
 COALESCE(sm.message_body_indexed,0) body_indexed,
 COALESCE(m.subject_prefix,'') || COALESCE(s.subject,'') subject,
 COALESCE(a.address,'') sender FROM messages m
 JOIN mailboxes b ON b.ROWID=m.mailbox
 LEFT JOIN message_global_data g ON g.ROWID=m.global_message_id
 LEFT JOIN subjects s ON s.ROWID=m.subject
 LEFT JOIN addresses a ON a.ROWID=m.sender
 LEFT JOIN searchable_messages sm ON sm.ROWID=m.searchable_message
 WHERE m.deleted=0"""


class Catalogue:
    def __init__(self, root: Path, budget: Budget) -> None:
        self.root = root.resolve()
        self.budget = budget
        self.path = self.root / "MailData/Envelope Index"
        self.identity = signature(self.path)[:2]
        self.connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=0.1)
        self.connection.row_factory = sqlite3.Row
        self.connection.set_progress_handler(self.progress, 10000)
        self.version: int = self.connection.execute("PRAGMA data_version").fetchone()[0]
        self.paths: dict[str, list[tuple[tuple[str, ...], Path]]] = {}
        self.files: dict[Path, Signature] = {}
        self.check()

    def progress(self) -> int:
        try:
            self.budget.check()
            return 0
        except NativeError:
            return 1

    def close(self) -> None:
        self.connection.close()

    def check(self) -> None:
        self.budget.check()
        for path, observed in self.files.items():
            if signature(path) != observed:
                raise NativeError("source_changed", "Native MIME changed during search")
        version: int = self.connection.execute("PRAGMA data_version").fetchone()[0]
        if version != self.version or signature(self.path)[:2] != self.identity:
            raise NativeError("source_changed", "Native catalogue changed; retry a fresh search")

    def rows(self, request: NativeSearch) -> list[Row]:
        clauses: list[str] = []
        params: list[int | float] = []
        if request.since is not None:
            clauses.append("m.date_received>=?")
            params.append(request.since.timestamp())
        if request.before is not None:
            clauses.append("m.date_received<?")
            params.append(request.before.timestamp())
        if request.unread_only:
            clauses.append("m.read=0")
        sql = SQL + "".join(" AND " + clause for clause in clauses)
        sql += " ORDER BY m.date_received DESC,m.ROWID DESC LIMIT 100001"
        rows = [Row.model_validate(dict(row)) for row in self.connection.execute(sql, params)]
        if len(rows) > 100000:
            raise NativeError("search_limit", "Native catalogue scope exceeds 100000 messages")
        result: list[Row] = []
        for row in rows:
            self.budget.check()
            account, boxes = row.selectors()
            if request.account_id is not None and request.account_id != account:
                continue
            if request.mailbox_path is not None and request.mailbox_path != boxes:
                continue
            result.append(row)
        self.check()
        return result

    def locate(self, row: Row) -> Path:
        account, boxes = row.selectors()
        directory = "Mailboxes" if account == "__local__" else account
        base = (self.root / directory).resolve()
        base.relative_to(self.root)
        if directory not in self.paths:
            roots: list[tuple[tuple[str, ...], Path]] = []
            for parent, directories, _ in os.walk(base, followlinks=False):
                self.budget.check()
                directories[:] = [d for d in directories if d not in {"Messages", "Attachments"}]
                if "Data" in directories:
                    path = Path(parent) / "Data"
                    names = tuple(
                        p[:-5].casefold()
                        for p in path.relative_to(base).parts
                        if p.endswith(".mbox")
                    )
                    roots.append((names, path))
                    directories.remove("Data")
            self.paths[directory] = roots
        shard = Path(*reversed(str(row.local_id // 1000))) if row.local_id >= 1000 else Path()
        roots = self.paths[directory]
        for preferred in (True, False):
            candidates = [
                root / shard / "Messages" / (str(row.local_id) + suffix)
                for names, root in roots
                if (names == tuple(b.casefold() for b in boxes)) == preferred
                for suffix in (".emlx", ".partial.emlx")
                if (root / shard / "Messages" / (str(row.local_id) + suffix)).is_file()
            ]
            if len(candidates) > 1:
                raise NativeError("message_identity", "Ambiguous native body location")
            if candidates:
                path = candidates[0].resolve()
                path.relative_to(base)
                return path
        raise NativeError("body_unavailable", "Local MIME body is unavailable")

    def body(self, row: Row, maximum_bytes: int = 20_000_000) -> tuple[str, bool, int]:
        self.budget.check()
        path = self.locate(row)
        before = signature(path)
        self.files[path] = before
        if before[2] > 22_000_000:
            raise NativeError("body_limit", "Native MIME file exceeds 22 MB")
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if stat_signature(opened) != before:
                raise NativeError("source_changed", "Native MIME replaced at open")
            line = stream.readline(32)
            if not re.fullmatch(rb"\d+[ \t]*\r?\n", line):
                raise NativeError("native_format", "Invalid native MIME length")
            length = int(line)
            if length > 20_000_000:
                raise NativeError("body_limit", "Native MIME body exceeds 20 MB")
            if length > maximum_bytes:
                raise NativeError(
                    "body_byte_limit", "Search reached its total original MIME byte bound"
                )
            raw = stream.read(length)
            tail = stream.read(2_000_001)
            if len(raw) != length or len(tail) > 2_000_000:
                raise NativeError("body_incomplete", "Truncated MIME file or excessive trailer")
            if stat_signature(os.fstat(stream.fileno())) != before:
                raise NativeError("source_changed", "Native MIME changed while reading")
        if signature(path) != before:
            raise NativeError("source_changed", "Native MIME replaced during capture")
        # RFC equality is the normal route. Missing/malformed IDs require the
        # separately bound native account/mailbox/UID/trailer route below.
        expected = row.message_id.strip("<>") if row.message_id else None
        malformed = False

        def decode(identity: str | None) -> str:
            nonlocal malformed
            try:
                return decoded_bytes(raw, identity)
            except NativeError as error:
                if error.code != "mime_invalid":
                    raise
                text = decoded_bytes(raw, identity, allow_separator_defect=True)
                malformed = True
                return text

        try:
            if expected is None:
                raise NativeError("message_identity", "Missing RFC identity")
            body = decode(expected)
        except NativeError as error:
            if error.code != "message_identity":
                raise
            self.bind_native(row, path, tail)
            body = decode(None)
        self.budget.check()
        # Partial files are searched for useful positives but cannot certify that
        # every body part is local. The result keeps them explicitly incomplete.
        return body, malformed or path.name.endswith(".partial.emlx"), len(raw)

    def bind_native(self, row: Row, path: Path, tail: bytes) -> None:
        account, boxes = row.selectors()
        relative = path.relative_to(self.root)
        actual_boxes = [p[:-5] for p in relative.parts if p.endswith(".mbox")]
        if (
            account == "__local__"
            or relative.parts[0] != account
            or actual_boxes != boxes
            or not row.remote_id
            or path.name not in {f"{row.local_id}.emlx", f"{row.local_id}.partial.emlx"}
        ):
            raise NativeError("message_identity", "Native account/mailbox/UID binding unavailable")
        start = tail.find(b"<?xml")
        if start < 0 or tail[:start].strip():
            raise NativeError("message_identity", "Native identity trailer unavailable")
        trailer: object = plistlib.loads(tail[start:])
        if not isinstance(trailer, dict):
            raise NativeError("message_identity", "Invalid native identity trailer")
        binding = Trailer.model_validate(trailer)
        if (
            str(binding.remote_id) != str(row.remote_id)
            or binding.date_received != row.date_received
            or str(binding.conversation_id) != str(row.conversation_id)
        ):
            raise NativeError("message_identity", "Native UID/date/conversation mismatch")
        found = self.connection.execute(SQL + " AND m.ROWID=?", (row.local_id,)).fetchone()
        if found is None or Row.model_validate(dict(found)) != row:
            raise NativeError("source_changed", "Native row changed during bound read")


class Trailer(Model):
    # Native plist has additional bookkeeping keys unrelated to identity.
    model_config = ConfigDict(strict=True, extra="ignore", frozen=True, populate_by_name=True)
    remote_id: int | str = Field(alias="remote-id")
    date_received: int = Field(alias="date-received")
    conversation_id: int | str = Field(alias="conversation-id")


def stat_signature(stat: os.stat_result) -> Signature:
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def snapshot(rows: list[Row], checkpoint: str = "") -> str:
    digest = hashlib.sha256(checkpoint.encode())
    for row in rows:
        digest.update(row.model_dump_json().encode())
    return digest.hexdigest()
