"""Explicit tool registry, strict dispatch and independently failing domains."""

import json
import platform
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

from mcp_types import Tool, ToolAnnotations
from pydantic import ValidationError

from macos_personal_mcp import __version__
from macos_personal_mcp.access import (
    CONTACTS_HOST_REQUIREMENT,
    access_action,
    access_granted,
    host_context,
)
from macos_personal_mcp.body_index import BodyIndex
from macos_personal_mcp.calendar_open import CalendarOpener
from macos_personal_mcp.calendar_writes import CalendarExecutor, EventOutcome
from macos_personal_mcp.mail_native.client import NativeSearchClient
from macos_personal_mcp.mail_native.contracts import NativeSearch, NativeSearchResult
from macos_personal_mcp.models import (
    AccessAction,
    Account,
    Accounts,
    BodySearchPage,
    CalendarKey,
    Calendars,
    CalendarScope,
    Capability,
    Contact,
    ContactKey,
    Contacts,
    ContactsBackend,
    ContactsScope,
    Doctor,
    Empty,
    Event,
    EventOpenResult,
    Events,
    Failure,
    MailAccountKey,
    Mailboxes,
    MailScope,
    Message,
    MessageKey,
    MessagePage,
    MessageSource,
    Model,
    NativeAccessResult,
    NativePermissions,
    PermissionDomain,
    PermissionRequest,
    PermissionResult,
    SourceKey,
)
from macos_personal_mcp.native import Bridge, NativeBridge
from macos_personal_mcp.permissions import (
    REVIEWED_TOOLS,
    ApprovalPolicy,
    ApprovalReport,
    LoadedConfig,
    ToolApproval,
)
from macos_personal_mcp.process import NativeError
from macos_personal_mcp.safety import (
    EventCreate,
    MailPreview,
    MailSend,
    preview_mail,
    refuse_write,
)
from macos_personal_mcp.sending import MailExecutor, SendOutcome


@dataclass(frozen=True)
class Definition:
    name: str
    description: str
    input: type[Model]
    output: type[Model]
    mutates: bool = False
    native: bool = True


