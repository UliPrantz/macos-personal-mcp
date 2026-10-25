"""Only this adapter crosses the fixed scripting/JSON boundary."""

import sys
from importlib.resources import files
from typing import Protocol

from pydantic import ValidationError

from macos_personal_mcp.models import Failure, Model, NativeReply
from macos_personal_mcp.process import NativeError, run_child


class Bridge(Protocol):
    async def call[T: Model](self, operation: str, request: Model, output: type[T]) -> T: ...


class NativeBridge:
    async def call[T: Model](self, operation: str, request: Model, output: type[T]) -> T:
        if sys.platform != "darwin":
            raise NativeError("platform", "Native operations require macOS")
        if operation in {"permissions", "request_permissions"} or operation.startswith(
            ("calendar_", "contacts_")
        ):
            raw = await run_child(
                [
                    sys.executable,
                    "-m",
                    "macos_personal_mcp.native_worker",
                    operation,
                ],
                request.model_dump_json().encode(),
                timeout=105 if operation == "request_permissions" else 15,
            )
            reply = NativeReply.model_validate_json(raw)
            if reply.failure is not None:
                raise NativeError(reply.failure.code, reply.failure.message)
            if reply.result_json is None:
                raise NativeError("invalid_native_response", "Native worker omitted its result")
            return output.model_validate_json(reply.result_json)
        source = files("macos_personal_mcp").joinpath("bridge.js").read_bytes()
        raw = await run_child(
            ["/usr/bin/osascript", "-l", "JavaScript", "-", operation, request.model_dump_json()],
            source,
            max_bytes=192_000_000 if operation == "mail_get_source" else 8_000_000,
        )
        try:
            failure = Failure.model_validate_json(raw)
        except ValidationError:
            pass
        else:
            raise NativeError(failure.code, failure.message)
        try:
            return output.model_validate_json(raw)
        except ValueError as error:
            raise NativeError(
                "invalid_native_response", "Native response failed the typed contract"
            ) from error
