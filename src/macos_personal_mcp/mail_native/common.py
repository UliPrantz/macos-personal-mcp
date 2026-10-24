"""Shared absolute work budget and bounded binary reads."""

import mmap
import struct
import time
from dataclasses import dataclass
from pathlib import Path

from macos_personal_mcp.process import NativeError

Buffer = bytes | mmap.mmap

Signature = tuple[int, int, int, int, int]


def signature(path: Path) -> Signature:
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


@dataclass
class Budget:
    deadline: float
    remaining: int = 2_000_000

    def check(self, units: int = 1) -> None:
        self.remaining -= units
        if self.remaining < 0:
            raise NativeError("search_limit", "Native search exhausted its work budget")
        if time.monotonic() >= self.deadline:
            raise NativeError("deadline", "Native search exceeded its absolute deadline")


def bounded_read(path: Path, maximum: int) -> bytes:
    before = signature(path)
    if before[2] > maximum:
        raise NativeError("native_format", "Native file exceeds its format bound")
    with path.open("rb") as stream:
        data = stream.read(maximum + 1)
    if len(data) != before[2] or signature(path) != before:
        raise NativeError("source_changed", "Native file changed during capture")
    return data


def u32(data: Buffer, pos: int) -> int:
    if pos < 0 or pos + 4 > len(data):
        raise NativeError("native_format", "Native integer exceeds captured data")
    return int.from_bytes(data[pos : pos + 4], "little")


def leb(data: Buffer, pos: int, end: int | None = None) -> tuple[int, int]:
    stop = len(data) if end is None else min(end, len(data))
    value = 0
    for shift in range(0, 70, 7):
        if pos >= stop:
            raise NativeError("native_format", "Truncated native varint")
        byte = data[pos]
        pos += 1
        value |= (byte & 127) << shift
        if byte < 128:
            if value >= 2**64:
                break
            return value, pos
    raise NativeError("native_format", "Oversized native varint")


def variable(data: Buffer, pos: int, end: int | None = None) -> tuple[int, int]:
    stop = len(data) if end is None else min(end, len(data))
    if not 0 <= pos < stop:
        raise NativeError("native_format", "Truncated prefix integer")
    byte = data[pos]
    pos += 1
    count = 0
    while count < 8 and byte & (128 >> count):
        count += 1
    if pos + count > stop:
        raise NativeError("native_format", "Truncated prefix integer payload")
    value = byte & ((1 << (7 - count)) - 1) if count < 5 else 0
    for item in data[pos : pos + count]:
        value = (value << 8) | item
    return value, pos + count


def be64(data: Buffer, offset: int) -> int:
    if offset < 0 or offset + 8 > len(data):
        raise NativeError("native_format", "Native identity exceeds captured table")
    value: int = struct.unpack_from(">Q", data, offset)[0]
    return value
