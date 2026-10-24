"""Independent native human review. No tool accepts an approval value or token."""

import json
import sys

from macos_personal_mcp.models import Model
from macos_personal_mcp.permissions import ApprovalMode
from macos_personal_mcp.process import NativeError, run_child
from macos_personal_mcp.safety import EventPreview, MailPreview, WritePreview


class Decision(Model):
    digest: str
    allow: bool


def review_text(preview: WritePreview) -> str:
    if isinstance(preview, EventPreview):
        from zoneinfo import ZoneInfo

        event, calendar = preview.payload, preview.calendar
        zone = ZoneInfo(event.timezone)
        start, end = event.instants()
        dates = (
            f"All-day dates: {event.all_day_start} through {event.all_day_end_exclusive} (exclusive end)\n"
            if event.all_day_start is not None
            else f"Start: {start.astimezone(zone).isoformat()}\nEnd: {end.astimezone(zone).isoformat()}\n"
        )
        return (
            f"Calendar: {calendar.name}\nSource/account: {calendar.source_name or '(unavailable)'}\n"
            f"Exact calendar ID: {calendar.id}\nTitle: {event.title}\n"
            f"{dates}"
            f"Timezone: {event.timezone}\nAttendees: none\nLocation: {event.location}\nURL: {event.url}\n"
            f"Notes:\n{event.notes}\n\nThis calendar may synchronize or be shared.\n"
            f"Operation: {event.operation_id}\nPayload SHA-256: {preview.digest}"
        )
    payload = preview.payload
    attachments = (
        "\n".join(
            f"{item.path}\n  {item.bytes} bytes; SHA-256 {item.sha256}"
            for item in preview.attachment_identities
        )
        or "(none)"
    )
    return (
        f"From: {payload.sender}\nTo: {', '.join(payload.to)}\n"
        f"CC: {', '.join(payload.cc) or '(none)'}\nBCC: {', '.join(payload.bcc) or '(none)'}\n"
        f"Subject: {payload.subject}\n\nAttachments:\n{attachments}\n\n"
        f"Message body ({len(payload.body)} characters):\n{payload.body}\n\n"
        f"End of message body.\nOperation: {payload.operation_id}\nPayload SHA-256: {preview.digest}"
    )


class NativeReviewer:
    def __init__(self, *, denial_test: bool = False) -> None:
        self.denial_test = denial_test

    async def approve(self, preview: WritePreview) -> bool:
        if self.denial_test:
            raise NativeError(
                "approval_unavailable", "An inert diagnostic cannot authorize a write"
            )
        return (await self.review(preview)).allow

    async def review(self, preview: WritePreview) -> Decision:
        raw = await run_child(
            [sys.executable, "-m", "macos_personal_mcp.approval_dialog"]
            + (["--denial-test"] if self.denial_test else [])
            + (["--calendar-event"] if isinstance(preview, EventPreview) else []),
            preview.model_dump_json().encode(),
            timeout=180,
        )
        decision = Decision.model_validate_json(raw)
        if decision.digest != preview.digest:
            raise NativeError("approval_mismatch", "Approval is not bound to this exact payload")
        return decision


class HostReviewer:
    """Explicit owner delegation; proceeding is not evidence of human consent."""

    async def approve(self, preview: WritePreview) -> bool:
        return True


def reviewer_for(mode: ApprovalMode) -> NativeReviewer | HostReviewer:
    return {"native": NativeReviewer, "host": HostReviewer}[mode]()


def approval_check() -> None:
    """Local diagnostic only: show a preview, print the decision, never dispatch."""
    import asyncio
    from pathlib import Path

    preview = MailPreview.model_validate_json(Path(sys.argv[1]).read_bytes())
    allowed = asyncio.run(NativeReviewer(denial_test=True).review(preview)).allow
    print(json.dumps({"approved": allowed, "external_effects_dispatched": False}))


if __name__ == "__main__":
    approval_check()
