"""Alarm CLI.

Pure-Python in-process scheduler. ``alarm add`` schedules; ``alarm wait`` runs
the loop until alarms fire. Alarms ring the terminal bell by default; ``--sound``
plays generated white-noise static through ``aplay``. Ctrl-C exits cleanly.

``alarm ctl`` starts a background daemon that keeps the scheduler alive, and
drops you into an interactive terminal sharing the same store — so you can
schedule alarms from one shell while another process fires them.

Run ``alarm --help``.
"""

import argparse
import datetime as _dt
import os
import shlex
import signal
import subprocess
import sys
from typing import Optional

# Works both as a direct ``python src/cli.py`` script and as the installed
# ``alarm`` command. Adds the project root so the sibling modules import
# regardless of how the file was launched.
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT = os.path.dirname(_HERE)
_THIS_FILE = os.path.abspath(__file__)
if _PROJECT not in sys.path:
    sys.path.insert(0, _PROJECT)

from ids import make_id
from notify import notify
from parsing import parse_alarm_time, parse_duration
from scheduler import run_loop
from storage import default_store_path, load_alarms, save_alarms


def add_alarm(
    message: str,
    at: Optional[str] = None,
    in_: Optional[str] = None,
    store: Optional[str] = None,
    sound: bool = False,
) -> dict:
    """Schedule one alarm, persist it, return the record."""
    if at is None and in_ is None:
        raise ValueError("provide --at or --in")
    if at is not None and in_ is not None:
        raise ValueError("use only one of --at or --in")
    if at is not None:
        fire = parse_alarm_time(at)
    else:
        fire = parse_duration(in_)

    path = store or default_store_path("alarm")
    alarms = load_alarms(path)
    record = {
        "id": make_id(),
        "fire_at": fire.isoformat(timespec="seconds"),
        "message": message or "",
        "fired": False,
        "sound": bool(sound),
    }
    alarms.append(record)
    save_alarms(path, alarms)
    return record


def list_alarms(store: Optional[str] = None) -> list[dict]:
    """Return all alarms, oldest first."""
    path = store or default_store_path("alarm")
    return sorted(load_alarms(path), key=lambda a: a.get("fire_at", ""))


def edit_alarm(
    alarm_id: str,
    at: Optional[str] = None,
    message: Optional[str] = None,
    store: Optional[str] = None,
) -> Optional[dict]:
    """Change an alarm's time and/or message. Returns the updated record or None."""
    path = store or default_store_path("alarm")
    alarms = load_alarms(path)
    for a in alarms:
        if a.get("id") == alarm_id:
            if at is not None:
                a["fire_at"] = parse_alarm_time(at).isoformat(timespec="seconds")
            if message is not None:
                a["message"] = message
            save_alarms(path, alarms)
            return a
    return None


def delete_alarm(alarm_id: str, store: Optional[str] = None) -> bool:
    """Remove one alarm by id. Returns True if found."""
    path = store or default_store_path("alarm")
    alarms = load_alarms(path)
    before = len(alarms)
    alarms = [a for a in alarms if a.get("id") != alarm_id]
    if len(alarms) == before:
        return False
    save_alarms(path, alarms)
    return True


def clear_all(store: Optional[str] = None) -> int:
    """Remove all alarms. Returns the count removed."""
    path = store or default_store_path("alarm")
    alarms = load_alarms(path)
    count = len(alarms)
    save_alarms(path, [])
    return count


def fire_due(alarms: list[dict]) -> int:
    """Fire every due, unfired alarm. Returns count fired."""
    now = _dt.datetime.now()
    count = 0
    for a in alarms:
        if a.get("fired"):
            continue
        try:
            fire = _dt.datetime.fromisoformat(a["fire_at"])
        except (KeyError, ValueError, TypeError):
            continue
        if fire <= now:
            notify(a.get("message") or "(no message)")
            a["fired"] = True
            count += 1
    return count


def cmd_add(args: argparse.Namespace) -> None:
    record = add_alarm(
        args.message, at=args.at, in_=args.in_, store=args.store, sound=args.sound
    )
    print(f"added alarm {record['id']} at {record['fire_at']}: {record['message']}")


def cmd_list(args: argparse.Namespace) -> None:
    alarms = list_alarms(store=args.store)
    if not alarms:
        print("no alarms scheduled")
        return
    for a in alarms:
        status = "fired" if a.get("fired") else "pending"
        sound = "sound" if a.get("sound") else ""
        print(f"{a['id']}\t{a['fire_at']}\t{status}\t{sound}\t{a.get('message', '')}")


