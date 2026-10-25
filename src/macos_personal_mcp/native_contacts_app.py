"""Public Apple Events to Contacts.app; never UI automation or a file-store fallback."""

import asyncio
import ctypes
import sys
import threading
from typing import Protocol

from Foundation import NSAppleEventDescriptor as Descriptor
from Foundation import NSError
from pydantic import JsonValue

from macos_personal_mcp.models import Model, NativeAccessResult, PermissionRequest
from macos_personal_mcp.native_access import Completion, request_access
from macos_personal_mcp.process import NativeError, run_child

BUNDLE = "com.apple.AddressBook"
# AppleEvents.h: wait for reply, never interact, never prompt for user consent.
READ_OPTIONS = 0x00000003 | 0x00000010 | 0x00020000


def code(value: str) -> int:
    return int.from_bytes(value.encode("ascii"), "big")


class AddressDescriptor(ctypes.Structure):
    # AEDataModel.h packs AEDesc to two-byte alignment, including on arm64.
    _layout_ = "ms"
    _pack_ = 2
    _fields_ = [("descriptor_type", ctypes.c_uint32), ("data_handle", ctypes.c_void_p)]


def permission_code(ask: bool = False) -> int:
    """Small C boundary for Apple's public nonprompting preflight/explicit request."""
    api = ctypes.CDLL(
        "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
    )
    create = api.AECreateDesc
    create.argtypes = [
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_long,
        ctypes.POINTER(AddressDescriptor),
    ]
    create.restype = ctypes.c_int32
    dispose = api.AEDisposeDesc
    dispose.argtypes = [ctypes.POINTER(AddressDescriptor)]
    dispose.restype = ctypes.c_int32
    determine = api.AEDeterminePermissionToAutomateTarget
    determine.argtypes = [
        ctypes.POINTER(AddressDescriptor),
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_ubyte,
    ]
    determine.restype = ctypes.c_int32
    target = AddressDescriptor()
    bundle = BUNDLE.encode("ascii")
    created = int(create(code("bund"), bundle, len(bundle), ctypes.byref(target)))
    if created != 0:
        raise NativeError("automation_preflight", "Could not construct the Contacts.app target")
    try:
        return int(determine(ctypes.byref(target), code("****"), code("****"), ask))
    finally:
        dispose(ctypes.byref(target))


def automation_status() -> str:
    return {0: "authorized", -1744: "not_determined", -1743: "denied", -600: "not_running"}.get(
        permission_code(), "unknown"
    )


class AutomationAccessBackend:
    def status(self, domain: str) -> str:
        return automation_status()

    def request(self, domain: str, completion: Completion) -> None:
        def ask() -> None:
            try:
                result = permission_code(True)
                completion(result == 0, result if result != 0 else None)
            except OSError, NativeError:
                completion(False, None)

        # Apple forbids potentially prompting preflight on the main thread.
        threading.Thread(target=ask, daemon=True).start()


def request_automation_access() -> NativeAccessResult:
    before = automation_status()
    if before == "not_running":
        # Only explicit setup opens the app, in the background, without activation.
        asyncio.run(run_child(["/usr/bin/open", "-gj", "-b", BUNDLE], timeout=10))
    result = request_access(PermissionRequest(domain="contacts"), AutomationAccessBackend())
    return result.model_copy(update={"route": "contacts-app", "before": before})


def object_specifier(
    want: str, form: str, selection: Descriptor, container: Descriptor | None = None
) -> Descriptor:
    record = Descriptor.recordDescriptor()
    for key, value in (
        ("want", Descriptor.descriptorWithTypeCode_(code(want))),
        ("form", Descriptor.descriptorWithEnumCode_(code(form))),
        ("seld", selection),
        ("from", container if container is not None else Descriptor.nullDescriptor()),
    ):
        record.setDescriptor_forKeyword_(value, code(key))
    result = record.coerceToDescriptorType_(code("obj "))
    if result is None:
        raise NativeError("automation_descriptor", "Public object specifier could not be formed")
    return result


