"""Explicit public OS access requests, isolated from data reads and ordinary doctor calls."""

import threading
from collections.abc import Callable
from typing import Protocol

import Contacts as CN
import EventKit as EK
from Foundation import NSError

from macos_personal_mcp.access import access_granted
from macos_personal_mcp.models import (
    NativeAccessResult,
    NativePermissions,
    PermissionDomain,
    PermissionRequest,
)

type Completion = Callable[[bool, int | None], None]


def calendar_status(value: int) -> str:
    return {
        0: "not_determined",
        1: "restricted",
        2: "denied",
        3: "full_access",
        4: "write_only",
    }.get(value, "unknown")


def contacts_status(value: int) -> str:
    return {0: "not_determined", 1: "restricted", 2: "denied", 3: "authorized", 4: "limited"}.get(
        value, "unknown"
    )


def native_permissions() -> NativePermissions:
    return NativePermissions(
        calendar=calendar_status(EK.EKEventStore.authorizationStatusForEntityType_(0)),
        contacts=contacts_status(CN.CNContactStore.authorizationStatusForEntityType_(0)),
    )


class AccessBackend(Protocol):
    def status(self, domain: PermissionDomain) -> str: ...
    def request(self, domain: PermissionDomain, completion: Completion) -> None: ...


class PublicAccessBackend:
    def __init__(self) -> None:
        self.calendar_store: EK.EKEventStore | None = None
        self.contact_store: CN.CNContactStore | None = None

    def status(self, domain: PermissionDomain) -> str:
        if domain == "calendar":
            return calendar_status(EK.EKEventStore.authorizationStatusForEntityType_(0))
        return contacts_status(CN.CNContactStore.authorizationStatusForEntityType_(0))

    def request(self, domain: PermissionDomain, completion: Completion) -> None:
        def receive(granted: bool, error: NSError | None) -> None:
            completion(granted, error.code() if error is not None else None)

        if domain == "calendar":
            self.calendar_store = EK.EKEventStore.alloc().init()
            self.calendar_store.requestFullAccessToEventsWithCompletion_(receive)
        else:
            self.contact_store = CN.CNContactStore.alloc().init()
            self.contact_store.requestAccessForEntityType_completionHandler_(0, receive)


def request_access(
    request: PermissionRequest, backend: AccessBackend | None = None, *, timeout: float = 90
) -> NativeAccessResult:
    selected = backend if backend is not None else PublicAccessBackend()
    before = selected.status(request.domain)
    attempted = before == "not_determined" or (
        request.domain == "calendar" and before == "write_only"
    )
    completed = False
    error_code: int | None = None
    if attempted:
        done = threading.Event()

        def receive(granted: bool, error: int | None) -> None:
            nonlocal error_code
            error_code = error
            done.set()

        selected.request(request.domain, receive)
        completed = done.wait(timeout)
    after = selected.status(request.domain)
    return NativeAccessResult(
        domain=request.domain,
        before=before,
        after=after,
        request_attempted=attempted,
        request_completed=completed,
        granted=access_granted(request.domain, after),
        error_code=error_code,
    )