READS = (
    Definition(
        "mail_search",
        "Primary Mail search across locally stored subject, sender and body by default; select search_fields or filter account/mailbox/received dates. AND tokens may match across selected fields; quoted exact phrases stay within one field. Returns matched_fields and excerpts. Optional single-word ASCII fuzzy_distance 1-2; no FTS operators. Small scopes scan MIME; large scopes reuse Apple Spotlight with native metadata matching. No shadow body database. Inspect coverage/partial counts; nonexhaustive negatives are not proof of absence.",
        NativeSearch,
        NativeSearchResult,
        native=False,
    ),
    Definition(
        "doctor",
        "Inspect capability gates without prompting or test objects.",
        Empty,
        Doctor,
        native=False,
    ),
    Definition(
        "mail_list_accounts", "Configured native Mail accounts; no body reads.", Empty, Accounts
    ),
    Definition(
        "mail_list_mailboxes",
        "Nested mailbox paths and scoped native unread counts.",
        MailAccountKey,
        Mailboxes,
    ),
    Definition(
        "mail_list_messages",
        "Newest metadata in an explicit account/folder/date range; optional unread filter.",
        MailScope,
        MessagePage,
    ),
    Definition(
        "mail_search_headers",
        "Native sender/subject search within explicit dates; never body search.",
        MailScope,
        MessagePage,
    ),
    Definition(
        "mail_get_message",
        "Read a bounded body and headers after validating expected RFC Message-ID; body_truncated reports omitted text. Mail-rendered body text may add whitespace/separators; use decoded source for fidelity checks. Attachments are metadata only (name/ID/approximate bytes), not downloaded files. Reports read_before/read_after; fails on an observed state change and never restores flags. No mark-read/unread tool is implemented.",
        MessageKey,
        Message,
    ),
    Definition(
        "mail_get_source",
        "Read complete bounded raw RFC/MIME source after identity validation; reject unavailable/oversized sources. Decode MIME charset/transfer encoding before comparing text or attachment bytes. Inspect all body MIME fragments, not only the first HTML part, and exclude named text attachments. Source is not rendered HTML or a dedicated attachment-download tool. Reports read_before/read_after; fails on an observed state change and never restores flags. No mark-read/unread tool is implemented.",
        SourceKey,
        MessageSource,
    ),
    Definition(
        "calendar_list_calendars",
        "Public EventKit calendars with source, writability and subscription fields; visible scope may be incomplete.",
        Empty,
        Calendars,
    ),
    Definition(
        "calendar_list_events",
        "EventKit occurrences within explicit selected visible calendars and dates.",
        CalendarScope,
        Events,
    ),
    Definition(
        "calendar_search_events",
        "Title/location/notes on EventKit occurrences within explicit selected-calendar/date scope.",
        CalendarScope,
        Events,
    ),
    Definition(
        "calendar_get_event",
        "Exact EventKit identity in selected calendar; recurring reads require the listed occurrence_start.",
        CalendarKey,
        Event,
    ),
    Definition(
        "contacts_list",
        "Paginate native Contacts, including labeled phones/emails and postal addresses; inspect backend coverage and access limits.",
        ContactsScope,
        Contacts,
    ),
    Definition(
        "contacts_search",
        "Name/organization/phone/email substring search; preserve duplicate candidates.",
        ContactsScope,
        Contacts,
    ),
    Definition(
        "contacts_get",
        "Read an exact persistent contact ID; do not select by display name.",
        ContactKey,
        Contact,
    ),
    Definition(
        "mail_prepare_send",
        "Validate configured sender and exact addresses/attachment identities; PREVIEW ONLY, no consent or send. Body is Unicode plain text: no HTML/Markdown/RTF renderer, custom link labels or inline images. Supply full URLs; recipient-client linking is not guaranteed. Mail may add a leading blank paragraph and quote wrapper after draft verification. Up to 20 absolute regular-file attachments, 20,000,000 bytes each and 50,000,000 total; hashes bind reviewed bytes. These are input limits, not provider delivery limits. Mail controls attachment placement and may normalize Unicode filenames.",
        MailSend,
        MailPreview,
        native=False,
    ),
)
LEGACY_READS = (
    Definition(
        "mail_search_legacy",
        "Compatibility-only FTS5 search; prefer mail_search. Requires explicit startup enablement and a manually refreshed complete exact account/folder/date scope. Searches cached body/subject/sender with FTS5 operators, accent folding and relevance ranking; semantics differ from mail_search. Rejects stale/incomplete indexes; never silently substitutes another backend.",
        MailScope,
        BodySearchPage,
        native=False,
    ),
)
SETUP = (
    Definition(
        "request_permissions",
        "Explicit setup only: request macOS access for one selected Calendar or Contacts domain after the user asks to connect it. May show an OS consent dialog for this app/helper; no data is read or created and write executors remain disabled in read-only mode. Run doctor first and follow next_actions. A compatible host with not-determined access needs a first request; a known missing host entitlement needs an app update, not repeated requests or Settings toggles. Use this same desktop connection, not an unrelated Terminal process. Contacts remains read-only.",
        PermissionRequest,
        PermissionResult,
        mutates=True,
        native=False,
    ),
)
WRITES = (
    Definition(
        "mail_send",
        "External email with To/CC/BCC/attachments. Unicode plain-text body only; HTML/Markdown/RTF styling, custom link labels and inline images are unsupported. Supply full URLs; client linking is not guaranteed. Mail may add a leading blank paragraph and quote wrapper after draft verification. Attachments: up to 20 absolute regular files, 20,000,000 bytes each, 50,000,000 total; reviewed bytes are frozen before dispatch. Provider limits may be lower. Mail controls attachment placement and may normalize Unicode filenames. Requires locally enabled executor; startup approval policy chooses native confirmation or host/model delegation. Accepted means Mail accepted the command, not confirmed delivery, formatting or received attachment bytes. Verify Sent/receipt and decode recipient MIME when proof is needed. Never retry uncertain outcomes.",
        MailSend,
        SendOutcome,
        mutates=True,
        native=False,
    ),
    Definition(
        "calendar_create_event",
        "Create a timed or all-day event in one exact writable calendar when locally enabled; startup policy chooses native confirmation or host/model delegation. No attendees or fallback calendar.",
        EventCreate,
        EventOutcome,
        mutates=True,
        native=False,
    ),
    Definition(
        "calendar_open_event",
        "Visible native Calendar show for an exact current nonrecurring EventKit item; requires explicit local enablement. Recurring occurrence opening unavailable.",
        CalendarKey,
        EventOpenResult,
        mutates=True,
        native=False,
    ),
)