def cmd_edit(args: argparse.Namespace) -> None:
    record = edit_alarm(args.id, at=args.at, message=args.message, store=args.store)
    if record is None:
        print(f"no alarm with id {args.id}", file=sys.stderr)
        raise SystemExit(1)
    print(f"edited {record['id']}: {record['fire_at']} {record['message']}")


def cmd_delete(args: argparse.Namespace) -> None:
    if delete_alarm(args.id, store=args.store):
        print(f"deleted {args.id}")
    else:
        print(f"no alarm with id {args.id}", file=sys.stderr)
        raise SystemExit(1)


def cmd_clear_all(args: argparse.Namespace) -> None:
    n = clear_all(store=args.store)
    print(f"cleared {n} alarm(s)")


def cmd_wait(args: argparse.Namespace) -> None:
    """Run the scheduler loop until all alarms fire or Ctrl-C."""
    path = args.store or default_store_path("alarm")
    alarms = list_alarms(store=path)

    def on_fire(alarm: dict) -> None:
        notify(alarm.get("message") or "(no message)", sound=bool(alarm.get("sound")))
        alarm["fired"] = True
        save_alarms(path, alarms)

    # run_loop returns once every alarm has fired (or on Ctrl-C). It never
    # raises KeyboardInterrupt out of the loop, so no traceback on exit.
    run_loop(alarms, on_fire, poll_interval=1.0)


def _daemon_loop(path: str) -> None:
    """Block forever, firing alarms as they come due. Used by ``alarm ctl``."""
    alarms = load_alarms(path)

    def on_fire(alarm: dict) -> None:
        notify(alarm.get("message") or "(no message)", sound=bool(alarm.get("sound")))
        alarm["fired"] = True
        save_alarms(path, alarms)

    # Reload the store each tick so alarms scheduled from the interactive
    # terminal (or another process) are picked up and fired. on_fire persists
    # the in-memory list, so the fired flag survives the next reload.
    run_loop(
        alarms,
        on_fire,
        poll_interval=0.5,
        max_iterations=None,
        reload=lambda: load_alarms(path),
    )


def _fire_due(path: str) -> None:
    """Fire every currently-due alarm once, persisting the result."""
    alarms = load_alarms(path)
    now = _dt.datetime.now()
    changed = False
    for a in alarms:
        if a.get("fired"):
            continue
        try:
            fire = _dt.datetime.fromisoformat(a["fire_at"])
        except (KeyError, ValueError, TypeError):
            continue
        if fire <= now:
            notify(a.get("message") or "(no message)", sound=bool(a.get("sound")))
            a["fired"] = True
            changed = True
    if changed:
        save_alarms(path, alarms)


def cmd_ctl(args: argparse.Namespace) -> None:
    """Dispatch ``ctl start`` (default), ``ctl status``, or ``ctl stop``."""
    action = getattr(args, "action", "start")
    if action == "status":
        return cmd_ctl_status(args)
    if action == "stop":
        return cmd_ctl_stop(args)
    _ctl_start(args)


