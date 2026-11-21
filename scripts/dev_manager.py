"""Keep one authenticated local supervisor per MealMind development service."""

import argparse
import errno
import fcntl
import hmac
import json
import os
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

STATE = Path(".dev-local")
START_TIMEOUT = 25
STOP_TIMEOUT = 9


@dataclass(frozen=True)
class Service:
    directory: str
    port: int
    command: tuple[str, ...]
    health_path: str = "/"

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}"


SERVICES = {
    "backend": Service("backend", 8000, (
        ".venv/bin/python", "-m", "uvicorn", "app.main:app", "--reload", "--host",
        "127.0.0.1", "--port", "8000", "--no-proxy-headers", "--no-access-log",
    ), "/api/v1/health"),
    "frontend": Service("frontend", 5173, (
        "npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173", "--strictPort",
    )),
}


class DevError(Exception):
    pass


@dataclass(frozen=True)
class Identity:
    pid: int
    token: str

    def socket_path(self, name):
        # Relative paths also work in checkouts whose absolute paths exceed Darwin's socket limit.
        return str(STATE / f"{name}-{self.token[:12]}.sock")


def metadata(name):
    return STATE / f"{name}.json"


def log_path(name):
    return STATE / f"{name}.log"


def identity_of(name):
    try:
        record = json.loads(metadata(name).read_text())
        pid, token = record["pid"], record["token"]
        if type(pid) is int and pid > 1 and isinstance(token, str) and re.fullmatch(r"[0-9a-f]{48}", token):
            return Identity(pid, token)
    except (FileNotFoundError, KeyError, TypeError, ValueError):
        pass
    return None


def rpc(name, identity, command):
    if identity is None:
        return False
    try:
        if os.getpgid(identity.pid) != identity.pid:
            return False
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(0.5)
            connection.connect(identity.socket_path(name))
            connection.sendall(f"{identity.token} {command}\n".encode("ascii"))
            with connection.makefile("rb") as response:
                return response.readline(128) == f"{identity.token} {identity.pid}\n".encode("ascii")
    except OSError:
        return False


def group_members(pgid):
    result = subprocess.run(
        ("/bin/ps", "-ax", "-o", "pid=,pgid=,stat="), capture_output=True, text=True, check=False,
        start_new_session=True,
    )
    if result.returncode:
        raise DevError("Could not inspect process groups with macOS ps.")
    members = set()
    for line in result.stdout.splitlines():
        pid, group, status = line.split()
        if group == str(pgid) and not status.startswith("Z"):
            members.add(int(pid))
    return members


def listeners(port):
    result = subprocess.run(
        ("/usr/sbin/lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-Fpc"),
        capture_output=True, text=True, check=False,
    )
    if result.returncode not in (0, 1) or result.stderr.strip():
        raise DevError(f"Could not inspect TCP port {port} with macOS lsof.")
    owners = {}
    pid = None
    for line in result.stdout.splitlines():
        if line.startswith("p") and line[1:].isdigit():
            pid = int(line[1:])
            owners[pid] = "unknown"
        elif pid is not None and line.startswith("c"):
            owners[pid] = re.sub(r"[^a-zA-Z0-9._+-]", "?", line[1:])[:40] or "unknown"

    # lsof may hide other users' processes, so verify apparent availability with the kernel.
    if not owners:
        for family, address in ((socket.AF_INET, "0.0.0.0"), (socket.AF_INET6, "::")):
            try:
                with socket.socket(family, socket.SOCK_STREAM) as probe:
                    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    if family == socket.AF_INET6:
                        probe.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
                    probe.bind((address, port))
            except OSError as exc:
                if exc.errno == errno.EADDRINUSE:
                    return {None: "unidentified listener"}
                if family == socket.AF_INET6 and exc.errno in (errno.EAFNOSUPPORT, errno.EPROTONOSUPPORT):
                    continue
                raise DevError(f"Could not check TCP port {port} (errno {exc.errno}).") from None
    return owners


def owned_by(pid, identity):
    if pid is None or identity is None:
        return False
    try:
        return os.getpgid(pid) == identity.pid
    except ProcessLookupError:
        return False


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


HTTP = build_opener(ProxyHandler({}), NoRedirect())


def responds(service):
    try:
        with HTTP.open(service.url + service.health_path, timeout=0.5) as response:
            return response.status == 200
    except (HTTPError, URLError, OSError):
        return False


def describe(owners):
    return ", ".join(f"PID {pid} ({name})" if pid is not None else name for pid, name in owners.items())


