"""No permission prompts or scans at process startup."""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from pydantic import ValidationError

from macos_personal_mcp.calendar_open import NativeCalendarOpener
from macos_personal_mcp.calendar_writes import native_calendar_executor
from macos_personal_mcp.models import ContactsBackend, Failure, IndexRequest, MailScope
from macos_personal_mcp.native import NativeBridge
from macos_personal_mcp.permissions import load_config
from macos_personal_mcp.process import NativeError
from macos_personal_mcp.sending import native_executor
from macos_personal_mcp.server import serve
from macos_personal_mcp.service import Service


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["serve", "doctor", "schemas", "index", "policy"])
    parser.add_argument(
        "--config",
        type=Path,
        help="Absolute owner-controlled approval TOML; default is application-data permissions.toml",
    )
    parser.add_argument(
        "--scope-file", type=Path, help="JSON MailScope for explicit local index maintenance"
    )
    parser.add_argument(
        "--max-messages",
        type=int,
        default=20,
        help="At most 1-200 source reads per resumable index call",
    )
    parser.add_argument(
        "--rebuild-index",
        action="store_true",
        help="Reset only the selected owned scope once; subsequent calls resume without this flag",
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--read-only", action="store_true")
    modes.add_argument(
        "--enable-writes",
        action="store_true",
        help="Expose blocked write schemas; does not authorize execution",
    )
    parser.add_argument(
        "--enable-mail-send",
        action="store_true",
        help="Enable native Mail sending; local startup policy chooses native or host approval",
    )
    parser.add_argument(
        "--enable-calendar-open",
        action="store_true",
        help="Enable the visible native show command for exact nonrecurring events; never creates or invites",
    )
    parser.add_argument(
        "--enable-calendar-create",
        action="store_true",
        help="Enable native Calendar creation; local startup policy chooses native or host approval",
    )
    parser.add_argument(
        "--enable-legacy-mail-search",
        action="store_true",
        help="Expose compatibility-only mail_search_legacy; requires explicit scoped FTS5 cache maintenance",
    )
    parser.add_argument(
        "--contacts-backend",
        choices=["framework", "contacts-app"],
        default="framework",
        help="Owner-selected Contacts route: direct unified API (default) or Contacts.app Apple Events; never an automatic fallback",
    )
    args = parser.parse_args()
    contacts_backend: ContactsBackend = (
        "contacts-app" if args.contacts_backend == "contacts-app" else "framework"
    )
    if args.read_only and (
        args.enable_mail_send or args.enable_calendar_create or args.enable_calendar_open
    ):
        parser.error("--read-only cannot be combined with a native write executor")
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ.pop("CONTROL_PLANE_API_KEY", None)
    try:
        config = load_config(args.config)
        bridge = NativeBridge(contacts_backend)
        service = Service(
            read_only=not (
                args.enable_writes
                or args.enable_mail_send
                or args.enable_calendar_create
                or args.enable_calendar_open
            ),
            enable_legacy_mail_search=args.enable_legacy_mail_search,
            bridge=bridge,
            mail_executor=native_executor(config.config.approval.mode_for("mail_send"))
            if args.enable_mail_send
            else None,
            calendar_executor=native_calendar_executor(
                bridge, config.config.approval.mode_for("calendar_create_event")
            )
            if args.enable_calendar_create
            else None,
            calendar_opener=NativeCalendarOpener(bridge) if args.enable_calendar_open else None,
            approval_config=config,
            contacts_backend=contacts_backend,
        )
    except (NativeError, OSError, ValueError) as error:
        print(
            Failure(
                code="permission_config",
                message=error.detail
                if isinstance(error, NativeError)
                else "Local approval configuration failed; no server started",
            ).model_dump_json(),
            file=sys.stderr,
        )
        raise SystemExit(2) from None
    match args.command:
        case "policy":
            print(service.approval_report().model_dump_json(indent=2))
        case "index":
            if args.scope_file is None:
                parser.error(
                    "index requires --scope-file with an explicit account/folder/date scope"
                )
            try:
                request = IndexRequest(
                    scope=MailScope.model_validate_json(args.scope_file.read_bytes()),
                    max_messages=args.max_messages,
                    rebuild=args.rebuild_index,
                )
                print(
                    asyncio.run(
                        service.body_index.refresh(request, service.bridge)
                    ).model_dump_json(indent=2)
                )
            except (NativeError, OSError, ValidationError, ValueError) as error:
                print(
                    Failure(
                        code=error.code if isinstance(error, NativeError) else "index_input",
                        message="Index maintenance failed; no source mutation or complete-coverage claim",
                    ).model_dump_json()
                )
                raise SystemExit(1) from None
        case "serve":
            asyncio.run(serve(service))
        case "doctor":
            print(asyncio.run(service.doctor()).model_dump_json(indent=2))
        case "schemas":
            for tool in service.tools():
                print(tool.model_dump_json(by_alias=True))
        case _:
            parser.error("Unknown command")


if __name__ == "__main__":
    main()