def _ctl_start(args: argparse.Namespace) -> None:
    """Start a background daemon, then drop into an interactive terminal.

    Both processes read and write the same JSON store, so you can schedule
    alarms from the interactive shell while the daemon fires them. The daemon
    keeps running after you leave the interactive terminal — type ``exit`` to
    detach, or ``alarm ctl stop`` to kill it.
    """
    path = args.store or default_store_path("alarm")
    ensure_store(path)

    # Start the daemon detached from this terminal so it survives us leaving.
    proc = subprocess.Popen(
        [sys.executable, _THIS_FILE, "--daemon", "--store", path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    print(f"daemon started (pid {proc.pid}) watching {path}")
    print("Schedule alarms here; they fire in the background. 'exit' to detach, 'ctl stop' to stop.")

    try:
        _interactive_loop(path)
    finally:
        # Detach, don't kill: the daemon must keep firing alarms scheduled from
        # this terminal after we leave. It is stopped separately via
        # ``alarm ctl stop``.
        try:
            proc.detach()
        except (AttributeError, OSError):
            pass
        print("daemon left running in the background (use 'alarm ctl stop' to stop it)")


def _interactive_loop(path: str) -> None:
    """Read commands from stdin until 'exit'."""
    parser = build_parser()
    while True:
        try:
            line = input("alarm> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not line:
            continue
        if line in ("exit", "quit"):
            return
        try:
            ns = parser.parse_args(shlex.split(line))
        except SystemExit:
            continue
        try:
            ns.func(ns)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)


def ensure_store(path: str) -> None:
    """Create the store file if it does not exist."""
    if not os.path.exists(path):
        save_alarms(path, [])


def cmd_daemon(args: argparse.Namespace) -> None:
    """Internal: run the daemon loop (used by ``alarm ctl``).

    Registers a PID file on startup and removes it on exit so
    ``ctl status`` / ``ctl stop`` can find and stop the daemon.
    """
    path = args.store or default_store_path("alarm")
    pid_file = _daemon_pid_file(path)
    try:
        with open(pid_file, "w") as fh:
            fh.write(str(os.getpid()))
    except OSError:
        pass
    try:
        _daemon_loop(path)
    finally:
        try:
            os.remove(pid_file)
        except OSError:
            pass


def _daemon_pid_file(path: str) -> str:
    """Return the PID file path that tracks a running daemon."""
    return path + ".pid"


def cmd_ctl_stop(args: argparse.Namespace) -> None:
    """Stop a running background daemon."""
    path = args.store or default_store_path("alarm")
    pid_file = _daemon_pid_file(path)
    pid = None
    if os.path.exists(pid_file):
        try:
            with open(pid_file) as fh:
                pid = int(fh.read().strip())
        except (OSError, ValueError):
            pid = None
    if pid is None:
        print("no daemon pid file; nothing to stop")
        return
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"sent SIGTERM to daemon pid {pid}")
    except ProcessLookupError:
        print(f"daemon pid {pid} already stopped")
    try:
        os.remove(pid_file)
    except OSError:
        pass


def cmd_ctl_status(args: argparse.Namespace) -> None:
    """Report whether a daemon is running for this store."""
    path = args.store or default_store_path("alarm")
    pid_file = _daemon_pid_file(path)
    if not os.path.exists(pid_file):
        print("no daemon running")
        return
    try:
        with open(pid_file) as fh:
            pid = int(fh.read().strip())
    except (OSError, ValueError):
        print("daemon pid file unreadable")
        return
    try:
        os.kill(pid, 0)
        print(f"daemon running (pid {pid})")
    except ProcessLookupError:
        print(f"daemon pid file stale (pid {pid} not running)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alarm",
        description="Alarm clock: pure-Python in-process scheduler.",
    )
    parser.add_argument("--store", help="override JSON store path")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="schedule an alarm")
    p_add.add_argument("--at", help='absolute time, e.g. "12-sept-2026 16:00"')
    p_add.add_argument("--in", dest="in_", help="relative duration, e.g. 30m")
    p_add.add_argument("--message", default="", help="alarm message")
    p_add.add_argument(
        "--sound", action="store_true", help="play white-noise static when it fires"
    )
    p_add.set_defaults(func=cmd_add)

    sub.add_parser("list", help="show scheduled alarms").set_defaults(func=cmd_list)

    p_edit = sub.add_parser("edit", help="change time and/or message of an alarm")
    p_edit.add_argument("id")
    p_edit.add_argument("--at")
    p_edit.add_argument("--message")
    p_edit.set_defaults(func=cmd_edit)

    p_del = sub.add_parser("delete", help="remove one alarm by id")
    p_del.add_argument("id")
    p_del.set_defaults(func=cmd_delete)

    sub.add_parser("clear-all", help="remove all alarms").set_defaults(
        func=cmd_clear_all
    )

    sub.add_parser(
        "wait", help="run the scheduler loop until alarms fire"
    ).set_defaults(func=cmd_wait)

    p_ctl = sub.add_parser(
        "ctl",
        help="start a background daemon, then drop into an interactive terminal",
    )
    p_ctl.add_argument(
        "action",
        nargs="?",
        choices=("start", "status", "stop"),
        default="start",
        help="start (default), status, or stop the daemon",
    )
    p_ctl.set_defaults(func=cmd_ctl)

    return parser


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # Internal daemon mode: invoked by ``alarm ctl`` in a detached process.
    if "--daemon" in argv:
        argv = [a for a in argv if a != "--daemon"]
        store = default_store_path("alarm")
        if "--store" in argv:
            store = argv[argv.index("--store") + 1]
        return cmd_daemon(argparse.Namespace(store=store))
    args = build_parser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

