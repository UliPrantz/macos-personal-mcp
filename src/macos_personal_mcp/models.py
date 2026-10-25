"""Strict JSON contracts. Native values must pass these contracts before release."""

from datetime import date, timedelta
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Text = Annotated[str, Field(min_length=1, max_length=4096)]


class Model(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class Empty(Model):
    pass


class Page(Model):
    offset: int = Field(default=0, ge=0, le=100_000)
    limit: int = Field(default=50, ge=1, le=200)


class MailAccountKey(Model):
    account_id: Text


class MailScope(Page):
    account_id: Text
    mailbox_path: list[Text] = Field(min_length=1, max_length=20)
    since: AwareDatetime
    before: AwareDatetime
    unread_only: bool = False
    query: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def dates_ordered(self) -> Self:
        if self.before <= self.since:
            raise ValueError("Require since < before; lower inclusive, upper exclusive")
        return self


class MessageKey(Model):
    account_id: Text
    mailbox_path: list[Text] = Field(min_length=1, max_length=20)
    local_id: int = Field(gt=0)
    expected_message_id: Text
    body_chars: int = Field(default=20_000, ge=0, le=100_000)


class SourceKey(Model):
    account_id: Text
    mailbox_path: list[Text] = Field(min_length=1, max_length=20)
    local_id: int = Field(gt=0)
    expected_message_id: Text
    max_source_chars: int = Field(default=4_000_000, ge=1, le=64_000_000)


class CalendarScope(Page):
    calendar_ids: list[Text] = Field(min_length=1, max_length=100)
    since: AwareDatetime
    before: AwareDatetime
    query: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def bounded_range(self) -> Self:
        if not timedelta(0) < self.before - self.since <= timedelta(days=366):
            raise ValueError("Require 0 < date range <= 366 days")
        if len(set(self.calendar_ids)) != len(self.calendar_ids):
            raise ValueError("Duplicate calendar identifiers")
        return self


class CalendarKey(Model):
    calendar_id: Text
    event_uid: Text
    occurrence_start: AwareDatetime | None = None


class ContactsScope(Page):
    query: str = Field(default="", max_length=500)


class ContactKey(Model):
    contact_id: Text


class Account(Model):
    id: str
    name: str
    emails: list[str]
    enabled: bool


class Accounts(Model):
    accounts: list[Account]
    local_account_id: Literal["__local__"] = "__local__"


class Mailbox(Model):
    path: list[str]
    unread_count: int = Field(ge=0)


class Mailboxes(Model):
    account_id: str
    mailboxes: list[Mailbox]


class Metadata(Model):
    local_id: int
    message_id: str
    subject: str
    sender: str
    received_at: AwareDatetime
    read: bool


class MessagePage(Model):
    messages: list[Metadata]
    total_matches: int = Field(ge=0)
    next_offset: int | None
    observed_at: AwareDatetime
    complete: bool
    scope: str
    pagination: str = "Offset over a fresh enumeration; concurrent source changes can shift pages"
    semantics: str = "Mail native sender/subject predicate; bodies are not searched"


class Attachment(Model):
    id: str
    name: str
    approximate_bytes: int = Field(ge=0)


class Message(Model):
    metadata: Metadata
    body: str
    body_characters: int = Field(ge=0)
    body_truncated: bool
    raw_headers: str
    attachments: list[Attachment]
    read_before: bool
    read_after: bool

    @model_validator(mode="after")
    def preserved_identity_and_flags(self) -> Self:
        if self.read_before != self.read_after:
            raise ValueError("Observed read state change; no flags were restored")
        return self


class MessageSource(Model):
    message_id: str
    source: str = Field(max_length=64_000_000)
    read_before: bool
    read_after: bool

    @model_validator(mode="after")
    def flags_preserved(self) -> Self:
        if self.read_before != self.read_after:
            raise ValueError("Observed read state change; no restoration attempted")
        return self


class IndexRequest(Model):
    scope: MailScope
    max_messages: int = Field(default=20, ge=1, le=200)
    rebuild: bool = False

    @model_validator(mode="after")
    def whole_scope(self) -> Self:
        if self.scope.query or self.scope.unread_only or self.scope.offset:
            raise ValueError("Index scopes cannot filter query/unread or skip offsets")
        return self


class IndexProgress(Model):
    scope_key: str
    total: int
    indexed: int
    unavailable: int
    pending: int
    attempted: int
    complete: bool
    inventory_stable: bool = True
    error_counts: dict[str, int] = Field(default_factory=dict)
    exclusions: list[str] = [
        "Attachment contents, inline media and embedded RFC attachments are not body text"
    ]
    observed_at: AwareDatetime
    source: str = "Public Mail RFC source API; explicit account/folder/date scope"


class BodySearchPage(MessagePage):
    indexed_at: AwareDatetime
    indexed_messages: int
    excerpts: list[str]
    query_ms: float
    semantics: str = "SQLite FTS5 unicode61 token/phrase matching across decoded body, subject and sender; Latin diacritics folded; not substring matching"


class Calendar(Model):
    id: str
    name: str
    writable: bool
    source_id: str | None = None
    source_name: str | None = None
    source_type: int | None = None
    calendar_type: int | None = None
    subscribed: bool | None = None
    immutable: bool | None = None


class Calendars(Model):
    calendars: list[Calendar]
    availability: str = "Calendars visible to public EventKit; reconcile with Calendar app before claiming all-account coverage"


class Attendee(Model):
    name: str
    email: str
    status: str
    url: str = ""
    role: int | None = None


class Event(Model):
    calendar_id: str
    uid: str
    title: str
    start: AwareDatetime
    end: AwareDatetime
    all_day: bool
    location: str
    notes: str
    url: str
    recurrence: str
    attendees: list[Attendee]
    external_id: str | None = None
    timezone_name: str | None = None
    timezone_source: str = "unavailable"
    all_day_start: date | None = None
    all_day_end_exclusive: date | None = None
    recurring: bool = False


class EventOpenTarget(Model):
    event: Event
    calendar_item_id: Text


class EventOpenResult(Model):
    event: Event
    show_acknowledged: Literal[True] = True
    detail: str = "Calendar accepted native show for the exact validated item; visual display requires human observation"


class Events(Model):
    events: list[Event]
    total_matches: int = Field(ge=0)
    next_offset: int | None
    complete: bool = False
    coverage: str = (
        "EventKit occurrences in explicitly selected visible calendars and bounded dates"
    )
    timezone: str = (
        "UTC instants plus native timezone; floating/all-day dates use the reported system timezone"
    )


class LabeledValue(Model):
    label: str
    value: str


class PostalAddress(Model):
    label: str
    street: str
    city: str
    state: str
    postal_code: str
    country: str
    country_code: str


class Contact(Model):
    id: str
    name: str
    first_name: str
    last_name: str
    organization: str
    job_title: str
    emails: list[LabeledValue]
    phones: list[LabeledValue]
    middle_name: str = ""
    postal_addresses: list[PostalAddress] = []


class Contacts(Model):
    contacts: list[Contact]
    total_matches: int = Field(ge=0)
    next_offset: int | None
    complete: bool = False
    coverage: str = "Visible contacts only; limited access cannot be ruled out"
    unavailable_fields: list[str] = ["notes (restricted entitlement)"]


type ContactsBackend = Literal["framework", "contacts-app"]


class NativePermissions(Model):
    calendar: str
    contacts: str
    contacts_backend: ContactsBackend = "framework"


type PermissionDomain = Literal["calendar", "contacts"]


class PermissionRequest(Model):
    domain: PermissionDomain


class AccessAction(Model):
    capability: Literal["calendar", "contacts", "mail_files"]
    status: str
    action: Literal[
        "ready", "request_permission", "open_settings", "administrator", "diagnose_host"
    ]
    instructions: list[str]
    settings_path: str | None = None
    tool: Literal["request_permissions"] | None = None
    arguments: PermissionRequest | None = None


class HostContext(Model):
    executable: str
    process_id: int
    parent_process_id: int
    parent_command: str | None = None
    attribution: str = (
        "Observed launch paths only. macOS chooses the responsible app/helper shown in its "
        "permission dialog and Settings; these paths do not establish that attribution. "
        "The entry may not be named macos-personal. Use this same desktop connection for requests and verification."
    )


class NativeAccessResult(Model):
    domain: PermissionDomain
    route: ContactsBackend = "framework"
    before: str
    after: str
    request_attempted: bool
    request_completed: bool
    granted: bool
    error_code: int | None = None

    @model_validator(mode="after")
    def observed_grant(self) -> Self:
        if self.domain == "calendar" and self.route != "framework":
            raise ValueError("Calendar authorization always uses the framework route")
        expected = (
            self.after == "full_access"
            if self.domain == "calendar"
            else self.after in {"authorized", "limited"}
        )
        if self.granted != expected:
            raise ValueError("Access grant must match the observed native status")
        return self


class PermissionResult(NativeAccessResult):
    guidance: AccessAction
    host: HostContext


class Capability(Model):
    capability: str
    state: Literal["available", "blocked", "unverified"]
    detail: str


class Doctor(Model):
    schema_version: Literal[1] = 1
    server_version: str = "unknown"
    python: str
    sdk: str
    read_only: bool
    permissions: NativePermissions | None
    capabilities: list[Capability]
    host: HostContext | None = None
    next_actions: list[AccessAction] = Field(default_factory=lambda: list[AccessAction]())


class Failure(Model):
    schema_version: Literal[1] = 1
    ok: Literal[False] = False
    code: str
    message: str
    complete: Literal[False] = False
    external_effects_dispatched: Literal[False] = False


class NativeReply(Model):
    result_json: str | None = None
    failure: Failure | None = None
