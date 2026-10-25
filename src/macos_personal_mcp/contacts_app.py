"""Typed assembly of batched Contacts.app columns, independent of native frameworks."""

from typing import Protocol

from pydantic import JsonValue

from macos_personal_mcp.models import (
    Contact,
    ContactKey,
    Contacts,
    ContactsScope,
    LabeledValue,
    Model,
    PostalAddress,
)
from macos_personal_mcp.process import NativeError

PREFIX = "contacts-app:"
# Codes come from Contacts.app's public scripting dictionary; notes/vCard excluded.
COLUMNS: dict[str, tuple[str, str | None]] = {
    "id": ("ID  ", None),
    "name": ("pnam", None),
    "first_name": ("azf7", None),
    "middle_name": ("az40", None),
    "last_name": ("azf8", None),
    "organization": ("az38", None),
    "job_title": ("az12", None),
    "email_values": ("az17", "az21"),
    "email_labels": ("az18", "az21"),
    "phone_values": ("az17", "az20"),
    "phone_labels": ("az18", "az20"),
    "address_labels": ("az18", "az27"),
    "street": ("az28", "az27"),
    "city": ("az29", "az27"),
    "state": ("az30", "az27"),
    "postal_code": ("az31", "az27"),
    "country": ("az32", "az27"),
    "country_code": ("az33", "az27"),
}


class ColumnReader(Protocol):
    def read(self, property_code: str, element: str | None = None) -> list[JsonValue]: ...


def text(value: JsonValue) -> str:
    if not isinstance(value, str):
        raise NativeError("automation_response", "Contacts.app column has an invalid text value")
    return value


def strings(value: JsonValue) -> list[str]:
    if not isinstance(value, list):
        raise NativeError("automation_response", "Contacts.app column has an invalid list value")
    return [text(item) for item in value]


def labeled(values: JsonValue, labels: JsonValue) -> list[LabeledValue]:
    rows, names = strings(values), strings(labels)
    if len(rows) != len(names):
        raise NativeError("contacts_changed", "Contacts.app field counts changed; retry the read")
    return [
        LabeledValue(label=label, value=value) for label, value in zip(names, rows, strict=True)
    ]


def read_contacts(operation: str, payload: str, reader: ColumnReader) -> Model:
    key = ContactKey.model_validate_json(payload) if operation == "contacts_get" else None
    if key is not None and not key.contact_id.startswith(PREFIX):
        raise NativeError(
            "contact_backend_identity", "This ID belongs to another Contacts backend; search again"
        )
    if operation not in {"contacts_list", "contacts_search", "contacts_get"}:
        raise NativeError("unknown_operation", "Unknown Contacts operation")
    request = ContactsScope.model_validate_json(payload) if key is None else ContactsScope()
    ids = [text(value) for value in reader.read(*COLUMNS["id"])]
    if len(ids) > 50_000:
        raise NativeError("candidate_limit", "Contacts.app exceeds the bounded enumeration limit")
    if any(not value for value in ids) or len(set(ids)) != len(ids):
        raise NativeError(
            "contact_identity", "Contacts.app returned absent or duplicate record IDs"
        )
    if key is not None and key.contact_id.removeprefix(PREFIX) not in ids:
        raise NativeError(
            "contact_not_found", "Exact contact is unavailable in the selected backend"
        )
    columns = {name: reader.read(*spec) for name, spec in COLUMNS.items() if name != "id"}
    if (
        any(len(values) != len(ids) for values in columns.values())
        or reader.read(*COLUMNS["id"]) != ids
    ):
        raise NativeError(
            "contacts_changed", "Contacts.app record order/count changed; retry the read"
        )
    rows: list[Contact] = []
    for index, identity in enumerate(ids):
        address_names = ("street", "city", "state", "postal_code", "country", "country_code")
        address_columns = {name: strings(columns[name][index]) for name in address_names}
        address_labels = strings(columns["address_labels"][index])
        if any(len(values) != len(address_labels) for values in address_columns.values()):
            raise NativeError(
                "contacts_changed", "Contacts.app address counts changed; retry the read"
            )
        rows.append(
            Contact(
                id=PREFIX + identity,
                name=text(columns["name"][index]),
                first_name=text(columns["first_name"][index]),
                middle_name=text(columns["middle_name"][index]),
                last_name=text(columns["last_name"][index]),
                organization=text(columns["organization"][index]),
                job_title=text(columns["job_title"][index]),
                emails=labeled(columns["email_values"][index], columns["email_labels"][index]),
                phones=labeled(columns["phone_values"][index], columns["phone_labels"][index]),
                postal_addresses=[
                    PostalAddress(
                        label=label,
                        **{name: values[position] for name, values in address_columns.items()},
                    )
                    for position, label in enumerate(address_labels)
                ],
            )
        )
    if key is not None:
        return next(row for row in rows if row.id == key.contact_id)
    needle = request.query.casefold()
    rows = [
        row
        for row in rows
        if not needle
        or any(
            needle in value.casefold()
            for value in [
                row.name,
                row.organization,
                *[v.value for v in row.emails],
                *[v.value for v in row.phones],
            ]
        )
    ]
    rows.sort(key=lambda row: (row.name.casefold(), row.id))
    end = request.offset + request.limit
    return Contacts(
        contacts=rows[request.offset : end],
        total_matches=len(rows),
        next_offset=end if end < len(rows) else None,
        complete=True,
        coverage="All records exposed by Contacts.app during this enumeration, not unified across sources; provider synchronization is outside this scope",
    )
