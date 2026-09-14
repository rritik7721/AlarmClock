"""Alarm notification.

Prints the message and either rings the terminal bell or plays generated
white-noise static through ``aplay``. No external dependencies: the WAV is
built in-memory from stdlib ``wave``/``struct``.
"""

import io
import random
import shutil
import struct
import subprocess
import sys
import time
import wave

try:
    import winsound  # Windows-only; absent on POSIX.
except ImportError:
    winsound = None

_BELL = "\a"
_SAMPLE_RATE = 8000
_AMPLITUDE = 32767


def _static_wav(seconds: float = 1.0, sample_rate: int = _SAMPLE_RATE) -> bytes:
    """Return white-noise static as a WAV byte string."""
    n = int(sample_rate * seconds)
    samples = (random.randint(-_AMPLITUDE, _AMPLITUDE) for _ in range(n))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(struct.pack(f"<{n}h", *samples))
    return buf.getvalue()


def _play_wav(data: bytes) -> bool:
    """Play WAV bytes. Tries aplay, then ffplay. Returns True on success."""
    for player in ("aplay", "ffplay"):
        exe = shutil.which(player)
        if not exe:
            continue
        cmd = [exe]
        if player == "aplay":
            cmd += ["-q", "-t", "wav", "-"]
        else:
            cmd += ["-autoexit", "-nodisp", "-log", "quiet", "-"]
        try:
            proc = subprocess.run(
                cmd,
                input=data,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
            )
            if proc.returncode == 0:
                return True
        except (subprocess.SubprocessError, OSError):
            continue
    return False


def play_static(seconds: float = 1.0) -> bool:
    """Play white-noise static.

    Order: aplay/ffplay WAV, then Windows ``winsound.MessageBeep`` (a simple
    system beep), then the terminal bell. Returns True if anything played.
    """
    if _play_wav(_static_wav(seconds)):
        return True
    if winsound is not None:
        try:
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            return True
        except Exception:
            pass
    beep()
    return False


def beep(count: int = 3, stream=None) -> None:
    """Ring the terminal bell ``count`` times."""
    stream = stream or sys.stderr
    for _ in range(count):
        stream.write(_BELL)
        stream.flush()
        time.sleep(0.25)


def notify(message: str, times: int = 1, sound: bool = False, stream=None) -> None:
    """Print ``message`` and beep (or play static when ``sound`` is True)."""
    stream = stream or sys.stdout
    for _ in range(times):
        stream.write(f"\n*** ALARM: {message} ***\n")
        stream.flush()
        if sound:
            play_static()
        else:
            beep()
        if times > 1:
            time.sleep(1)