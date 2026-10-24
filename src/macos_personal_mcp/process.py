"""Subprocess deadlines include creation, stdin, draining, cancellation and reaping."""

import asyncio
import math
import os
import re
import signal
from contextlib import suppress
from dataclasses import dataclass


@dataclass
class NativeError(Exception):
    code: str
    detail: str


async def run_child(
    argv: list[str], payload: bytes = b"", *, timeout: float = 15.0, max_bytes: int = 8_000_000
) -> bytes:
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Timeout must be finite and positive")
    process: asyncio.subprocess.Process | None = None
    finished = False
    # CPython's Unix subprocess creation closes/reaps its transport on cancellation.
    # Assignment has no intervening await after creation completes.
    creation = asyncio.create_task(
        asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
    )

    async def reap() -> None:
        child = process
        if child is None:
            if creation.cancelled():
                return
            try:
                child = await creation
            except OSError:
                return
        if child.returncode is None:
            with suppress(ProcessLookupError):
                os.killpg(child.pid, signal.SIGKILL)
        # Drain after killing, including when the bounded readers were cancelled.
        # Process.wait alone can deadlock while a full pipe pauses its transport.
        await child.communicate()

    async def drain(reader: asyncio.StreamReader | None) -> bytes:
        if reader is None:
            raise NativeError("bridge_failure", "Missing subprocess pipe")
        chunks: list[bytes] = []
        size = 0
        while block := await reader.read(65536):
            size += len(block)
            if size > max_bytes:
                raise NativeError(
                    "output_limit", "Native response exceeded the bounded output size"
                )
            chunks.append(block)
        return b"".join(chunks)

    async def feed(child: asyncio.subprocess.Process) -> None:
        if child.stdin is None:
            raise NativeError("bridge_failure", "Missing subprocess stdin")
        fed = False
        try:
            child.stdin.write(payload)
            await child.stdin.drain()
            fed = True
        except BrokenPipeError, ConnectionResetError:
            fed = True
        finally:
            if fed:
                child.stdin.close()
            else:
                child.stdin.transport.abort()
            # Do not await wait_closed here: cancellation during a blocked write
            # would otherwise wait for the still-live child before reaching reap().

    try:
        async with asyncio.timeout(timeout):
            child = await creation
            process = child
            async with asyncio.TaskGroup() as group:
                stdout = group.create_task(drain(child.stdout))
                stderr = group.create_task(drain(child.stderr))
                group.create_task(feed(child))
                group.create_task(child.wait())
            finished = True
            if child.returncode:
                # No raw native diagnostics: they can contain private message/recipient data.
                code = "permission_denied" if b"-1743" in stderr.result() else "native_failure"
                numbers = re.findall(rb"\((-?\d+)\)", stderr.result())
                native_code = numbers[-1].decode("ascii") if numbers else "unavailable"
                raise NativeError(
                    code,
                    "Native operation failed (code " + native_code + "); access is not established",
                )
            return stdout.result()
    except TimeoutError as error:
        raise NativeError(
            "deadline", "Native operation exceeded its deadline; no complete result"
        ) from error
    except ExceptionGroup as error:
        raise NativeError(
            "bridge_failure", "Native pipe processing failed; no complete result"
        ) from error
    finally:
        if not finished:
            cleanup = asyncio.create_task(reap())
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                await cleanup
                raise
