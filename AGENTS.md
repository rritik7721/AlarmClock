# AGENTS.md — alarm

Guidance for AI agents working in this repository. Read this first.

## What this is

A pure-Python alarm clock CLI. Six modules in `src/`, no dependencies, no web
UI, no database. The installed command is `alarm`.

## Layout

```
src/
├── cli.py          # argparse entry point + all command handlers
├── storage.py      # JSON store: load_alarms, save_alarms, default_store_path
├── parsing.py      # parse_alarm_time, parse_duration
├── notify.py       # beep() + play_static() (white noise via aplay/ffplay/winsound)
├── ids.py          # make_id
└── scheduler.py    # run_loop, next_fire, wait_until
pyproject.toml     # alarm = "cli:main"; py-modules sourced from src/
```

Everything is flat — there is no `src/alarm/` package. Imports inside `cli.py`
are absolute (`from storage import ...`) with a `sys.path` shim so the file
works as `python src/cli.py`, as `python -m cli` (from `src/`), and as the
installed `alarm` command.

## How to run / test

```bash
source bin/activate          # venv at the project root
pip install -e .             # installs the `alarm` command
alarm --help
```

Smoke-test pattern (use a temp store so the real one stays clean):

```bash
export ALARM_STORE_DIR=/tmp/alarmtest
alarm add --at "2000-01-01 00:00" --message smoke --sound
alarm wait          # fires immediately, prints the message, exits 0
alarm list          # shows fired: true
```

A past `--at` fires on the next `wait`. Use `--in` for future alarms.

## Conventions

- **Plain functions, no classes.** YAGNI: nothing here is object-oriented on
  purpose. Keep new code functional and small.
- **No third-party dependencies.** The stdlib covers argparse, json, wave,
  struct, subprocess, secrets, re. `textual` is installed in the venv but is
  **not used** — the Textual TUI was dropped when the project was consolidated
  into this single implementation. Do not re-add it.
- **Atomic writes.** `save_alarms` writes a temp file then `os.replace`s it.
  Preserve that.
- **Cross-platform store path.** `default_store_path` uses `%APPDATA%/alarm`
  on Windows and `~/.local/share/alarm` on Unix. `ALARM_STORE_DIR` and
  `--store` override it.
- **Ctrl-C is clean.** `run_loop` catches `KeyboardInterrupt` internally and
  returns; it never raises a traceback out of the loop.
- **`--store` goes before the subcommand.** `alarm --store /path ctl`, not
  `alarm ctl --store /path`.

## The `ctl` daemon

`alarm ctl` starts a detached daemon and drops into an interactive terminal
sharing one JSON store. Key behaviors an agent must preserve:

- The daemon is started with `start_new_session=True` and **detaches** when
  you type `exit` — it is *not* killed on session end. Stop it with
  `alarm ctl stop`.
- The daemon reloads the store each tick (`reload=` on `run_loop`), so alarms
  scheduled from the interactive terminal are picked up and fired.
- `cmd_ctl`'s `finally` block must detach, not kill. A final sweep that kills
  the daemon would defeat the whole feature.
- `ctl status` / `ctl stop` read and remove the `<store>.pid` file.

## Time parsing

`parse_duration` uses a regex (`(\d+(?:\.\d+)?)([smhd])`) and accepts decimals
(`0.5m`) and compounds (`1h30m`). Bad input raises `ValueError` with a helpful
message listing the accepted forms. `parse_alarm_time` accepts the forms
listed in README.md; time-only input schedules today or tomorrow.

## Gotchas

- Running `python src/cli.py` directly works because of the `sys.path` shim.
  Removing that shim breaks all three invocation methods.
- `--sound` is per-alarm and persisted as `"sound": true` in the store. If no
  audio backend exists, `play_static` falls back to the bell — never crash.
- The store is JSON; `fired` is a boolean on each record. Don't rename fields
  without updating every reader.
- Test only against temp stores. The real store is `~/.local/share/alarm/alarm.json`.