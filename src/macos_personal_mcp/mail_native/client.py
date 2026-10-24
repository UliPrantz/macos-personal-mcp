"""Lazy supervised, serialized read worker tied to this MCP connection."""

import asyncio
import os
import signal
import sys
import time
from contextlib import suppress

from pydantic import ValidationError

from macos_personal_mcp.mail_native.contracts import NativeSearch, NativeSearchResult
from macos_personal_mcp.mail_native.worker import Work
from macos_personal_mcp.models import Failure
from macos_personal_mcp.process import NativeError


class NativeSearchClient:
    def __init__(self, command: tuple[str, ...] | None = None, timeout: float = 120) -> None:
        self.command = command or (sys.executable, "-m", "macos_personal_mcp.mail_native.worker")
        self.timeout = min(timeout, 120)
        self.process: asyncio.subprocess.Process | None = None
        self.lock = asyncio.Lock()

    async def close(self) -> None:
        process, self.process = self.process, None
        if process is None:
            return
        if process.returncode is None:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
        await process.communicate()

    async def search(self, request: NativeSearch) -> NativeSearchResult:
        deadline = time.monotonic() + self.timeout
        success = False
        owned = False
        creation: asyncio.Task[asyncio.subprocess.Process] | None = None
        try:
            async with asyncio.timeout_at(deadline):
                await self.lock.acquire()
                owned = True
                if self.process is None or self.process.returncode is not None:
                    creation = asyncio.create_task(
                        asyncio.create_subprocess_exec(
                            *self.command,
                            stdin=asyncio.subprocess.PIPE,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.DEVNULL,
                            start_new_session=True,
                            limit=2_000_000,
                        )
                    )
                    self.process = await creation
                process = self.process
                if process.stdin is None or process.stdout is None:
                    raise NativeError("native_failure", "Native reader pipes unavailable")
                process.stdin.write(
                    Work(request=request, deadline=deadline).model_dump_json().encode() + b"\n"
                )
                await process.stdin.drain()
                raw = await process.stdout.readline()
                if not raw or len(raw) > 2_000_000 or not raw.endswith(b"\n"):
                    raise NativeError(
                        "native_failure", "Native reader exited or exceeded its frame bound"
                    )
                try:
                    failure = Failure.model_validate_json(raw)
                except ValidationError:
                    result = NativeSearchResult.model_validate_json(raw)
                else:
                    success = True
                    raise NativeError(failure.code, failure.message)
                success = True
                return result
        except TimeoutError as error:
            raise NativeError(
                "deadline", "Native search exceeded its absolute 120-second deadline"
            ) from error
        except (OSError, ValueError) as error:
            raise NativeError(
                "native_failure", "Native reader failed; no complete search result"
            ) from error
        finally:
            if owned:
                try:
                    if not success:
                        if (
                            creation is not None
                            and not creation.cancelled()
                            and self.process is None
                        ):
                            with suppress(OSError, asyncio.CancelledError):
                                self.process = await creation
                        cleanup = asyncio.create_task(self.close())
                        try:
                            await asyncio.shield(cleanup)
                        except asyncio.CancelledError:
                            await cleanup
                            raise
                finally:
                    self.lock.release()
