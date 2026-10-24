"""run_in_daemon_thread: results, errors, and not blocking process exit."""

import asyncio
import subprocess
import sys
import time

import pytest

from core.background import run_in_daemon_thread


def test_returns_the_result():
    assert asyncio.run(run_in_daemon_thread(lambda a, b: a + b, 2, 3)) == 5


def test_raises_the_error():
    def fail():
        raise ValueError("bad model")

    with pytest.raises(ValueError, match="bad model"):
        asyncio.run(run_in_daemon_thread(fail))


def test_a_cancelled_wait_does_not_break_when_the_job_finishes():
    async def scenario():
        task = asyncio.create_task(run_in_daemon_thread(time.sleep, 0.2))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0.3)  # the job finishes after the cancel; nothing must blow up

    asyncio.run(scenario())


def test_process_exits_without_waiting_for_a_long_job():
    """The server hang: exiting while a slow job (model load) still runs."""
    code = (
        "import asyncio, time\n"
        "from core.background import run_in_daemon_thread\n"
        "async def main():\n"
        "    task = asyncio.create_task(run_in_daemon_thread(time.sleep, 60))\n"
        "    await asyncio.sleep(0.2)\n"
        "    task.cancel()\n"
        "asyncio.run(main())\n"
    )
    started = time.monotonic()
    subprocess.run([sys.executable, "-c", code], check=True, timeout=30, cwd=".")
    assert time.monotonic() - started < 10
