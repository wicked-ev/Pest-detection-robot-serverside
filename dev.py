"""Start the server, wait until it is ready, then start the dashboard. Ctrl+C stops both.

Usage (from this folder, with any Python 3.9+):
    python dev.py
    python dev.py --port 8000 --dashboard-port 5173

The server runs from server/.venv (set it up first, see server/README.md) and listens on
all network interfaces, so a robot on the Wi-Fi can connect. The dashboard is pointed at
this local server, whatever dashboard/.env.local says.
"""

from __future__ import annotations

import argparse
import http.client
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SERVER_DIR = ROOT / "server"
DASHBOARD_DIR = ROOT / "dashboard"
WINDOWS = os.name == "nt"

COLORS = {"server": "\033[36m", "dashboard": "\033[35m", "dev": "\033[33m"}
RESET = "\033[0m"


USE_COLOR = sys.stdout.isatty() and os.getenv("NO_COLOR") is None
if USE_COLOR and WINDOWS:
    os.system("")  # turns on colour support in the Windows console


def say(source: str, line: str) -> None:
    if USE_COLOR:
        print(f"{COLORS.get(source, '')}[{source}]{RESET} {line}", flush=True)
    else:
        print(f"[{source}] {line}", flush=True)


def server_python() -> Path:
    candidates = [SERVER_DIR / ".venv" / "Scripts" / "python.exe", SERVER_DIR / ".venv" / "bin" / "python"]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    sys.exit("server/.venv not found: set up the server first (see server/README.md)")


def port_in_use(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


# Set when the server reports that its shutdown (saving pending data) has finished.
SERVER_SHUTDOWN_DONE = threading.Event()


def relay(name: str, proc: subprocess.Popen) -> None:
    for line in proc.stdout:
        line = line.rstrip()
        if name == "server" and "Application shutdown complete" in line:
            SERVER_SHUTDOWN_DONE.set()
        say(name, line)


def start(name: str, cmd: list, cwd: Path, env: dict | None = None) -> subprocess.Popen:
    """Start a process in its own process group, so it can be stopped cleanly on its own."""
    kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if WINDOWS else {"start_new_session": True}
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        **kwargs,
    )
    threading.Thread(target=relay, args=(name, proc), daemon=True).start()
    return proc


def kill_tree(proc: subprocess.Popen) -> None:
    if WINDOWS:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    else:
        os.killpg(proc.pid, signal.SIGKILL)
    proc.wait(timeout=5)


def stop(name: str, proc: subprocess.Popen | None, graceful: bool = True, grace: float = 30.0) -> None:
    """Stop a process and its children.

    graceful: ask it to stop like Ctrl+C would (the server then saves pending data),
    and force it only after `grace` seconds. Otherwise close it right away.
    """
    if proc is None or proc.poll() is not None:
        return
    say("dev", f"stopping {name}...")
    if not graceful:
        kill_tree(proc)
        return
    try:
        if WINDOWS:
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(proc.pid, signal.SIGINT)
        deadline = time.monotonic() + grace
        told = False
        while proc.poll() is None:
            if name == "server" and SERVER_SHUTDOWN_DONE.wait(timeout=0):
                # Its data is saved; it should exit by itself any moment. Rarely (when stopped
                # while the model is still loading) it lingers, so close it after a short wait.
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    say("dev", "server saved its data but did not exit; closing it")
                    kill_tree(proc)
                return
            if time.monotonic() > deadline:
                raise subprocess.TimeoutExpired(proc.args, grace)
            if not told and time.monotonic() > deadline - grace + 3:
                say("dev", f"{name} is still finishing; waiting up to {grace:.0f}s")
                told = True
            time.sleep(0.1)
    except (subprocess.TimeoutExpired, OSError):
        say("dev", f"{name} did not stop within {grace:.0f}s; forcing it")
        kill_tree(proc)


def server_ready(port: int) -> bool:
    # Plain HTTP via http.client (no SSL setup involved).
    try:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        connection.request("GET", "/health")
        ok = connection.getresponse().status == 200
        connection.close()
        return ok
    except OSError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8000, help="server port (default 8000)")
    parser.add_argument("--dashboard-port", type=int, default=5173, help="dashboard port (default 5173)")
    parser.add_argument("--timeout", type=float, default=120.0, help="seconds to wait for the server")
    args = parser.parse_args()

    # Treat Ctrl+Break / termination like Ctrl+C, so the cleanup below always runs
    # (otherwise Python exits at once and leaves the server and dashboard running).
    def interrupt(signum, frame):
        raise KeyboardInterrupt

    for name in ("SIGBREAK", "SIGTERM"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), interrupt)

    for port, what in ((args.port, "server"), (args.dashboard_port, "dashboard")):
        if port_in_use(port):
            say("dev", f"port {port} is already in use: is the {what} already running? (or pick another port)")
            return 1

    npm = shutil.which("npm")
    if npm is None:
        say("dev", "npm not found: install Node.js 18+ for the dashboard")
        return 1

    server = dashboard = None
    try:
        say("dev", f"starting server on port {args.port}")
        server = start(
            "server",
            [
                str(server_python()), "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", str(args.port),
                # Without a limit, shutdown can wait forever for a connection that never closes
                # (seen with the dashboard's proxy), and the app's own shutdown, which saves
                # pending data, would never run.
                "--timeout-graceful-shutdown", "5",
            ],
            SERVER_DIR,
        )

        deadline = time.monotonic() + args.timeout
        while not server_ready(args.port):
            if server.poll() is not None:
                say("dev", f"server exited (code {server.returncode}) before it was ready; see its output above")
                return 1
            if time.monotonic() > deadline:
                say("dev", f"server not ready after {args.timeout:.0f}s")
                return 1
            time.sleep(0.5)
        say("dev", f"server ready: http://127.0.0.1:{args.port}/health")

        if not (DASHBOARD_DIR / "node_modules").exists():
            say("dev", "installing dashboard packages (first run)...")
            subprocess.run([npm, "install"], cwd=DASHBOARD_DIR, check=True)

        env = dict(os.environ, VITE_SERVER_URL=f"http://127.0.0.1:{args.port}")
        dashboard = start(
            "dashboard",
            [npm, "run", "dev", "--", "--port", str(args.dashboard_port), "--strictPort"],
            DASHBOARD_DIR,
            env,
        )
        say("dev", f"dashboard: http://localhost:{args.dashboard_port}   (Ctrl+C stops both)")

        while True:
            for name, proc in (("server", server), ("dashboard", dashboard)):
                if proc.poll() is not None:
                    say("dev", f"{name} exited (code {proc.returncode}); stopping the rest")
                    return 1
            time.sleep(0.5)
    except KeyboardInterrupt:
        return 0
    finally:
        # Server first, while the dashboard can still close its proxy connection to it
        # normally; a force-closed dashboard can leave that connection half-open on
        # Windows, and the server then waits for it forever.
        stop("server", server)
        stop("dashboard", dashboard, graceful=False)
        say("dev", "stopped")


if __name__ == "__main__":
    sys.exit(main())