class Service:
    def __init__(
        self,
        *,
        read_only: bool = True,
        enable_legacy_mail_search: bool = False,
        bridge: Bridge | None = None,
        mail_executor: MailExecutor | None = None,
        body_index: BodyIndex | None = None,
        calendar_executor: CalendarExecutor | None = None,
        calendar_opener: CalendarOpener | None = None,
        approval_config: LoadedConfig | None = None,
        contacts_backend: ContactsBackend = "framework",
    ) -> None:
        self.native_search = NativeSearchClient()
        self.read_only = read_only
        self.enable_legacy_mail_search = enable_legacy_mail_search
        self.contacts_backend: ContactsBackend = contacts_backend
        self.bridge = bridge if bridge is not None else NativeBridge(contacts_backend)
        self.mail_executor = mail_executor
        self.body_index = body_index if body_index is not None else BodyIndex()
        self.calendar_executor = calendar_executor
        self.calendar_opener = calendar_opener
        self.approval_config = approval_config
        self.approval_policy = (
            approval_config.config.approval if approval_config is not None else ApprovalPolicy()
        )
        self.approval_policy.validate_tools({d.name for d in READS + SETUP + LEGACY_READS + WRITES})
        for name, executor in (
            ("mail_send", mail_executor),
            ("calendar_create_event", calendar_executor),
        ):
            if executor is not None and executor.approval_mode != self.approval_policy.mode_for(
                name
            ):
                raise NativeError(
                    "permission_config", "Executor and local approval policy disagree"
                )

    def approval_report(self) -> ApprovalReport:
        exposed = {t.name for t in self.tools()}
        return ApprovalReport(
            config_path=str(self.approval_config.path)
            if self.approval_config is not None
            else None,
            config_loaded=self.approval_config.loaded
            if self.approval_config is not None
            else False,
            default=self.approval_policy.default,
            read_only=self.read_only,
            tools=[
                ToolApproval(
                    tool=d.name,
                    mode=self.approval_policy.mode_for(d.name),
                    exposed=d.name in exposed,
                    executor_enabled=d.name in exposed
                    and (
                        not d.mutates
                        or d.name == "request_permissions"
                        or (
                            not self.read_only
                            and (
                                (d.name == "mail_send" and self.mail_executor is not None)
                                or (
                                    d.name == "calendar_create_event"
                                    and self.calendar_executor is not None
                                )
                                or (
                                    d.name == "calendar_open_event"
                                    and self.calendar_opener is not None
                                )
                            )
                        )
                    ),
                    server_dialog=d.name in REVIEWED_TOOLS
                    and not self.read_only
                    and (
                        (d.name == "mail_send" and self.mail_executor is not None)
                        or (
                            d.name == "calendar_create_event" and self.calendar_executor is not None
                        )
                    )
                    and self.approval_policy.mode_for(d.name) == "native",
                )
                for d in READS + SETUP + LEGACY_READS + WRITES
            ],
        )

    def description(self, definition: Definition) -> str:
        if definition.name.startswith("contacts_"):
            return (
                definition.description
                + " "
                + CONTACTS_HOST_REQUIREMENT
                + (
                    " Selected backend: Contacts.app Apple Events; Automation consent also required and alone does not prove data access; no UI automation; IDs use contacts-app: prefix, records not unified across sources."
                    if self.contacts_backend == "contacts-app"
                    else " Selected backend: public unified CNContactStore."
                )
            )
        if definition.name == "request_permissions":
            return (
                definition.description
                + " "
                + CONTACTS_HOST_REQUIREMENT
                + (
                    " Contacts setup requests Automation to Contacts.app and may open it in the background. granted=true covers that Automation grant only; run doctor and verify a read before claiming Contacts works."
                    if self.contacts_backend == "contacts-app"
                    else ""
                )
            )
        if definition.name not in REVIEWED_TOOLS:
            return definition.description
        mode = self.approval_policy.mode_for(definition.name)
        return definition.description + (
            " Server policy: native; exact independent human dialog required."
            if mode == "native"
            else " Server policy: host; no server dialog, host/model responsible for consent."
        )

    def tools(self) -> list[Tool]:
        definitions = READS + SETUP if self.read_only else READS + SETUP + WRITES
        if self.enable_legacy_mail_search:
            definitions += LEGACY_READS
        return [
            Tool(
                name=d.name,
                description=self.description(d),
                input_schema=d.input.model_json_schema(),
                output_schema=d.output.model_json_schema(),
                annotations=ToolAnnotations(
                    read_only_hint=not d.mutates,
                    destructive_hint=d.mutates
                    and d.name not in {"calendar_open_event", "request_permissions"},
                    idempotent_hint=not d.mutates or d.name == "calendar_open_event",
                    open_world_hint=True,
                ),
            )
            for d in definitions
        ]

    async def doctor(self) -> Doctor:
        permissions: NativePermissions | None = None
        try:
            permissions = await self.bridge.call("permissions", Empty(), NativePermissions)
            permission_note = "Native authorization status inspected without a permission request"
        except NativeError as error:
            permission_note = error.detail
        contacts_framework_status: str | None = None
        if self.contacts_backend == "contacts-app":
            try:
                framework_permissions = await self.bridge.call(
                    "contacts_framework_permissions", Empty(), NativePermissions
                )
                contacts_framework_status = framework_permissions.contacts
            except NativeError:
                contacts_framework_status = "unknown"
        try:
            next((Path.home() / "Library" / "Mail").iterdir(), None)
            mail_source = "Mail root readable; no schema/body corpus coverage is established"
            mail_status = "root_readable"
        except FileNotFoundError:
            mail_source = (
                "Local Mail storage is absent; configure Mail and let it synchronize first"
            )
            mail_status = "missing"
        except OSError:
            mail_source = "Mail filesystem root is denied; authorized public Mail API ingestion is independent"
            mail_status = "denied"
        actions = [
            access_action(
                "calendar", permissions.calendar if permissions is not None else "unknown"
            ),
            access_action(
                "contacts",
                permissions.contacts if permissions is not None else "unknown",
                self.contacts_backend,
                contacts_framework_status,
            ),
            AccessAction(
                capability="mail_files",
                status=mail_status,
                action="ready"
                if mail_status == "root_readable"
                else "open_settings"
                if mail_status == "denied"
                else "diagnose_host",
                settings_path="System Settings → Privacy & Security → Full Disk Access"
                if mail_status == "denied"
                else None,
                instructions=[
                    mail_source,
                    "If denied, enable Full Disk Access for the actual launching app/helper shown by macOS, restart it if requested, and verify a real search. This tool cannot grant Full Disk Access."
                    if mail_status == "denied"
                    else "Configure the native Mail account and allow local synchronization before retrying."
                    if mail_status == "missing"
                    else "Verify a representative mail_search; a readable root is not proof of full search access or coverage.",
                ],
            ),
        ]
        permission_states: list[tuple[PermissionDomain, str]] = [
            ("calendar", permissions.calendar if permissions is not None else "unknown"),
            ("contacts", permissions.contacts if permissions is not None else "unknown"),
        ]
        return Doctor(
            server_version=__version__,
            python=platform.python_version(),
            sdk=version("mcp"),
            read_only=self.read_only,
            permissions=permissions,
            host=await host_context(),
            next_actions=actions,
            capabilities=[
                Capability(
                    capability=domain + "_permission",
                    state="unverified"
                    if permissions is None
                    or (
                        domain == "contacts"
                        and self.contacts_backend == "contacts-app"
                        and status == "authorized"
                        and contacts_framework_status not in {"authorized", "limited"}
                    )
                    else "available"
                    if access_granted(domain, status)
                    else "blocked",
                    detail="OS authorization only; actual data reads remain separately verified. "
                    + " ".join(
                        access_action(
                            domain, status, self.contacts_backend, contacts_framework_status
                        ).instructions
                    ),
                )
                for domain, status in permission_states
            ]
            + [
                Capability(
                    capability="server_approval",
                    state="available",
                    detail="Local startup policy: "
                    + ", ".join(
                        f"{name}={self.approval_policy.mode_for(name)}"
                        for name in sorted(REVIEWED_TOOLS)
                    )
                    + "; host approval rules remain independent",
                ),
                Capability(capability="native_reads", state="unverified", detail=permission_note),
                Capability(
                    capability="calendar_create",
                    state="unverified"
                    if self.calendar_executor is not None and not self.read_only
                    else "blocked",
                    detail="Native executor and durable journal enabled; server approval follows local startup policy; save outcomes are checked against the payload"
                    if self.calendar_executor is not None and not self.read_only
                    else "Calendar execution disabled in this launch mode",
                ),
                Capability(
                    capability="full_body_search",
                    state="unverified",
                    detail="Primary mail_search searches native subject/sender/body on demand with explicit coverage. "
                    + (
                        "Compatibility-only mail_search_legacy is enabled with separate FTS5 semantics and explicit cache maintenance. "
                        if self.enable_legacy_mail_search
                        else "Legacy FTS5 search is disabled and absent from this tool registry. "
                    )
                    + mail_source,
                ),
                Capability(
                    capability="email_send",
                    state="unverified"
                    if self.mail_executor is not None and not self.read_only
                    else "blocked",
                    detail="Native executor and durable journal enabled; server approval follows local startup policy; delivery still needs verification"
                    if self.mail_executor is not None and not self.read_only
                    else "Mail execution disabled in this launch mode; exact human review is required when enabled",
                ),
                Capability(
                    capability="email_composition",
                    state="unverified",
                    detail="Unicode plain-text input; no HTML/Markdown/RTF renderer, custom link labels or inline images. Full URL text is supported; recipient-client linking is not guaranteed. Mail can add a leading blank paragraph and quote wrapper after draft checks. Attachments: <=20 absolute regular files, <=20,000,000 bytes each and <=50,000,000 total; provider limits may be lower. Accepted sends do not verify delivery, final formatting or received attachment bytes. See docs/MAIL_CAPABILITIES.md for scoped evidence, not a guarantee for this host.",
                ),
                Capability(
                    capability="email_read_state_write",
                    state="blocked",
                    detail="No mark-read or mark-unread tool is implemented, regardless of send enablement. Reads report/filter read state without setting it; targeted reads fail on an observed change and never restore flags. Native API feasibility is not an exposed MCP capability.",
                ),
                Capability(
                    capability="invitations",
                    state="blocked",
                    detail="Attendee creation is excluded by owner decision; native macOS integration only, no direct provider APIs",
                ),
                Capability(
                    capability="desktop",
                    state="unverified",
                    detail="A subprocess client does not prove desktop registration/access",
                ),
            ],
        )

    async def call(self, name: str, arguments_json: str) -> Model:
        definitions = READS + SETUP + WRITES
        if self.enable_legacy_mail_search:
            definitions += LEGACY_READS
        definition = next((d for d in definitions if d.name == name), None)
        if definition is None:
            return Failure(code="unknown_tool", message="Unknown tool")
        try:
            # Check effects before touching attachments, native apps or accepting hidden tool inputs.
            if definition.mutates and self.read_only and name != "request_permissions":
                refuse_write(read_only=True)
            request = definition.input.model_validate_json(arguments_json)
            if name == "request_permissions":
                if not isinstance(request, PermissionRequest):
                    raise NativeError("invalid_input", "Expected selected permission domain")
                try:
                    result = await self.bridge.call(name, request, NativeAccessResult)
                except NativeError as error:
                    raise NativeError(
                        "permission_request_failed",
                        "The native access request did not establish a grant (" + error.code + "). "
                        "Run doctor in this same desktop connection and inspect its host context. "
                        "Check for a pending OS dialog; the responsible host may need valid privacy usage descriptions. "
                        "Do not assume a Settings entry exists or that access was denied.",
                    ) from error
                if result.domain != request.domain:
                    raise NativeError(
                        "invalid_native_response", "Permission result belongs to a different domain"
                    )
                if result.route != (
                    self.contacts_backend if request.domain == "contacts" else "framework"
                ):
                    raise NativeError(
                        "invalid_native_response",
                        "Permission result belongs to a different startup route",
                    )
                guidance = access_action(request.domain, result.after, result.route)
                if (
                    result.domain == "contacts"
                    and result.route == "framework"
                    and result.before == "not_determined"
                    and result.after == "denied"
                    and result.error_code == 100
                ):
                    guidance = AccessAction(
                        capability="contacts",
                        status="denied",
                        action="diagnose_host",
                        settings_path="System Settings → Privacy & Security → Contacts",
                        instructions=[
                            "macOS refused the Contacts request (error 100). This alone does not prove the user declined it.",
                            CONTACTS_HOST_REQUIREMENT,
                            "If no Contacts dialog or Settings entry appeared, inspect the responsible host's signed declarations. Repeating the request will not add missing declarations. See docs/PERMISSIONS.md; no fallback is enabled.",
                            "If the user actually declined a dialog and the host is listed in Contacts settings, enable that existing entry and verify again.",
                            "MCP send/create approval policy is separate and cannot grant OS Contacts access.",
                        ],
                    )
                elif (
                    result.request_attempted and not result.request_completed and not result.granted
                ):
                    guidance = AccessAction(
                        capability=request.domain,
                        status=result.after,
                        action="diagnose_host",
                        instructions=[
                            "The access request did not complete within 90 seconds. Check for a pending macOS dialog before retrying.",
                            "Run doctor in this same desktop connection after the dialog is resolved.",
                        ],
                    )
                elif (
                    result.request_attempted
                    and not result.granted
                    and result.after == "not_determined"
                ):
                    guidance = AccessAction(
                        capability=request.domain,
                        status=result.after,
                        action="diagnose_host",
                        instructions=[
                            "The native request completed but macOS recorded no permission decision. Check for a pending dialog and the responsible host's privacy usage descriptions.",
                            "Run doctor in this same connection; do not report denied access or repeatedly request it without diagnosing the host.",
                        ],
                    )
                elif (
                    result.request_attempted
                    and result.request_completed
                    and result.after == "write_only"
                ):
                    guidance = access_action("calendar", "denied").model_copy(
                        update={"status": "write_only"}
                    )
                return PermissionResult(
                    domain=result.domain,
                    route=result.route,
                    before=result.before,
                    after=result.after,
                    request_attempted=result.request_attempted,
                    request_completed=result.request_completed,
                    granted=result.granted,
                    error_code=result.error_code,
                    guidance=guidance,
                    host=await host_context(),
                )
            if definition.mutates:
                if name == "calendar_create_event" and self.calendar_executor is not None:
                    if not isinstance(request, EventCreate):
                        raise NativeError("invalid_input", "Expected event creation payload")
                    return await self.calendar_executor.create(request)
                if name == "mail_send" and self.mail_executor is not None:
                    if not isinstance(request, MailSend):
                        raise NativeError("invalid_input", "Expected MailSend")
                    accounts = await self.bridge.call("mail_list_accounts", Empty(), Accounts)
                    self.validate_sender(request.sender, accounts.accounts)
                    return await self.mail_executor.send(request)
                if name == "calendar_open_event":
                    if self.calendar_opener is None:
                        raise NativeError(
                            "open_disabled", "Calendar UI opening disabled in this launch mode"
                        )
                    if not isinstance(request, CalendarKey):
                        raise NativeError("invalid_input", "Expected exact event identity")
                    return await self.calendar_opener.open(request)
                refuse_write(read_only=False)
            if name == "doctor":
                return await self.doctor()
            if name == "mail_search":
                if not isinstance(request, NativeSearch):
                    raise NativeError("invalid_input", "Expected native Mail search scope")
                return await self.native_search.search(request)
            if name == "mail_search_legacy":
                if not isinstance(request, MailScope):
                    raise NativeError("invalid_input", "Expected explicit Mail scope")
                return await self.body_index.search(request, self.bridge)
            if name == "mail_prepare_send":
                if not isinstance(request, MailSend):
                    raise NativeError("invalid_input", "Expected MailSend")
                accounts = await self.bridge.call("mail_list_accounts", Empty(), Accounts)
                self.validate_sender(request.sender, accounts.accounts)
                return preview_mail(request)
            return await self.bridge.call(name, request, definition.output)
        except NativeError as error:
            return Failure(code=error.code, message=error.detail)
        except ValidationError:
            # Validation messages may echo bodies/addresses; release a redacted error instead.
            return Failure(
                code="invalid_input",
                message="Input or native output violates the published strict schema",
            )
        except OSError, ValueError:
            return Failure(
                code="operation_failed",
                message="Operation failed before any external write dispatch",
            )

    @staticmethod
    def validate_sender(sender: str, accounts: list[Account]) -> None:
        matches = [
            a
            for a in accounts
            if a.enabled and sender.casefold() in {v.casefold() for v in a.emails}
        ]
        if len(matches) != 1:
            raise NativeError(
                "sender_ambiguous",
                "Sender must identify exactly one enabled configured Mail account",
            )


def structured(model: Model) -> dict[str, object]:
    # SDK boundary only. Domain code uses validated models, never raw native dictionaries.
    result: dict[str, object] = json.loads(model.model_dump_json())
    return result
