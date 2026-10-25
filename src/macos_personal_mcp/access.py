"""Permission guidance and observed launch context; never grants access or reads app data."""

import os
import sys

from macos_personal_mcp.models import (
    AccessAction,
    HostContext,
    PermissionDomain,
    PermissionRequest,
)
from macos_personal_mcp.process import NativeError, run_child


def access_granted(domain: PermissionDomain, status: str) -> bool:
    return status == "full_access" if domain == "calendar" else status in {"authorized", "limited"}


def access_action(domain: PermissionDomain, status: str) -> AccessAction:
    name = "Calendars" if domain == "calendar" else "Contacts"
    settings = "System Settings → Privacy & Security → " + name
    if access_granted(domain, status):
        return AccessAction(
            capability=domain,
            status=status,
            action="ready",
            instructions=[
                "No permission change is needed for this process. Verify an actual read from this desktop connection.",
                "Only selected contacts are visible; expand access in Settings if you want more."
                if status == "limited"
                else "An OS grant does not certify every account or item is visible.",
            ],
            settings_path=settings if status == "limited" else None,
        )
    if status == "not_determined" or (domain == "calendar" and status == "write_only"):
        return AccessAction(
            capability=domain,
            status=status,
            action="request_permission",
            tool="request_permissions",
            arguments=PermissionRequest(domain=domain),
            instructions=[
                "For this user-requested feature, call request_permissions from the same desktop connection; the user decides in the native macOS dialog.",
                "macOS has not received a decision yet; there may be no Settings entry until the request."
                if status == "not_determined"
                else "Write-only Calendar access cannot read or validate the selected calendar. Request full access.",
                "Approve the native macOS dialog for the app/helper it names; run doctor and an actual read afterward.",
            ],
        )
    if status == "denied":
        return AccessAction(
            capability=domain,
            status=status,
            action="open_settings",
            settings_path=settings,
            instructions=[
                "Open "
                + settings
                + ". Enable access for the responsible app/helper named by macOS.",
                "The entry may be ChatGPT, Codex or a Python/helper process; do not assume it is named macos-personal.",
                "Choose full access for Calendar. Contacts remains read-only in this MCP.",
                "Restart the connection (and the named app/helper only if macOS asks), then run doctor and an actual read.",
            ],
        )
    if status == "restricted":
        return AccessAction(
            capability=domain,
            status=status,
            action="administrator",
            settings_path=settings,
            instructions=[
                "macOS reports a restriction. Ask the device administrator to review the relevant privacy/device policy.",
                "Repeated access requests or a different message/calendar payload will not lift that restriction.",
            ],
        )
    return AccessAction(
        capability=domain,
        status=status,
        action="diagnose_host",
        instructions=[
            "Authorization could not be established. Run doctor from the same desktop connection and inspect its host context.",
            "Do not infer denied access or tell the user to enable a nonexistent Settings entry.",
        ],
    )


def permission_problem(domain: PermissionDomain, status: str) -> str:
    action = access_action(domain, status)
    return f"{domain.capitalize()} access is {status}. " + " ".join(action.instructions)


async def host_context() -> HostContext:
    parent = os.getppid()
    command: str | None = None
    try:
        raw = await run_child(
            ["/bin/ps", "-p", str(parent), "-o", "comm="], timeout=2, max_bytes=8192
        )
        command = raw.decode("utf-8").strip() or None
    except NativeError, OSError, UnicodeError:
        pass
    return HostContext(
        executable=sys.executable,
        process_id=os.getpid(),
        parent_process_id=parent,
        parent_command=command,
    )
