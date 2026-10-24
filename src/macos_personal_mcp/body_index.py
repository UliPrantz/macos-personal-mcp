"""Explicit resumable local FTS5 index, sourced through public read-only Mail APIs."""

import hashlib
import json
import os
import sqlite3
import stat
import time
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from macos_personal_mcp.mime_body import decoded_body
from macos_personal_mcp.models import (
    AwareDatetime,
    BodySearchPage,
    IndexProgress,
    IndexRequest,
    MailScope,
    MessagePage,
    MessageSource,
    Metadata,
    Model,
    SourceKey,
)
from macos_personal_mcp.native import Bridge
from macos_personal_mcp.process import NativeError
from macos_personal_mcp.sending import private_directory

MAX_AGE = timedelta(minutes=30)


def scope_key(scope: MailScope) -> str:
    fields = scope.model_copy(
        update={
            "since": scope.since.astimezone(UTC),
            "before": scope.before.astimezone(UTC),
        }
    ).model_dump(mode="json", exclude={"query", "unread_only", "offset", "limit"})
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


def fingerprint(message: Metadata) -> str:
    return hashlib.sha256(message.model_dump_json(exclude={"read"}).encode()).hexdigest()


def inventory_digest(messages: list[Metadata]) -> str:
    return hashlib.sha256(
        "".join(fingerprint(m) for m in sorted(messages, key=lambda m: m.local_id)).encode()
    ).hexdigest()


async def inventory(bridge: Bridge, scope: MailScope) -> MessagePage:
    request = scope.model_copy(
        update={"query": "", "unread_only": False, "offset": 0, "limit": 200}
    )
    page = await bridge.call("mail_inventory", request, MessagePage)
    if (
        not page.complete
        or page.next_offset is not None
        or page.total_matches != len(page.messages)
        or len({m.local_id for m in page.messages}) != len(page.messages)
    ):
        raise NativeError(
            "inventory_incomplete",
            "A complete identity inventory is required; no partial scope claim",
        )
    return page


class DocumentState(Model):
    local_id: int
    fingerprint: str
    error: str | None


class StoredScope(Model):
    digest: str
    complete: bool
    indexed_at: AwareDatetime
    total: int


class Hit(Model):
    local_id: int
    excerpt: str


