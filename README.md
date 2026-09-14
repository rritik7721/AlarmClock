# alarm

The alarm is a command line tool that schedules and fires alarms.
A scheduler loop sleeps until an alarm is due. Then it rings the alarm.
You schedule an alarm by absolute time or by a relative duration.
You run the scheduler loop to fire alarms.

You start a background daemon and drive it from an interactive terminal.
The alarm has no web UI, no database, and no external dependencies.
It is six small modules in `src/`.
It needs Python 3.10 or later.

## Install

Run this command:

```bash
pip install -e .
```

This installs the `alarm` command.
Then you need a virtualenv to use this command.
A virtualenv is an isolated copy of Python.
It keeps the `alarm` command separate from other tools.

You do not need to install anything to try the alarm.
The alarm uses only the Python standard library.
So `python src/cli.py ...` works on any computer with Python 3.10 or later.
It works with or without a virtualenv.
It works on Linux, macOS, and Windows.

## Run it

Run this command:

```bash
alarm --help
```

Any of these commands work, from any directory:

```bash
python src/cli.py add --in 1m --message hi     # direct script, no install
python -m cli add --in 1m --message hi        # from the src/ directory
alarm add --in 1m --message hi                # installed command
```

## Commands

This table lists the commands.

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

`--store PATH` overrides the store location. Put it before the subcommand:

```bash
alarm --store /path/to/store.json add ...
```

## Time formats

`--at` accepts these forms:

- `12-sept-2026 16:00` / `12-sep-2026 4pm`
- `2026-09-12 16:00:00`
- `12/09/2026 16:00`
- `16:00` (time-only: today, or tomorrow if already passed)

`--in` accepts durations with the units `s`, `m`, `h`, `d`.
It accepts decimals and compounds: `30m`, `2h`, `1d`, `90s`, `0.5m`, `1h30m`.

## Sound

By default an alarm rings the terminal bell and prints its message.
No audio file plays.
No second program starts.

Add `--sound` to play generated white noise instead:

```bash
alarm add --in 1m --message "standup" --sound
```

White noise is a constant sound made of many frequencies at once.
`--sound` is per-alarm.

You can mix sound and bell alarms.
The `list` command shows a `sound` column.
The alarm tries `aplay`, then `ffplay`, then Windows `winsound.MessageBeep`, then the terminal bell.
An audio backend is the program that plays sound.
A headless machine has no audio backend.
The alarm never fails.
So it works on headless machines, on SSH, and in CI.

## The background daemon (`ctl`)

`alarm ctl` starts a daemon.
A daemon is a program that runs in the background without a terminal.
The daemon keeps the scheduler alive.
Then it drops you into an interactive terminal.
This terminal shares the same store as the daemon.

Alarms you schedule there fire in the background.
They fire even after you leave.

```bash
alarm ctl
# daemon started (pid 123) watching ~/.local/share/alarm/alarm.json
# Schedule alarms here; they fire in the background. 'exit' to detach, 'ctl stop' to stop.
alarm> add --in 1m --message standup --sound
alarm> exit
# daemon left running in the background
alarm ctl stop
```

The daemon re-reads the store each tick.
So alarms scheduled from the interactive terminal are picked up and fired.

`exit` detaches.
It does not kill the daemon.
Use `ctl stop` to stop it.

The daemon reads the store every 0.5 seconds.
So a nearer alarm scheduled while the process sleeps is discovered quickly.
If the current alarm is more than 0.5 seconds away, a nearer one can be about 0.5 seconds late.

## Store

Alarms persist to a JSON file.
One file per invocation:

- Linux: `~/.local/share/alarm/alarm.json`
- Windows: `%APPDATA%/alarm/alarm.json`

Override the location with `--store PATH` or the `ALARM_STORE_DIR` environment variable.
Writes are atomic.
The alarm writes to a temp file, then moves it into place with `os.replace`.
A reader never sees a half-written file.

## Caveats

**Timing precision.**
The scheduler is a synchronous loop.
It uses `time.sleep`.
It has no event loop, no async, and no threads.
These are ways to run more than one thing at once.
A synchronous loop runs one thing at a time.
Alarms fire at or after their scheduled time.
They never fire early.

The sleep is capped at 60 seconds.
The loop re-evaluates it each tick.
So a nearer alarm scheduled while the process sleeps is discovered on the next wake.
It fires before the previously scheduled one.
If the current alarm is more than a minute away, a nearer one added during that sleep can be about 60 seconds late.

For sub-second precision, use `ctl`.
It reads the store every 0.5 seconds.

**`wait` exits when the store is empty.**
`wait` re-reads the store each tick.
So alarms scheduled externally while it is running are picked up and fired.
`wait` on an empty store exits immediately.
It does not loop.

**Sound.**
`--sound` tries `aplay`, then `ffplay`, then Windows `winsound.MessageBeep`, then the terminal bell.
An audio backend is the program that plays sound.
A headless machine has no audio backend.
The alarm never fails.
So it works on headless machines, on SSH, and in CI.

**`wait` is single-threaded.**
One process runs at a time.
One loop runs in that process.
If you need alarms to fire after the shell that scheduled them closes, use `ctl`.
The daemon detaches on `exit`.

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

The alarm uses plain functions.
It has no classes.
It has no third-party dependencies.

## Notes

`wait` blocks until the store has no pending alarms left.
It re-reads the store each tick.
So externally-scheduled alarms are picked up mid-run.
Ctrl-C exits cleanly.
It prints no traceback.

`--sound` starts a second program.
Without it the alarm is pure Python plus a terminal escape code.
So it works on headless machines, on SSH, and in CI.

The alarm started as three types: cron-based, pure-Python, and Textual TUI.
We consolidated it into this single pure-Python implementation.