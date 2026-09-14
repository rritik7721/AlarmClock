# alarm

A pure-Python alarm clock with a CLI. Schedule alarms by absolute time or
relative duration, run an in-process scheduler loop that fires them, or start
a detached background daemon and drive it from an interactive terminal.

No web UI, no database, no external dependencies — the whole thing is six
small modules in `src/`.

## Install

```bash
pip install -e .
```

This installs the `alarm` console command. The package is pure Python 3.10+.

**No install needed to try it.** The alarm code uses only the Python standard
library, so `python src/cli.py ...` works on any computer with Python 3.10+ —
with or without a virtualenv, on Linux, macOS, or Windows.

## Run it

```bash
alarm --help
```

Any of these work, from any directory:

```bash
python src/cli.py add --in 1m --message hi     # direct script, no install
python -m cli add --in 1m --message hi        # from the src/ directory
alarm add --in 1m --message hi                # installed command
```

## Commands

| Command | What it does |
|---|---|
| `add --at "12-sept-2026 16:00" --message x` | schedule an alarm at an absolute time |
| `add --in 30m --message x` | schedule an alarm in a relative duration |
| `list` | show all alarms with id, time, status, message |
| `edit <id> --at "..." --message "..."` | change an alarm's time and/or message |
| `delete <id>` | remove one alarm |
| `clear-all` | remove all alarms |
| `wait` | run the scheduler loop until alarms fire (Ctrl-C to stop) |
| `ctl` | start a background daemon, then drop into an interactive terminal |
| `ctl status` | report whether a daemon is running |
| `ctl stop` | stop a running daemon |

`--store PATH` overrides the JSON store location. It goes **before** the
subcommand: `alarm --store /path/to/store.json add ...`.

## Time formats

`--at` accepts:

- `12-sept-2026 16:00` / `12-sep-2026 4pm`
- `2026-09-12 16:00:00`
- `12/09/2026 16:00`
- `16:00` (time-only: today, or tomorrow if already passed)

`--in` accepts durations with units `s`, `m`, `h`, `d`, including decimals and
compounds: `30m`, `2h`, `1d`, `90s`, `0.5m`, `1h30m`.

## Sound

By default an alarm rings the **terminal bell** and prints its message — no
audio file, no subprocess. Add `--sound` to play generated white-noise static
instead:

```bash
alarm add --in 1m --message "standup" --sound
```

`--sound` is per-alarm, so you can mix. `list` shows a `sound` column. If you
ask for sound but no audio backend is available (`aplay`/`ffplay` on POSIX,
`winsound` on Windows), it falls back to the bell — it never fails.

## The background daemon (`ctl`)

`alarm ctl` starts a detached daemon that keeps the scheduler alive, then
drops you into an interactive terminal sharing the same JSON store. Alarms you
schedule there fire in the background even after you leave.

```bash
alarm ctl
# daemon started (pid 123) watching ~/.local/share/alarm/alarm.json
# Schedule alarms here; they fire in the background. 'exit' to detach, 'ctl stop' to stop.
alarm> add --in 1m --message standup --sound
alarm> exit
# daemon left running in the background
alarm ctl stop
```

The daemon reloads the store each tick, so alarms scheduled from the interactive
terminal are picked up and fired. `exit` detaches rather than kills it; use
`ctl stop` to stop it. The daemon polls every 0.5s, so a nearer alarm scheduled
while it is sleeping is discovered quickly — but if the current alarm is more
than 0.5s away, a nearer one can still be up to ~0.5s late.

## Store

Alarms persist to a JSON file, one per invocation:

- Linux: `~/.local/share/alarm/alarm.json`
- Windows: `%APPDATA%/alarm/alarm.json`
- Override with `--store PATH` or the `ALARM_STORE_DIR` environment variable.

Writes are atomic (write to a temp file, then `os.replace`).

## Caveats

- **Timing precision.** The scheduler is a plain synchronous loop with
  `time.sleep` — no event loop, no async, no threads. Alarms fire at or after
  their scheduled time, never early. The sleep is capped at 60 seconds and
  re-evaluated each tick, so a nearer alarm scheduled while the process is
  sleeping is discovered on the next wake and fires before the previously
  scheduled one. If the current alarm is more than a minute away, a nearer one
  added during that sleep can be up to ~60 seconds late. For sub-second
  precision use `ctl` (0.5s poll).
- **`wait` exits when the store is empty.** It re-reads the store each tick, so
  alarms scheduled externally while it is running are picked up and fired.
  `wait` on an empty store exits immediately rather than looping.
- **Sound degrades gracefully.** `--sound` tries `aplay`, then `ffplay`, then
  Windows `winsound.MessageBeep`, then the terminal bell. It never crashes if
  no audio backend is available — so it works on headless machines, SSH, and
  CI.
- **`wait` is single-threaded.** One process, one loop. If you need alarms to
  keep firing after the scheduling shell closes, use `ctl` (the daemon
  detaches on `exit`).

## Layout

```
src/
├── cli.py          # argparse: add/list/edit/delete/clear-all/wait/ctl
├── storage.py      # JSON store, atomic writes, cross-platform path
├── parsing.py      # parse_alarm_time, parse_duration (decimals + compound)
├── notify.py       # terminal bell + white-noise static via aplay/ffplay/winsound
├── ids.py          # make_id
└── scheduler.py    # run_loop, next_fire, wait_until (with reload hook)
```

Plain functions throughout, no classes, no third-party dependencies.

## Notes

- `wait` blocks until the store has no pending alarms left; it re-reads the
  store each tick, so externally-scheduled alarms are picked up mid-run.
  Ctrl-C exits cleanly with no traceback.
- `--sound` shells out to an audio player; without it the alarm is pure Python
  plus a terminal escape code, so it works on headless machines, SSH, and CI.
- The original three-type design (cron-based, pure-Python, and Textual TUI
  variants) was consolidated into this single pure-Python implementation.