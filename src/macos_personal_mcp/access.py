"""Permission guidance and observed launch context; never grants access or reads app data."""

import os
import sys

from macos_personal_mcp.models import (
    AccessAction,
    ContactsBackend,
    HostContext,
    PermissionDomain,
    PermissionRequest,
)
from macos_personal_mcp.process import NativeError, run_child


def access_granted(domain: PermissionDomain, status: str) -> bool:
    return status == "full_access" if domain == "calendar" else status in {"authorized", "limited"}


def access_action(
    domain: PermissionDomain, status: str, contacts_backend: ContactsBackend = "framework"
) -> AccessAction:
    if domain == "contacts" and contacts_backend == "contacts-app":
        return automation_action(status)
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
                "If this server's request_permissions tool is missing, restart the existing MCP connection or open a fresh local chat; updating files does not refresh a running tool catalog.",
            ],
        )
    if status == "denied":
        return AccessAction(
            capability=domain,
            status=status,
            action="open_settings",
            settings_path=settings,
            instructions=[
                "macOS denial does not prove the user declined a dialog. A host entitlement/usage-description failure can also deny access before any prompt.",
                "Open "
                + settings
                + " only if the responsible app/helper has an entry there; then enable the requested access.",
                "The entry may be ChatGPT, Codex or a Python/helper process; do not assume it is named macos-personal.",
                "If no dialog or entry exists, diagnose the host's native privacy declarations first; repeated requests or MCP approval-mode changes cannot supply a missing host entitlement.",
                "For direct Contacts API access, a hardened host needs com.apple.security.personal-information.addressbook and NSContactsUsageDescription. If missing, that route needs a host fix or properly authorized helper. See docs/PERMISSION_MCP_COMPARISON.md for researched alternatives; no fallback is enabled."
                if domain == "contacts"
                else "Choose full access for Calendar; write-only cannot read or validate the selected calendar.",
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


def automation_action(status: str) -> AccessAction:
    settings = "System Settings → Privacy & Security → Automation"
    if status == "authorized":
        return AccessAction(
            capability="contacts",
            status=status,
            action="ready",
            instructions=[
                "Contacts uses Contacts.app through public Apple Events, not CNContactStore or screen automation. Verify a real read from this connection.",
                "Automation consent does not establish a direct Contacts API grant. Records are not unified across sources.",
            ],
        )
    if status in {"not_determined", "not_running"}:
        return AccessAction(
            capability="contacts",
            status=status,
            action="request_permission",
            tool="request_permissions",
            arguments=PermissionRequest(domain="contacts"),
            instructions=[
                "Call request_permissions for contacts from this same connection. Explicit setup may open Contacts.app in the background and request permission for this host to control Contacts.app.",
                "Approve the macOS Automation dialog if you want that access. Ordinary reads and doctor never prompt or launch Contacts.app.",
                "This route uses Automation settings, not the Contacts privacy pane; no direct Contacts API grant is implied.",
            ],
        )
    return AccessAction(
        capability="contacts",
        status=status,
        action="open_settings" if status == "denied" else "diagnose_host",
        settings_path=settings if status == "denied" else None,
        instructions=[
            "Contacts.app Automation is not authorized. If this host has an existing Automation entry, enable Contacts.app under it; do not look for this route in Contacts privacy settings.",
            "If no dialog or entry appeared, inspect the responsible host's com.apple.security.automation.apple-events entitlement and NSAppleEventsUsageDescription. Denial alone does not prove the user refused.",
            "No direct Contacts API or private database fallback will run. Recheck doctor and a real read from this same connection.",
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
