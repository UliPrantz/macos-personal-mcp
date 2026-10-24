"""A disposable AppKit dialog. Only a human button click produces approval."""

import sys

import AppKit as AK

from macos_personal_mcp.approval import Decision, review_text
from macos_personal_mcp.safety import EventPreview, MailPreview


def main() -> None:
    raw = sys.stdin.buffer.read(4_000_001)
    if len(raw) > 4_000_000:
        raise ValueError("Approval input exceeds bound")
    calendar_event = "--calendar-event" in sys.argv[1:]
    preview = (
        EventPreview.model_validate_json(raw)
        if calendar_event
        else MailPreview.model_validate_json(raw)
    )
    app = AK.NSApplication.sharedApplication()
    app.setActivationPolicy_(AK.NSApplicationActivationPolicyAccessory)
    alert = AK.NSAlert.alloc().init()
    denial_test = "--denial-test" in sys.argv[1:]
    if denial_test:
        heading, button = "Cancellation test — please click Cancel", "Approve test (does nothing)"
        note = "This is an inert approval diagnostic. Please click Cancel to verify denial. "
    elif calendar_event:
        heading, button = "Create this calendar event?", "Create event"
        note = (
            "macOS Personal MCP will create the exact event below. No attendees will be invited. "
        )
    else:
        heading, button = "Send this email?", "Send this email"
        note = "macOS Personal MCP will send exactly the message below through Apple Mail. Review all recipients, content and attachments. "
    alert.setMessageText_(heading)
    alert.setInformativeText_(
        note + "Cancel performs no write. This request expires after three minutes."
    )
    cancel = alert.addButtonWithTitle_("Cancel")
    cancel.setKeyEquivalent_("\r")
    send = alert.addButtonWithTitle_(button)
    send.setKeyEquivalent_("")
    frame = ((0.0, 0.0), (640.0, 360.0))
    scroll = AK.NSScrollView.alloc().initWithFrame_(frame)
    scroll.setHasVerticalScroller_(True)
    text = AK.NSTextView.alloc().initWithFrame_(frame)
    text.setEditable_(False)
    text.setSelectable_(True)
    text.setRichText_(False)
    text.setVerticallyResizable_(True)
    text.setHorizontallyResizable_(False)
    text.setMinSize_((640.0, 360.0))
    text.setMaxSize_((640.0, 10_000_000.0))
    container = text.textContainer()
    if container is None:
        raise RuntimeError("Missing approval text container")
    container.setContainerSize_((640.0, 10_000_000.0))
    container.setWidthTracksTextView_(True)
    text.setString_(review_text(preview))
    scroll.setDocumentView_(text)
    alert.setAccessoryView_(scroll)
    app.activateIgnoringOtherApps_(True)
    choice = alert.runModal()
    print(
        Decision(
            digest=preview.digest, allow=choice == AK.NSAlertSecondButtonReturn
        ).model_dump_json()
    )


if __name__ == "__main__":
    main()