class BodyIndex:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (
            root
            if root is not None
            else Path.home() / "Library/Application Support/macos-personal-mcp"
        )
        self.path = self.root / "mail-body-index.sqlite3"

    @contextmanager
    def connection(self, *, write: bool) -> Generator[sqlite3.Connection]:
        if write:
            private_directory(self.root)
            descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            os.close(descriptor)
        if not self.path.exists():
            raise NativeError(
                "body_source_unavailable",
                "No complete owned body index exists; refresh it explicitly first",
            )
        info = self.path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise NativeError("private_storage", "Body index must be an owner-only regular file")
        connection = sqlite3.connect(
            self.path.as_uri() + ("?mode=rw" if write else "?mode=ro"), uri=True, timeout=1
        )
        try:
            if write:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS scopes (key TEXT PRIMARY KEY, digest TEXT NOT NULL, complete INTEGER NOT NULL, indexed_at TEXT NOT NULL, total INTEGER NOT NULL)"
                )
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS documents (scope TEXT, local_id INTEGER, fingerprint TEXT NOT NULL, error TEXT, PRIMARY KEY(scope,local_id))"
                )
                connection.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS bodies USING fts5(scope UNINDEXED, local_id UNINDEXED, subject, sender, body, tokenize='unicode61 remove_diacritics 2')"
                )
                connection.commit()
            yield connection
        except sqlite3.Error as error:
            raise NativeError(
                "index_database", "Owned index query/update failed; no complete results"
            ) from error
        finally:
            connection.close()

    @staticmethod
    def states(connection: sqlite3.Connection, key: str) -> dict[int, DocumentState]:
        return {
            item.local_id: item
            for row in connection.execute(
                "SELECT local_id,fingerprint,error FROM documents WHERE scope=?", (key,)
            )
            for item in [
                DocumentState.model_validate(
                    {"local_id": row[0], "fingerprint": row[1], "error": row[2]}
                )
            ]
        }

    def store(self, key: str, message: Metadata, text: str | None, error: str | None) -> None:
        with self.connection(write=True) as connection:
            connection.execute(
                "DELETE FROM bodies WHERE scope=? AND local_id=?", (key, message.local_id)
            )
            connection.execute(
                "INSERT OR REPLACE INTO documents VALUES (?,?,?,?)",
                (key, message.local_id, fingerprint(message), error),
            )
            if text is not None:
                connection.execute(
                    "INSERT INTO bodies VALUES (?,?,?,?,?)",
                    (key, message.local_id, message.subject, message.sender, text),
                )
            connection.commit()

    async def refresh(self, request: IndexRequest, bridge: Bridge) -> IndexProgress:
        scope = request.scope
        key = scope_key(scope)
        initial = await inventory(bridge, scope)
        with self.connection(write=True) as connection:
            if request.rebuild:
                connection.execute("DELETE FROM documents WHERE scope=?", (key,))
                connection.execute("DELETE FROM bodies WHERE scope=?", (key,))
            connection.execute(
                "INSERT INTO scopes VALUES (?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET complete=0",
                (
                    key,
                    inventory_digest(initial.messages),
                    0,
                    datetime.now(UTC).isoformat(),
                    initial.total_matches,
                ),
            )
            states = self.states(connection, key)
            current = {m.local_id for m in initial.messages}
            for identifier in states.keys() - current:
                connection.execute(
                    "DELETE FROM documents WHERE scope=? AND local_id=?", (key, identifier)
                )
                connection.execute(
                    "DELETE FROM bodies WHERE scope=? AND local_id=?", (key, identifier)
                )
            connection.commit()
        pending = [
            m
            for m in initial.messages
            if m.local_id not in states
            or states[m.local_id].fingerprint != fingerprint(m)
            or states[m.local_id].error is not None
        ]
        pending.sort(key=lambda m: m.local_id in states and states[m.local_id].error is not None)
        attempted = 0
        for message in pending[: request.max_messages]:
            attempted += 1
            try:
                source = await bridge.call(
                    "mail_get_source",
                    SourceKey(
                        account_id=scope.account_id,
                        mailbox_path=scope.mailbox_path,
                        local_id=message.local_id,
                        expected_message_id=message.message_id,
                        max_source_chars=64_000_000,
                    ),
                    MessageSource,
                )
                if source.message_id != message.message_id:
                    raise NativeError("message_identity", "Source identity differs from inventory")
                text = decoded_body(source.source, message.message_id)
                self.store(key, message, text, None)
            except NativeError as error:
                self.store(key, message, None, error.code)
        final = await inventory(bridge, scope)
        with self.connection(write=True) as connection:
            states = self.states(connection, key)
            valid = [
                m
                for m in final.messages
                if m.local_id in states and states[m.local_id].fingerprint == fingerprint(m)
            ]
            indexed = sum(states[m.local_id].error is None for m in valid)
            unavailable = len(valid) - indexed
            error_counts: dict[str, int] = {}
            for message in valid:
                error_code = states[message.local_id].error
                if error_code is not None:
                    error_counts[error_code] = error_counts.get(error_code, 0) + 1
            missing = len(final.messages) - len(valid)
            complete = inventory_digest(initial.messages) == inventory_digest(
                final.messages
            ) and indexed == len(final.messages)
            stamp = datetime.now(UTC).isoformat()
            connection.execute(
                "UPDATE scopes SET digest=?,complete=?,indexed_at=?,total=? WHERE key=?",
                (inventory_digest(final.messages), int(complete), stamp, len(final.messages), key),
            )
            connection.commit()
        return IndexProgress(
            scope_key=key,
            total=len(final.messages),
            indexed=indexed,
            unavailable=unavailable,
            pending=missing,
            attempted=attempted,
            complete=complete,
            inventory_stable=inventory_digest(initial.messages) == inventory_digest(final.messages),
            error_counts=error_counts,
            observed_at=final.observed_at,
        )

    async def search(self, scope: MailScope, bridge: Bridge) -> BodySearchPage:
        if not scope.query.strip():
            raise NativeError(
                "query_required", "Full-body search requires an explicit FTS5 token/phrase query"
            )
        key = scope_key(scope)
        with self.connection(write=False) as connection:
            connection.execute("BEGIN")
            row = connection.execute(
                "SELECT digest,complete,indexed_at,total FROM scopes WHERE key=?", (key,)
            ).fetchone()
            if row is None:
                raise NativeError(
                    "body_source_unavailable",
                    "Selected account/folder/date scope has no owned body index",
                )
            stored = StoredScope.model_validate_json(
                json.dumps(
                    {
                        "digest": row[0],
                        "complete": bool(row[1]),
                        "indexed_at": row[2],
                        "total": row[3],
                    }
                )
            )
            if not stored.complete:
                raise NativeError(
                    "index_incomplete",
                    "Selected body index is incomplete; explicitly resume refresh",
                )
            age = datetime.now(UTC) - stored.indexed_at
            if age < timedelta(0) or age > MAX_AGE:
                raise NativeError(
                    "index_stale",
                    "Body snapshot is outside its 30-minute freshness window; refresh explicitly",
                )
            current = await inventory(bridge, scope)
            if inventory_digest(current.messages) != stored.digest:
                raise NativeError(
                    "index_stale",
                    "Mailbox inventory changed; refresh additions, moves, changes or deletes explicitly",
                )
            started = time.perf_counter()
            count = connection.execute(
                "SELECT count(*) FROM bodies WHERE scope=?", (key,)
            ).fetchone()
            if count is None or count[0] != stored.total:
                raise NativeError(
                    "index_incomplete",
                    "Owned index row coverage differs from its complete snapshot",
                )
            try:
                rows = connection.execute(
                    "SELECT local_id,snippet(bodies,4,'[',']',' … ',24) FROM bodies WHERE bodies MATCH ? AND scope=? ORDER BY bm25(bodies),CAST(local_id AS INTEGER)",
                    (scope.query, key),
                ).fetchall()
            except sqlite3.OperationalError as error:
                raise NativeError(
                    "invalid_query", "FTS5 query is invalid or the index is unavailable"
                ) from error
            milliseconds = (time.perf_counter() - started) * 1000
            hits = [Hit.model_validate({"local_id": row[0], "excerpt": row[1]}) for row in rows]
            messages = {m.local_id: m for m in current.messages}
            hits = [h for h in hits if not scope.unread_only or not messages[h.local_id].read]
            selected = hits[scope.offset : scope.offset + scope.limit]
            end = scope.offset + scope.limit
            return BodySearchPage(
                messages=[messages[h.local_id] for h in selected],
                total_matches=len(hits),
                next_offset=end if end < len(hits) else None,
                observed_at=current.observed_at,
                complete=True,
                scope=scope.account_id
                + "/"
                + "/".join(scope.mailbox_path)
                + " ["
                + scope.since.isoformat()
                + ", "
                + scope.before.isoformat()
                + ")",
                indexed_at=stored.indexed_at,
                indexed_messages=stored.total,
                excerpts=[h.excerpt for h in selected],
                query_ms=milliseconds,
            )
