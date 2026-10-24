import asyncio
import os
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from time import monotonic

import pytest

from macos_personal_mcp.process import NativeError, run_child


async def test_drains_both_pipes_and_feeds_large_stdin() -> None:
    payload = b"x" * 500_000
    result = await run_child(
        [
            sys.executable,
            "-c",
            (
                "import sys; sys.stderr.buffer.write(b'e'*500000); sys.stderr.flush(); "
                "sys.stdout.buffer.write(sys.stdin.buffer.read())"
            ),
        ],
        payload,
    )
    assert result == payload


async def test_timeout_during_stdin_and_reaps_child(monkeypatch: pytest.MonkeyPatch) -> None:
    # Create the real child first: this test isolates a blocked pipe from process
    # startup scheduling. The creation deadline has its own independent test.
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import time; time.sleep(20)",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )

    async def existing(*args: str, **kwargs: object) -> asyncio.subprocess.Process:
        return child

    monkeypatch.setattr(asyncio, "create_subprocess_exec", existing)
    started = monotonic()
    try:
        with pytest.raises(NativeError) as error:
            await run_child([sys.executable], b"x" * 4_000_000, timeout=0.3)
        assert error.value.code == "deadline"
        assert monotonic() - started < 3
        assert child.returncode is not None
        with pytest.raises(ProcessLookupError):
            os.kill(child.pid, 0)
    finally:
        if child.returncode is None:
            child.kill()
            await child.communicate()


async def test_cancellation_reaps_child(tmp_path: Path) -> None:
    pid_file = tmp_path / "pid"
    task = asyncio.create_task(
        run_child(
            [
                sys.executable,
                "-c",
                (
                    "import os,sys,time; from pathlib import Path; "
                    "Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(20)"
                ),
                str(pid_file),
            ]
        )
    )
    for _ in range(100):
        if pid_file.exists():
            break
        await asyncio.sleep(0.01)
    assert pid_file.exists()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)


async def test_oversize_and_nonzero_are_errors_not_empty_success() -> None:
    with pytest.raises(NativeError):
        await run_child([sys.executable, "-c", "print('x'*10000)"], max_bytes=100)
    with pytest.raises(NativeError) as error:
        await run_child(
            [sys.executable, "-c", "import sys; sys.stderr.write('private body'); sys.exit(1)"]
        )
    assert "private body" not in error.value.detail


async def test_deadline_covers_child_creation(monkeypatch: pytest.MonkeyPatch) -> None:
    original = asyncio.create_subprocess_exec

    async def delayed(*args: str, **kwargs: object) -> asyncio.subprocess.Process:
        await asyncio.sleep(10)
        raise AssertionError("A creation cancelled before spawn must never reach the OS")

    # The replacement deliberately never spawns; cancellation must finish within the deadline.
    delayed_spawn: Callable[..., Awaitable[asyncio.subprocess.Process]] = delayed
    monkeypatch.setattr(asyncio, "create_subprocess_exec", delayed_spawn)
    started = monotonic()
    with pytest.raises(NativeError) as error:
        await run_child([sys.executable, "-c", "pass"], timeout=0.1)
    assert error.value.code == "deadline" and monotonic() - started < 1
    monkeypatch.setattr(asyncio, "create_subprocess_exec", original)
