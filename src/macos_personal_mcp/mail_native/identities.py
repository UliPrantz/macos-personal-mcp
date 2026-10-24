"""Narrow native metadata reader, no GPL parser or copied decompilation.

Format reference: libyal/dtformats spotlight_storedb.py and YAML at
308ce8c38df2eb95a71b6e832b3f9803f0c4b169 (Apache-2.0). See THIRD_PARTY.md.
Only OID, native update version and Mail ROWID survive decompression.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from lz4.block import decompress

from macos_personal_mcp.mail_native.common import (
    Budget,
    Signature,
    bounded_read,
    signature,
    u32,
    variable,
)
from macos_personal_mcp.process import NativeError

KEYS = {"_kMDItemExternalID", "_kMDItemBundleID", "kMDItemContentType"}
Pair = tuple[int, int]


@dataclass(frozen=True)
class Block:
    identities: dict[int, Pair]
    errors: int


class Maps:
    def __init__(self, root: Path, budget: Budget) -> None:
        self.raw: dict[int, bytes] = {}
        self.offsets: dict[int, bytes] = {}
        self.types: dict[int, tuple[int, int, str]] = {}
        digest = hashlib.sha256()
        for number in (1, 2, 4, 5):
            budget.check()
            header = bounded_read(root / f"dbStr-{number}.map.header", 4096)
            if header[:8] != b"\x00PataD\x00\x00" or len(header) < 56:
                raise NativeError("native_format", "Unsupported native metadata map")
            size, count = u32(header, 20), u32(header, 28)
            raw = bounded_read(root / f"dbStr-{number}.map.data", 200_000_000)
            offsets = bounded_read(root / f"dbStr-{number}.map.offsets", 40_000_000)
            if size > len(raw) or count * 4 > len(offsets):
                raise NativeError("native_format", "Truncated native metadata map")
            self.raw[number], self.offsets[number] = raw[:size], offsets[: count * 4]
            for data in (header, self.raw[number], self.offsets[number]):
                digest.update(len(data).to_bytes(8, "little"))
                digest.update(data)
        self.digest = digest.digest()
        raw, offsets = self.raw[1], self.offsets[1]
        for key in range(1, len(offsets) // 4):
            budget.check()
            offset = u32(offsets, key * 4)
            end = u32(offsets, (key + 1) * 4) if (key + 1) * 4 < len(offsets) else len(raw)
            if offset in {0, 1}:
                continue
            length, pos = variable(raw, offset)
            if pos + length != end:
                continue  # Allocated stream remnants, not active definitions.
            if length < 3 or pos + length > len(raw):
                raise NativeError("native_format", "Invalid native property definition")
            name = raw[pos + 2 : pos + length].split(b"\0", 1)[0].decode("utf-8")
            self.types[key] = raw[pos], raw[pos + 1], name

    def category(self, key: int) -> str:
        offsets, raw = self.offsets[2], self.raw[2]
        if key < 1 or key * 4 + 4 > len(offsets):
            raise NativeError("native_format", "Metadata category key exceeds map")
        offset = u32(offsets, key * 4)
        if offset in {0, 1}:
            raise NativeError("native_format", "Unavailable native category")
        length, pos = variable(raw, offset)
        if pos + length > len(raw):
            raise NativeError("native_format", "Native category exceeds map")
        return raw[pos : pos + length].split(b"\0", 1)[0].decode("utf-8")

    def reference(self, key: int, prop: int) -> str:
        if prop & 3 not in {2, 3}:
            return self.category(key)
        number = 5 if prop & 3 == 3 else 4
        offsets, raw = self.offsets[number], self.raw[number]
        if key < 1 or key * 4 + 4 > len(offsets):
            raise NativeError("native_format", "Native metadata list key exceeds map")
        offset = u32(offsets, key * 4)
        _, pos = variable(raw, offset)
        length, pos = variable(raw, pos)
        pos += number == 5
        if length % 4 or pos + length > len(raw) or length < 4:
            raise NativeError("native_format", "Invalid native metadata identity list")
        value = self.category(u32(raw, pos))
        return value.split("\x16\x02", 1)[0]

    def attribute(
        self, data: bytes, pos: int, end: int, kind: int, prop: int, needed: bool
    ) -> tuple[str | None, int]:
        value: str | None = None
        if kind in {0, 2, 6} or (kind == 7 and not prop & 2):
            _, pos = variable(data, pos, end)
        elif kind == 15:
            key, pos = variable(data, pos, end)
            if needed:
                value = self.reference(key, prop)
        elif kind in {7, 8, 9, 10, 11, 12, 14}:
            if kind in {7, 11, 14} or prop & 2:
                size, pos = variable(data, pos, end)
            else:
                size = {8: 1, 9: 4, 10: 8, 12: 8}[kind]
            if pos + size > end:
                raise NativeError("native_format", "Metadata attribute exceeds record")
            if needed and kind == 11:
                value = (
                    data[pos : pos + size]
                    .split(b"\0", 1)[0]
                    .decode("utf-8")
                    .split("\x16\x02", 1)[0]
                )
            pos += size
        else:
            raise NativeError("native_format", "Unsupported metadata attribute type")
        if pos > end:
            raise NativeError("native_format", "Metadata attribute crosses record boundary")
        return value, pos


def merge(destination: dict[int, Pair], source: dict[int, Pair]) -> None:
    for oid, pair in source.items():
        previous = destination.get(oid)
        if previous and previous[1] == pair[1] and previous[0] != pair[0]:
            raise NativeError("native_format", "Conflicting native metadata identity versions")
        if previous is None or pair[1] >= previous[1]:
            destination[oid] = pair


def records(data: bytes, maps: Maps, budget: Budget) -> Block:
    cursor = errors = 0
    found: dict[int, Pair] = {}
    while cursor < len(data):
        budget.check()
        size = u32(data, cursor)
        end = cursor + 4 + size
        if end > len(data) or size < 5:
            raise NativeError("native_format", "Native metadata record exceeds page")
        oid, pos = variable(data, cursor + 4, end)
        if pos >= end:
            raise NativeError("native_format", "Truncated native record flags")
        pos += 1
        for _ in range(2):
            _, pos = variable(data, pos, end)
        version, pos = variable(data, pos, end)
        values: dict[str, str] = {}
        index = 0
        try:
            while pos < end:
                budget.check()
                delta, pos = variable(data, pos, end)
                index += delta
                if index not in maps.types:
                    raise NativeError("native_format", "Undefined native property type")
                kind, prop, name = maps.types[index]
                if name == "kMDStoreAccumulatedSizes":
                    break
                value, pos = maps.attribute(data, pos, end, kind, prop, name in KEYS)
                if value is not None:
                    values[name] = value
                    if (name == "_kMDItemBundleID" and value != "com.apple.mail") or (
                        name == "kMDItemContentType" and value != "public.email-message"
                    ):
                        break
                    if len(values) == 3:
                        raw = values["_kMDItemExternalID"]
                        if raw.isdecimal() and int(raw) > 0:
                            merge(found, {oid: (int(raw), version)})
                        else:
                            errors += 1
                        break
        except NativeError as error:
            if error.code != "native_format":
                raise
            # Preserve diagnostics even when cached; unknown records cannot
            # silently become proof that all Mail metadata was enumerated.
            errors += 1
        cursor = end
    return Block(found, errors)


def page(raw: bytes, budget: Budget) -> bytes:
    if raw[:4] != b"2pbd" or len(raw) < 20 or u32(raw, 4) != len(raw):
        raise NativeError("native_format", "Unsupported native metadata page")
    kind, expected = u32(raw, 12), u32(raw, 16)
    if kind not in {0x1009, 0x5009} or not 0 < expected <= 8_000_000:
        raise NativeError("native_format", "Unsupported native metadata compression")
    data = raw[20:]
    result: list[bytes] = []
    previous: bytes | None = None
    pos = size = 0
    while pos + 4 <= len(data):
        budget.check()
        magic = data[pos : pos + 4]
        if magic == b"bv4$":
            return b"".join(result)
        output = u32(data, pos + 4)
        if output > 8_000_000 - size:
            raise NativeError("native_format", "Metadata decompression exceeds bound")
        if magic == b"bv41":
            compressed = u32(data, pos + 8)
            start, stop = pos + 12, pos + 12 + compressed
            if stop > len(data):
                raise NativeError("native_format", "Truncated LZ4 metadata block")
            decoded = decompress(data[start:stop], uncompressed_size=output, dict=previous)
        elif magic == b"bv4-":
            start, stop = pos + 8, pos + 8 + output
            if stop > len(data):
                raise NativeError("native_format", "Truncated raw metadata block")
            decoded = data[start:stop]
        else:
            raise NativeError("native_format", "Unknown metadata compression marker")
        if len(decoded) != output:
            raise NativeError("native_format", "Metadata decompressed length mismatch")
        result.append(decoded)
        previous, pos, size = decoded, stop, size + output
    raise NativeError("native_format", "Missing metadata compression terminator")


class Inventory:
    def __init__(self) -> None:
        self.blocks: dict[tuple[bytes, bytes], Block] = {}
        self.errors = 0
        self.decoded_blocks = 0

    def observations(self, root: Path) -> dict[Path, Signature]:
        paths = [root / name for name in ("store.db", ".store.db") if (root / name).exists()]
        paths += [
            root / f"dbStr-{number}.map.{suffix}"
            for number in (1, 2, 4, 5)
            for suffix in ("header", "offsets", "data")
        ]
        return {path: signature(path) for path in paths}

    def refresh(self, root: Path, budget: Budget) -> tuple[dict[int, Pair], dict[Path, Signature]]:
        before = self.observations(root)
        if root / "store.db" not in before:
            raise NativeError("native_unavailable", "Native metadata store is unavailable")
        maps = Maps(root, budget)
        working: dict[tuple[bytes, bytes], Block] = {}
        identities: dict[int, Pair] = {}
        errors = decoded = 0
        for name in ("store.db", ".store.db"):
            path = root / name
            if path not in before:
                continue
            with path.open("rb") as stream:
                head = stream.read(4096)
                if head[:4] != b"8tsd" or any(u32(head, i) for i in (48, 52, 56, 60, 64)):
                    raise NativeError(
                        "native_format", "Unsupported native metadata database profile"
                    )
                start, size = u32(head, 36), u32(head, 40)
                if size > 32_000_000:
                    raise NativeError("native_format", "Metadata page directory exceeds bound")
                directory = read_at(stream, start, size)
                pos = 0
                while pos < len(directory):
                    budget.check()
                    if directory[pos : pos + 4] not in {b"1mbd", b"2mbd"}:
                        raise NativeError("native_format", "Unsupported metadata page directory")
                    length, count = u32(directory, pos + 4), u32(directory, pos + 8)
                    if length < 20 or pos + length > len(directory) or 20 + count * 16 > length:
                        raise NativeError("native_format", "Truncated metadata page directory")
                    for index in range(count):
                        budget.check()
                        offset = u32(directory, pos + 20 + index * 16 + 8) * 4096
                        page_header = read_at(stream, offset, 20)
                        page_size = u32(page_header, 4)
                        if not 20 <= page_size <= 1_000_000:
                            raise NativeError(
                                "native_format", "Metadata compressed page exceeds bound"
                            )
                        raw = page_header + read_at(stream, offset + 20, page_size - 20)
                        key = maps.digest, hashlib.sha256(raw).digest()
                        cached = working.get(key) or self.blocks.get(key)
                        if cached is None:
                            cached = records(page(raw, budget), maps, budget)
                            decoded += 1
                        working[key] = cached
                        errors += cached.errors
                        merge(identities, cached.identities)
                    pos += length
        if self.observations(root) != before:
            raise NativeError("source_changed", "Native metadata changed during inventory")
        self.blocks, self.errors, self.decoded_blocks = working, errors, decoded
        return identities, before


def read_at(stream: BinaryIO, offset: int, size: int) -> bytes:
    if offset < 0 or size < 0:
        raise NativeError("native_format", "Negative native metadata offset")
    stream.seek(offset)
    data = stream.read(size)
    if len(data) != size:
        raise NativeError("native_format", "Truncated native metadata read")
    return data
