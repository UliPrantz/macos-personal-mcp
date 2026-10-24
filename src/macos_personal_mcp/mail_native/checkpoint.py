"""Persisted shadow view with change and stable-lag guards; never native writes."""

import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path

from macos_personal_mcp.mail_native.common import (
    Budget,
    Signature,
    bounded_read,
    leb,
    signature,
    u32,
)
from macos_personal_mcp.process import NativeError

ROOT = (
    Path.home()
    / "Library/Metadata/CoreSpotlight/NSFileProtectionCompleteUntilFirstUserAuthentication/index.spotlightV3"
)


@dataclass(frozen=True)
class Header:
    raw: bytes
    flags: int
    generation: int
    documents: int
    posting_regions: tuple[int, int, int]


def header(path: Path) -> Header:
    data = bounded_read(path, 4096)
    if len(data) != 4096 or u32(data, 0) != 114:
        raise NativeError("checkpoint_not_ready", "Unsupported or refreshing native header")
    state, flags, generation, size = struct.unpack_from("<4I", data, 4)
    if (
        state not in {0xD00D0DD0, 0xC001D00D}
        or not 24 <= size <= 4096
        or u32(data, size - 4) != size
    ):
        raise NativeError("checkpoint_not_ready", "Native header is not a readable checkpoint")
    values: list[int] = []
    pos = 20
    for _ in range(30):
        value, pos = leb(data, pos, size - 4)
        values.append(value)
    if not 0 < values[1] <= values[2] or values[0] + 1 != values[1]:
        raise NativeError("native_format", "Invalid native document limits")
    regions = values[14], values[15], values[16]
    if not 0 <= regions[0] <= regions[1] <= regions[2]:
        raise NativeError("native_format", "Invalid native posting arenas")
    return Header(data, flags, generation, values[1], regions)


class Checkpoint:
    def __init__(self, root: Path, budget: Budget) -> None:
        self.root, self.budget = root, budget
        self.state = bounded_read(root / "indexState", 28)
        if len(self.state) != 28:
            raise NativeError("native_format", "Unsupported native index state")
        values = struct.unpack("<7I", self.state)
        if values[0] not in {3, 4, 5} or max(values[3:]) > 256 or values[3:5] != values[5:7]:
            raise NativeError(
                "checkpoint_not_ready", "Native checkpoint prefix counts lag or are unsupported"
            )
        self.paths: dict[str, dict[str, Path]] = {}
        self.headers: dict[str, Header] = {}
        self.observed: dict[Path, Signature] = {root / "indexState": signature(root / "indexState")}
        self.originals: dict[Path, bytes] = {}
        for base in [str(i) for i in range(values[3])] + [f"live.{i}" for i in range(values[4])]:
            budget.check()
            shadow = root / f"{base}.shadowIndexHead"
            info = header(shadow)
            original = root / f"{base}.indexHead"
            raw = bounded_read(original, 4096)
            if len(raw) != 4096 or u32(raw, 0) != 114 or u32(raw, 12) != info.generation:
                raise NativeError("checkpoint_not_ready", "Native shadow generation lags original")
            self.originals[original] = raw
            self.observed[original] = signature(original)
            mapping = {"indexHead": shadow, "indexGroups": root / f"{base}.shadowIndexGroups"}
            for name in ("indexDirectory", "indexCompactDirectory", "indexArrays", "indexTermIds"):
                if name == "indexTermIds" and info.flags & 4:
                    continue
                physical = name if info.flags & 2 else "shadow" + name[0].upper() + name[1:]
                mapping[name] = root / f"{base}.{physical}"
            for name in ("indexPostings", "indexPositions", "indexIds"):
                mapping[name] = root / f"{base}.{name}"
            if (
                signature(mapping["indexGroups"])[2] < info.documents
                or signature(mapping["indexIds"])[2] < 8 * info.documents
            ):
                raise NativeError("native_format", "Native identity tables are truncated")
            for path in mapping.values():
                self.observed[path] = signature(path)
            self.headers[base], self.paths[base] = info, mapping
        self.check()

    def check(self) -> None:
        self.budget.check()
        if bounded_read(self.root / "indexState", 28) != self.state:
            raise NativeError("source_changed", "Native index state changed")
        for base, mapping in self.paths.items():
            self.budget.check()
            if bounded_read(mapping["indexHead"], 4096) != self.headers[base].raw:
                raise NativeError("source_changed", "Native shadow header changed")
        for path, raw in self.originals.items():
            if bounded_read(path, 4096) != raw:
                raise NativeError("source_changed", "Native current header changed")
        for path, observed in self.observed.items():
            if signature(path) != observed:
                raise NativeError("source_changed", "Native checkpoint file changed")

    def digest(self) -> str:
        value = hashlib.sha256(self.state)
        for base, info in self.headers.items():
            value.update(base.encode())
            value.update(info.raw)
        return value.hexdigest()