def status():
    for name, service in SERVICES.items():
        identity = identity_of(name)
        managed = rpc(name, identity, "status")
        owners = listeners(service.port)
        outside = {pid: label for pid, label in owners.items() if not managed or not owned_by(pid, identity)}
        if outside:
            state = f"unmanaged port occupant: {describe(outside)}"
        elif managed and owners:
            state = "running (managed)" if responds(service) else "listening, HTTP unavailable (managed)"
        elif managed:
            state = "supervisor running, service not listening (managed)"
        else:
            state = "stopped"
            if identity and group_members(identity.pid):
                state += "; recorded process group is unverified"
        print(f"{name.capitalize()}: {state} | {service.url} | log: {log_path(name)}")


def stop(names):
    waiting = {}
    success = True
    for name in names:
        identity = identity_of(name)
        if rpc(name, identity, "stop"):
            waiting[name] = identity
        elif identity and group_members(identity.pid):
            print(f"{name.capitalize()}: recorded group is unverified; left untouched.")
            success = False
        else:
            if identity is not None:
                Path(identity.socket_path(name)).unlink(missing_ok=True)
            metadata(name).unlink(missing_ok=True)
            print(f"{name.capitalize()}: no managed service to stop.")

    deadline = time.monotonic() + STOP_TIMEOUT
    while waiting:
        for name, identity in list(waiting.items()):
            if not group_members(identity.pid):
                Path(identity.socket_path(name)).unlink(missing_ok=True)
                metadata(name).unlink(missing_ok=True)
                print(f"{name.capitalize()}: stopped.")
                del waiting[name]
        if waiting and time.monotonic() >= deadline:
            for name in waiting:
                print(f"{name.capitalize()}: stop could not be verified; see {log_path(name)}.")
            return False
        if waiting:
            time.sleep(0.15)
    return success


def preflight():
    pending = {}
    problems = []
    for name, service in SERVICES.items():
        identity = identity_of(name)
        managed = rpc(name, identity, "status")
        owners = listeners(service.port)
        conflicts = {pid: label for pid, label in owners.items() if not managed or not owned_by(pid, identity)}
        if conflicts:
            problems.append(
                f"{name.capitalize()} port {service.port} is occupied by {describe(conflicts)}. "
                "Close the owning application or stop its server from the original terminal, then retry."
            )
        elif managed:
            print(f"{name.capitalize()}: already managed.")
        elif identity and group_members(identity.pid):
            problems.append(f"{name.capitalize()}: recorded process group is unverified. Inspect it before retrying.")
        else:
            pending[name] = service
            if name == "backend" and not os.access(Path(service.directory) / service.command[0], os.X_OK):
                problems.append("Backend virtual environment is missing. Follow the setup instructions in README.md.")
            if name == "frontend" and (not shutil.which("npm") or not Path("frontend/node_modules/.bin/vite").exists()):
                problems.append("npm or Vite is missing. Follow the frontend setup instructions in README.md.")
    if problems:
        raise DevError("\n".join(problems))
    return pending


def start(lock_fd):
    pending = preflight()
    children = {}
    try:
        for name in pending:
            with open(log_path(name), "a") as log:
                children[name] = subprocess.Popen(
                    (sys.executable, __file__, "--supervise", name, str(lock_fd)),
                    cwd=Path.cwd(), stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.DEVNULL,
                    start_new_session=True, pass_fds=(lock_fd,),
                )

        deadline = time.monotonic() + START_TIMEOUT
        while True:
            ready = set()
            for name, service in SERVICES.items():
                child = children.get(name)
                if child is not None and child.poll() is not None:
                    raise DevError(f"{name.capitalize()} exited during startup. See {log_path(name)}.")
                identity = identity_of(name)
                if (
                    identity is not None and (child is None or identity.pid == child.pid)
                    and rpc(name, identity, "status")
                ):
                    owners = listeners(service.port)
                    if owners and all(owned_by(pid, identity) for pid in owners) and responds(service):
                        ready.add(name)
            if len(ready) == len(SERVICES):
                break
            if time.monotonic() >= deadline:
                names = ", ".join(str(log_path(name)) for name in SERVICES if name not in ready)
                raise DevError(f"Startup did not reach HTTP readiness. See {names}.")
            time.sleep(0.15)
    except (DevError, OSError, KeyboardInterrupt):
        # Direct children are still ours to signal even before they publish a control socket.
        for child in children.values():
            child.terminate()
        for name, child in children.items():
            try:
                child.wait(timeout=STOP_TIMEOUT)
            except subprocess.TimeoutExpired:
                print(f"{name.capitalize()}: cleanup did not finish; see {log_path(name)}.", file=sys.stderr)
        raise
    for name, service in SERVICES.items():
        print(f"{name.capitalize()}: running (managed) | {service.url} | log: {log_path(name)}")


