"""Connection-owned reader child. Framed bounded I/O; stdout is responses only."""

import sys
import time

from pydantic import Field, ValidationError

from macos_personal_mcp.mail_native.contracts import NativeSearch
from macos_personal_mcp.mail_native.engine import Engine
from macos_personal_mcp.models import Failure, Model
from macos_personal_mcp.process import NativeError


class Work(Model):
    request: NativeSearch
    deadline: float = Field(gt=0)


def main() -> None:
    engine = Engine()
    while True:
        raw = sys.stdin.buffer.readline(65537)
        if not raw:
            return
        if len(raw) > 65536 or not raw.endswith(b"\n"):
            return
        try:
            work = Work.model_validate_json(raw)
            if work.deadline > time.monotonic() + 121:
                raise NativeError("invalid_input", "Worker deadline exceeds supported duration")
            output = engine.search(work.request, work.deadline).model_dump_json()
        except NativeError as error:
            output = Failure(code=error.code, message=error.detail).model_dump_json()
        except OSError, ValueError, ValidationError:
            output = Failure(
                code="native_unavailable",
                message="Native Mail storage unavailable or unsupported; no complete search result",
            ).model_dump_json()
        except Exception:
            # Prevent native/library diagnostics containing payloads from reaching
            # stdout/stderr. Parent treats a child exit as failure and restarts.
            return
        sys.stdout.write(output + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
