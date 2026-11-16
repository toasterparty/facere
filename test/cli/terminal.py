"""Running `python -m facere` on a pseudo-terminal 10 rows by 40 columns, as from an interactive shell."""

import os
import subprocess
import sys
from pathlib import Path

ROWS = 10
COLUMNS = 40


def start_on_terminal(root: Path, *args: str) -> tuple[subprocess.Popen[bytes], int]:
    """Start Facere in `root` with the terminal as its standard streams, and return it with the terminal's other end, to read what it shows."""
    assert sys.platform != "win32"
    import fcntl
    import pty
    import struct
    import termios

    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLUMNS, 0, 0))
    process = subprocess.Popen(
        [sys.executable, "-m", "facere", *args],
        cwd=root,
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env={**os.environ, "TERM": "xterm"},
    )
    os.close(slave)
    return process, master


def read_all(master: int) -> str:
    """Return everything shown on the terminal until every process closed it."""
    chunks = []
    while True:
        try:
            chunk = os.read(master, 4096)
        except OSError:
            break
        if not chunk:
            break
        chunks.append(chunk)
    os.close(master)
    return b"".join(chunks).decode()
