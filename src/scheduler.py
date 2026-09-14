"""Background scheduler loop for the alarm CLI.

Plain functions. The loop sleeps until the next alarm fires, then invokes a
callback. YAGNI: no threading, no retries, no persistence beyond the store.
"""

from __future__ import annotations

import time
from typing import Callable, List, Optional

import datetime as _dt


def next_fire(alarms: list[dict]) -> Optional[_dt.datetime]:
    """Return the soonest fire time among alarms that are still pending."""
    soonest: Optional[_dt.datetime] = None
    for a in alarms:
        if a.get("fired"):
            continue
        fire = a.get("fire_at")
        if not fire:
            continue
        try:
            dt = _dt.datetime.fromisoformat(fire)
        except (ValueError, TypeError):
            continue
        if soonest is None or dt < soonest:
            soonest = dt
    return soonest


def wait_until(dt: _dt.datetime, stop: Optional[_dt.datetime] = None) -> bool:
    """Sleep until ``dt`` (or ``stop``, whichever is sooner).

    Returns True if we reached ``dt``, False if we were interrupted by ``stop``.
    """
    target = dt
    if stop is not None and stop < target:
        target = stop
    delta = (target - _dt.datetime.now()).total_seconds()
    if delta <= 0:
        return dt <= _dt.datetime.now()
    time.sleep(min(delta, 60))
    return dt <= _dt.datetime.now()


def run_loop(
    alarms: list[dict],
    on_fire: Callable[[dict], None],
    *,
    poll_interval: float = 1.0,
    max_iterations: Optional[int] = None,
    reload: Optional[Callable[[], list[dict]]] = None,
    idle: str = "exit",
) -> None:
    """Block until every alarm has fired (or ``max_iterations`` ticks).

    ``on_fire(alarm)`` is called for each alarm whose time has arrived. The
    callback decides what to do (notify, mark fired, persist). The loop exits
    once all alarms are fired; Ctrl-C exits cleanly with no traceback.

    When ``reload`` is given, the alarms list is refreshed each tick — this lets
    a long-running daemon pick up alarms scheduled by another process.

    ``idle`` controls what happens when there is nothing left to fire:

    - ``"exit"`` (default): the loop returns. Use this for ``wait``.
    - ``"poll"``: the loop keeps sleeping and re-reading. Use this for a
      daemon that must stay alive until alarms are scheduled later.
    
    This applies both when the store is empty and when every alarm has fired.
    A daemon never exits on store state; it stops only on Ctrl-C or
    ``ctl stop``.
    """
    iterations = 0
    try:
        while max_iterations is None or iterations < max_iterations:
            iterations += 1
            if reload is not None:
                alarms[:] = reload()
            if alarms and all(a.get("fired") for a in alarms):
                # All alarms fired. ``wait`` is done; a daemon must stay alive
                # in case new alarms are scheduled later, so it keeps polling.
                if idle == "exit":
                    return
                time.sleep(poll_interval)
                continue
            if not alarms:
                # An empty store means nothing to fire. ``wait`` exits; a daemon
                # that must stay alive keeps polling for alarms scheduled later.
                if idle == "exit":
                    return
                time.sleep(poll_interval)
                continue
            soonest = next_fire(alarms)
            if soonest is None:
                time.sleep(poll_interval)
                continue
            if wait_until(soonest):
                for a in list(alarms):
                    if a.get("fired"):
                        continue
                    fire = a.get("fire_at")
                    if not fire:
                        continue
                    try:
                        dt = _dt.datetime.fromisoformat(fire)
                    except (ValueError, TypeError):
                        continue
                    if dt <= _dt.datetime.now():
                        on_fire(a)
            else:
                # We stopped early (e.g. test timeout); exit.
                return
    except KeyboardInterrupt:
        # Ctrl-C exits cleanly instead of dumping a traceback from the loop.
        return