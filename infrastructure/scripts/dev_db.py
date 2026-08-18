#!/usr/bin/env python
"""Local development datastore manager.

Starts PostgreSQL 16 and Redis under `.devdata/` so the whole stack runs without Docker or root
access. Production uses real managed Postgres/Redis via DATABASE_URL / REDIS_URL — nothing in the
application imports this module.

Both servers are started as detached background processes listening on TCP, so they survive the
exit of this script and are reachable from every other process (API, worker, tests).

Usage:
    python infrastructure/scripts/dev_db.py start    # boot both, create the database
    python infrastructure/scripts/dev_db.py status
    python infrastructure/scripts/dev_db.py env      # shell export lines
    python infrastructure/scripts/dev_db.py stop
    python infrastructure/scripts/dev_db.py reset    # destroy and recreate all local data
"""

from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / ".devdata"
PG_DATA = DATA_DIR / "pgdata"
REDIS_DIR = DATA_DIR / "redis"
LOG_DIR = DATA_DIR / "logs"

PG_PORT = int(os.environ.get("DEV_PG_PORT", "5433"))
REDIS_PORT = int(os.environ.get("DEV_REDIS_PORT", "6399"))
DB_NAME = "rozgar"
DB_USER = os.environ.get("USER", "rozgar")

HOST = "127.0.0.1"


# --------------------------------------------------------------------- utils --

