"""Complete decoded MIME body text; attachment contents are deliberately excluded."""

from email import policy
from email.errors import MissingHeaderBodySeparatorDefect
from email.message import EmailMessage, MIMEPart
from email.parser import BytesParser
from html.parser import HTMLParser
from typing import override

from macos_personal_mcp.process import NativeError


class HTMLText(HTMLParser):
    """Static visible-text heuristic, preserving link/table/block boundaries."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, bool]] = []
        self.text: list[str] = []

    def hidden(self) -> bool:
        return bool(self.stack and self.stack[-1][1])

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        style = (attributes.get("style") or "").casefold()
        hidden_style = False
        for declaration in style.split(";"):
            key, _, value = declaration.partition(":")
            if (key.strip(), value.replace("!important", "").strip()) in {
                ("display", "none"),
                ("visibility", "hidden"),
                ("visibility", "collapse"),
                ("mso-hide", "all"),
            }:
                hidden_style = True
        hidden = (
            self.hidden()
            or tag in {"head", "script", "style"}
            or "hidden" in attributes
            or hidden_style
        )
        if tag not in {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }:
            self.stack.append((tag, hidden))
        if not hidden and tag in {"br", "p", "div", "li", "tr", "h1", "h2", "a", "td", "th"}:
            self.text.append("\n")

    @override
    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break
        if not self.hidden() and tag in {"p", "div", "li", "tr", "a", "td", "th"}:
            self.text.append("\n")

    @override
    def handle_data(self, data: str) -> None:
        if not self.hidden():
            self.text.append(data)


def body_parts(
    part: MIMEPart[str, str], depth: int = 0, *, original_bytes: bool = False
) -> list[str]:
    if depth > 50:
        raise NativeError("mime_depth", "MIME nesting exceeds the explicit safety bound")
    if part.get_content_disposition() == "attachment" or part.get_filename() is not None:
        return []
    if part.get_content_type() in {
        "multipart/encrypted",
        "application/pkcs7-mime",
        "application/x-pkcs7-mime",
    }:
        raise NativeError("body_encrypted", "Encrypted MIME body is unavailable to the index")
    if part.get_content_maintype() == "message":
        return []  # Attached/embedded RFC messages are not this message's body.
    if part.get_content_maintype() in {"image", "audio", "video"}:
        return []  # Inline media resources are not body text.
    if part.is_multipart():
        parts: list[str] = []
        children = list(part.iter_parts())
        if original_bytes and part.get_content_type() == "multipart/alternative":
            selected_body = part.get_body(preferencelist=("html", "plain"))
            children = [selected_body] if selected_body is not None else []
        elif original_bytes and part.get_content_type() == "multipart/related":
            start = part.get_param("start")
            selected = [child for child in children if start and child.get("Content-ID") == start]
            if start and len(selected) != 1:
                raise NativeError(
                    "mime_invalid", "Declared related MIME root is unavailable or ambiguous"
                )
            children = selected if start else children[:1]
        for child in children:
            parts.extend(body_parts(child, depth + 1, original_bytes=original_bytes))
        return parts
    if part.get_content_type() == "text/calendar":
        return []
    if part.get_content_maintype() != "text":
        raise NativeError("body_format", "Unsupported inline body format; scope is incomplete")
    payload = part.get_payload(decode=True)
    if not isinstance(payload, bytes) or part.defects:
        raise NativeError("mime_invalid", "MIME transfer decoding is incomplete")
    raw = part.get_payload()
    declared_charset = part.get_content_charset()
    charset = declared_charset or ("utf-8" if original_bytes else "ascii")
    if (
        not original_bytes
        and isinstance(raw, str)
        and not raw.isascii()
        and charset.lower().replace("-", "") not in {"utf8", "ascii"}
    ):
        raise NativeError(
            "body_decode", "Native Unicode source cannot prove original non-UTF8 8-bit bytes"
        )
    try:
        text = payload.decode(charset, errors="strict")
    except (LookupError, UnicodeError) as error:
        raise NativeError("body_decode", "Body charset cannot be decoded completely") from error
    if part.get_content_type() == "text/html":
        parser = HTMLText()
        parser.feed(text)
        parser.close()
        text = "".join(parser.text)
    return [text]


def decoded_bytes(
    source: bytes,
    expected_message_id: str | None = None,
    *,
    original_bytes: bool = True,
    allow_separator_defect: bool = False,
) -> str:
    message = BytesParser(_class=EmailMessage, policy=policy.default).parsebytes(source)
    if message.defects and not (
        allow_separator_defect
        and all(isinstance(defect, MissingHeaderBodySeparatorDefect) for defect in message.defects)
    ):
        raise NativeError("mime_invalid", "Raw MIME source has structural defects")
    if expected_message_id is not None and str(message.get("Message-ID", "")).strip().strip(
        "<>"
    ) != expected_message_id.strip("<>"):
        raise NativeError("message_identity", "MIME Message-ID differs from the selected identity")
    if allow_separator_defect:
        message.defects = [
            defect
            for defect in message.defects
            if not isinstance(defect, MissingHeaderBodySeparatorDefect)
        ]
    return "\n\n".join(body_parts(message, original_bytes=original_bytes))


def decoded_body(source: str, expected_message_id: str | None = None) -> str:
    return decoded_bytes(source.encode("utf-8"), expected_message_id, original_bytes=False)
