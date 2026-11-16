import os
import sys

assert sys.platform != "win32"
import termios  # noqa: E402 - Windows has none, which the line above tells the type checker


def has_controlling_terminal():
    try:
        os.close(os.open("/dev/tty", os.O_RDWR))
    except OSError:
        return False
    return True


facts = [
    os.isatty(0),
    os.isatty(1),
    os.isatty(2),
    has_controlling_terminal(),
    tuple(os.get_terminal_size(2)) if os.isatty(2) else None,
    bool(termios.tcgetattr(2)[1] & termios.OPOST) if os.isatty(2) else None,
]
with open(sys.argv[1], "w") as file:
    file.write(repr(facts))
print("to stderr", file=sys.stderr)
