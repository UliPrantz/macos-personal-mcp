"""Owner-selected startup approval policy, separate from tool input and host policy."""

import json
import os
import stat
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import Field

from macos_personal_mcp.models import Model
from macos_personal_mcp.process import NativeError

type ApprovalMode = Literal["native", "host"]
REVIEWED_TOOLS = frozenset({"mail_send", "calendar_create_event"})


class ApprovalPolicy(Model):
    default: ApprovalMode = "native"
    mail: ApprovalMode | None = None
    calendar: ApprovalMode | None = None
    contacts: ApprovalMode | None = None
    tools: dict[str, ApprovalMode] = Field(default_factory=dict)

    def mode_for(self, tool: str) -> ApprovalMode:
        if tool in self.tools:
            return self.tools[tool]
        domain = tool.partition("_")[0]
        if domain == "mail" and self.mail is not None:
            return self.mail
        if domain == "calendar" and self.calendar is not None:
            return self.calendar
        if domain == "contacts" and self.contacts is not None:
            return self.contacts
        return self.default

    def validate_tools(self, known: set[str]) -> None:
        if self.tools.keys() - known:
            raise NativeError("permission_config", "Unknown tool name in local approval policy")


class LocalConfig(Model):
    approval: ApprovalPolicy = Field(default_factory=ApprovalPolicy)


@dataclass(frozen=True)
class LoadedConfig:
    config: LocalConfig
    path: Path
    loaded: bool


class ToolApproval(Model):
    tool: str
    mode: ApprovalMode
    exposed: bool
    executor_enabled: bool
    server_dialog: bool


class ApprovalReport(Model):
    config_path: str | None
    config_loaded: bool
    default: ApprovalMode
    read_only: bool
    tools: list[ToolApproval]
    precedence: str = (
        "tool > domain > default; read-only and executor launch gates remain independent"
    )


def default_config_path() -> Path:
    return Path.home() / "Library/Application Support/macos-personal-mcp/permissions.toml"


def load_config(path: Path | None = None) -> LoadedConfig:
    selected = path if path is not None else default_config_path()
    if not selected.is_absolute():
        raise NativeError("permission_config", "Approval config path must be absolute")
    try:
        fd = os.open(selected, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        if path is None:
            return LoadedConfig(LocalConfig(), selected, False)
        raise NativeError("permission_config", "Explicit approval config is missing") from None
    except OSError:
        raise NativeError(
            "permission_config", "Approval config is inaccessible or a symlink"
        ) from None
    try:
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
                raise NativeError(
                    "permission_config",
                    "Approval config must be an owned regular file, not group/world writable",
                )
            raw = stream.read(65_537)
        if len(raw) > 65_536:
            raise NativeError("permission_config", "Approval config exceeds 64 KiB")
        config = LocalConfig.model_validate_json(json.dumps(tomllib.loads(raw.decode("utf-8"))))
    except TypeError, ValueError:
        raise NativeError(
            "permission_config", "Invalid approval TOML/schema; no server started"
        ) from None
    return LoadedConfig(config, selected, True)