# Keep a fixed vocabulary in logs. Raw subprocess output can contain environment
# values, provider errors, request bodies, or configuration and stack trace details.
LOG_EVENTS = (
    (("address already in use", "eaddrinuse", "is already in use"), "Required port is already in use."),
    (("application startup complete",), "FastAPI application startup complete."),
    (("reloading", "detected changes"), "Development reload requested."),
    (("ready in",), "Vite reported startup complete."),
    (("modulenotfounderror", "cannot find module", "cannot find package"), "A required dependency could not be imported."),
    (("validationerror", "settingserror", "error loading asgi"), "Application configuration or import failed."),
    (("permission denied", "operation not permitted", "eacces"), "A local operation was denied."),
    (("error", "traceback"), "Service reported an error; private details withheld."),
)


def filter_output(stream):
    reported = set()
    while chunk := stream.readline(16384):
        line = chunk.decode("utf-8", errors="replace").casefold()
        for needles, message in LOG_EVENTS:
            if any(needle in line for needle in needles):
                if message not in reported:
                    print(message, flush=True)
                    reported.add(message)
                break


def supervise(name, lock_fd):
    identity = Identity(os.getpid(), secrets.token_hex(24))
    service = SERVICES[name]
    stopping = threading.Event()

    def request_stop(_signal, _frame):
        stopping.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    path = identity.socket_path(name)
    if os.getpgrp() != identity.pid or os.getsid(0) != identity.pid:
        return 1

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(path)
            server.listen()
            server.settimeout(0.2)
            record = metadata(name).with_suffix(f".{identity.token}.tmp")
            record.write_text(json.dumps({"pid": identity.pid, "token": identity.token}))
            record.replace(metadata(name))
            os.close(lock_fd)

            print(f"Starting {name} on {service.url}.", flush=True)
            if stopping.is_set():
                return 0
            with subprocess.Popen(
                service.command, cwd=service.directory, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            ) as worker:
                output = threading.Thread(target=filter_output, args=(worker.stdout,), daemon=True)
                output.start()
                while not stopping.is_set() and worker.poll() is None:
                    try:
                        connection, _address = server.accept()
                        with connection:
                            connection.settimeout(0.25)
                            with connection.makefile("rb") as request:
                                line = request.readline(128)
                            token, separator, command = line.rstrip(b"\n").partition(b" ")
                            if separator and hmac.compare_digest(token, identity.token.encode("ascii")):
                                if command in (b"status", b"stop"):
                                    connection.sendall(f"{identity.token} {identity.pid}\n".encode("ascii"))
                                if command == b"stop":
                                    stopping.set()
                    except OSError:
                        continue

                if worker.poll() is not None:
                    print(f"Service exited with code {worker.returncode}.", flush=True)
                print("Sending SIGTERM to the managed process group.", flush=True)
                # The live supervisor owns and anchors this group throughout shutdown.
                os.killpg(identity.pid, signal.SIGTERM)
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    worker.poll()  # Reap the direct child while waiting for its descendants.
                    if not group_members(identity.pid) - {identity.pid}:
                        output.join(timeout=0.3)
                        return 0 if stopping.is_set() else 1
                    time.sleep(0.1)
                print("Grace period expired; terminating the remaining managed group.", flush=True)
                os.killpg(identity.pid, signal.SIGKILL)
    except (DevError, OSError):
        print("Supervisor could not finish its operation. Check local process permissions and configuration.", flush=True)
        return 1
    finally:
        Path(path).unlink(missing_ok=True)
    return 1


def main():
    os.umask(0o077)
    if len(sys.argv) == 4 and sys.argv[1] == "--supervise":
        return supervise(sys.argv[2], int(sys.argv[3]))

    parser = argparse.ArgumentParser(description="Manage MealMind's local development servers on macOS.")
    parser.add_argument("command", choices=("start", "stop", "restart", "status"))
    args = parser.parse_args()

    if sys.platform != "darwin":
        print("This development manager requires macOS.", file=sys.stderr)
        return 1
    try:
        STATE.mkdir(mode=0o700, exist_ok=True)
        info = STATE.stat()
        if STATE.is_symlink() or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise DevError(f"{STATE} must be a private directory owned by the current user (mode 700).")
        with open(STATE / "lock", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if args.command == "status":
                status()
            elif args.command == "stop":
                return 0 if stop(SERVICES) else 1
            elif args.command == "restart":
                if not stop(SERVICES):
                    return 1
                start(lock.fileno())
            else:
                start(lock.fileno())
    except DevError as exc:
        print(exc, file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Local operation failed (errno {exc.errno}). See logs in {STATE}.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted. Run ./dev status to check managed services.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