def _port_open(port: int, host: str = HOST) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _wait_for_port(port: int, timeout: float = 25.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _port_open(port):
            return True
        time.sleep(0.3)
    return False


def _pg_bin(name: str) -> Path:
    """Prefer a system PostgreSQL; fall back to the pgserver-bundled binaries."""
    system = shutil.which(name)
    if system:
        return Path(system)
    try:
        import pgserver

        bundled = Path(pgserver.__file__).parent / "pginstall" / "bin" / name
        if bundled.exists():
            return bundled
    except ImportError:
        pass
    sys.exit(
        f"Could not find '{name}'.\n"
        "Install PostgreSQL 16, or `pip install pgserver` for a self-contained build."
    )


def _spawn(argv: list[str], log_name: str) -> subprocess.Popen:
    """Start a detached background process with its output captured to a log file."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = open(LOG_DIR / log_name, "ab")
    return subprocess.Popen(
        argv,
        stdout=log,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,  # survives this script exiting
    )


# ----------------------------------------------------------------- postgres --

def start_postgres() -> str:
    url = f"postgresql+psycopg://{DB_USER}@{HOST}:{PG_PORT}/{DB_NAME}"

    if _port_open(PG_PORT):
        print(f"  postgres  already running on {PG_PORT}")
        return url

    if not (PG_DATA / "PG_VERSION").exists():
        print(f"  postgres  initialising cluster in {PG_DATA.relative_to(ROOT)}")
        PG_DATA.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [str(_pg_bin("initdb")), "-D", str(PG_DATA), "-U", DB_USER, "--auth=trust",
             "--encoding=UTF8", "--locale=C"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            sys.exit(f"initdb failed:\n{result.stdout}\n{result.stderr}")

    print(f"  postgres  starting on {PG_PORT}")
    _spawn(
        [str(_pg_bin("postgres")), "-D", str(PG_DATA), "-p", str(PG_PORT),
         "-k", str(PG_DATA), "-c", "listen_addresses=127.0.0.1"],
        "postgres.log",
    )
    if not _wait_for_port(PG_PORT):
        sys.exit(f"Postgres did not start. See {LOG_DIR / 'postgres.log'}")

    # Create the application database if this is a fresh cluster.
    check = subprocess.run(
        [str(_pg_bin("psql")), "-h", HOST, "-p", str(PG_PORT), "-U", DB_USER,
         "-d", "postgres", "-tAc", f"SELECT 1 FROM pg_database WHERE datname='{DB_NAME}'"],
        capture_output=True, text=True,
    )
    if check.stdout.strip() != "1":
        subprocess.run(
            [str(_pg_bin("createdb")), "-h", HOST, "-p", str(PG_PORT), "-U", DB_USER, DB_NAME],
            check=True,
        )
        print(f"  postgres  created database '{DB_NAME}'")

    return url


def stop_postgres() -> None:
    pid_file = PG_DATA / "postmaster.pid"
    if not pid_file.exists():
        print("  postgres  not running")
        return
    subprocess.run(
        [str(_pg_bin("pg_ctl")), "-D", str(PG_DATA), "stop", "-m", "fast"],
        capture_output=True,
    )
    print("  postgres  stopped")


# -------------------------------------------------------------------- redis --

def start_redis() -> str:
    url = f"redis://{HOST}:{REDIS_PORT}/0"

    if _port_open(REDIS_PORT):
        print(f"  redis     already running on {REDIS_PORT}")
        return url

    REDIS_DIR.mkdir(parents=True, exist_ok=True)
    binary = shutil.which("redis-server")
    if not binary:
        try:
            import redislite

            binary = str(Path(redislite.__file__).parent / "bin" / "redis-server")
        except ImportError:
            binary = None
    if not binary or not Path(binary).exists():
        sys.exit("Could not find redis-server. Install Redis, or `pip install redislite`.")

    print(f"  redis     starting on {REDIS_PORT}")
    _spawn(
        [binary, "--port", str(REDIS_PORT), "--bind", HOST, "--dir", str(REDIS_DIR),
         "--daemonize", "no", "--save", "900", "1", "--appendonly", "no"],
        "redis.log",
    )
    if not _wait_for_port(REDIS_PORT, timeout=15):
        sys.exit(f"Redis did not start. See {LOG_DIR / 'redis.log'}")
    return url


def stop_redis() -> None:
    if not _port_open(REDIS_PORT):
        print("  redis     not running")
        return
    pid_file = REDIS_DIR / f"redis_{REDIS_PORT}.pid"
    try:
        binary = shutil.which("redis-cli")
        if binary:
            subprocess.run([binary, "-p", str(REDIS_PORT), "shutdown", "nosave"],
                           capture_output=True, timeout=5)
        elif pid_file.exists():
            os.kill(int(pid_file.read_text().strip()), signal.SIGTERM)
    except Exception:  # noqa: BLE001 - best effort shutdown
        pass
    print("  redis     stopped")


# ---------------------------------------------------------------- commands --

def cmd_start() -> int:
    print("Starting development datastores:")
    database_url = start_postgres()
    redis_url = start_redis()

    print()
    print("  DATABASE_URL =", database_url)
    print("  REDIS_URL    =", redis_url)

    env_file = ROOT / ".env"
    if env_file.exists():
        content = env_file.read_text()
        if f":{PG_PORT}/" not in content:
            print()
            print("  NOTE: your .env points somewhere else. Update it with the URLs above,")
            print("        or run: python infrastructure/scripts/dev_db.py env >> .env")
    return 0


def cmd_stop() -> int:
    print("Stopping development datastores:")
    stop_redis()
    stop_postgres()
    return 0


def cmd_status() -> int:
    pg = "running" if _port_open(PG_PORT) else "stopped"
    rd = "running" if _port_open(REDIS_PORT) else "stopped"
    print(f"  postgres  {pg:8} port {PG_PORT}")
    print(f"  redis     {rd:8} port {REDIS_PORT}")
    return 0 if pg == "running" and rd == "running" else 1


def cmd_env() -> int:
    print(f"DATABASE_URL=postgresql+psycopg://{DB_USER}@{HOST}:{PG_PORT}/{DB_NAME}")
    print(f"REDIS_URL=redis://{HOST}:{REDIS_PORT}/0")
    print(f"CELERY_BROKER_URL=redis://{HOST}:{REDIS_PORT}/1")
    print(f"CELERY_RESULT_BACKEND=redis://{HOST}:{REDIS_PORT}/2")
    return 0


def cmd_reset() -> int:
    confirm = input(f"Delete ALL local data in {DATA_DIR}? [y/N] ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return 1
    cmd_stop()
    time.sleep(1)
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    print("Local data removed. Run `start` to recreate, then apply migrations.")
    return 0


def main() -> int:
    commands = {
        "start": cmd_start, "stop": cmd_stop, "status": cmd_status,
        "env": cmd_env, "reset": cmd_reset,
    }
    command = sys.argv[1] if len(sys.argv) > 1 else "start"
    if command not in commands:
        print(f"Usage: {sys.argv[0]} [{' | '.join(commands)}]", file=sys.stderr)
        return 2
    return commands[command]()


if __name__ == "__main__":
    raise SystemExit(main())