def all_elements(kind: str, container: Descriptor | None = None) -> Descriptor:
    # typeAbsoluteOrdinal's four-character value is stored in native byte order.
    ordinal = Descriptor.descriptorWithDescriptorType_bytes_length_(
        code("abso"), code("all ").to_bytes(4, sys.byteorder), 4
    )
    if ordinal is None:
        raise NativeError("automation_descriptor", "Public ordinal could not be formed")
    return object_specifier(kind, "indx", ordinal, container)


def descriptor_value(value: Descriptor, depth: int = 0) -> JsonValue:
    kind = value.descriptorType()
    if kind == code("list"):
        if depth > 2 or value.numberOfItems() > 50_000:
            raise NativeError("candidate_limit", "Contacts.app result exceeds the bounded shape")
        items: list[JsonValue] = []
        for index in range(1, value.numberOfItems() + 1):
            item = value.descriptorAtIndex_(index)
            if item is None:
                raise NativeError("automation_response", "Contacts.app omitted a list element")
            items.append(descriptor_value(item, depth + 1))
        return items
    if kind == code("type") and value.typeCodeValue() == code("msng"):
        return ""
    if kind not in {code("utxt"), code("utf8"), code("TEXT")}:
        raise NativeError("automation_response", "Contacts.app returned an unexpected field type")
    text = value.stringValue()
    if text is None or len(text) > 65_536:
        raise NativeError(
            "automation_response", "Contacts.app returned an invalid or oversized field"
        )
    return text


class AppleEventsReader:
    """Read only the listed public dictionary fields using core/getd events."""

    def read(self, property_code: str, element: str | None = None) -> list[JsonValue]:
        people = all_elements("azf4")
        container = all_elements(element, people) if element is not None else people
        spec = object_specifier(
            "prop", "prop", Descriptor.descriptorWithTypeCode_(code(property_code)), container
        )
        event = (
            Descriptor.appleEventWithEventClass_eventID_targetDescriptor_returnID_transactionID_(
                code("core"),
                code("getd"),
                Descriptor.descriptorWithBundleIdentifier_(BUNDLE),
                -1,
                0,
            )
        )
        event.setParamDescriptor_forKeyword_(spec, code("----"))
        # This flag also handles a permission revocation/reset after preflight:
        # a read fails rather than displaying a consent prompt.
        return read_reply(event)


class ReadEvent(Protocol):
    def sendEventWithOptions_timeout_error_(
        self, options: int, timeout: float, error: None
    ) -> tuple[Descriptor | None, NSError | None]: ...


def read_reply(event: ReadEvent) -> list[JsonValue]:
    reply, error = event.sendEventWithOptions_timeout_error_(READ_OPTIONS, 5.0, None)
    if error is not None or reply is None:
        raise NativeError(
            "contacts_automation",
            "Contacts.app read failed; run doctor and explicit permission setup if needed",
        )
    failure = reply.paramDescriptorForKeyword_(code("errn"))
    if failure is not None and failure.int32Value() != 0:
        raise NativeError("contacts_automation", "Contacts.app rejected a read; no complete result")
    result = reply.paramDescriptorForKeyword_(code("----"))
    if result is None:
        raise NativeError("automation_response", "Contacts.app omitted the requested field")
    values = descriptor_value(result)
    if not isinstance(values, list):
        raise NativeError("automation_response", "Contacts.app did not return a record column")
    return values


def read_contacts(operation: str, payload: str) -> Model:
    from macos_personal_mcp.contacts_app import read_contacts as assemble

    status = automation_status()
    if status != "authorized":
        raise NativeError(
            "contacts_permission",
            "Contacts.app Automation is "
            + status
            + ". Run doctor, then explicit request_permissions for contacts; ordinary reads do not prompt.",
        )
    return assemble(operation, payload, AppleEventsReader())
