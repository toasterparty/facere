import ctypes
import msvcrt
import sys
from ctypes import wintypes

assert sys.platform == "win32"


# os.isatty holds for any character device, NUL included, so only a console mode tells a console.
def is_console(descriptor):
    mode = wintypes.DWORD()
    handle = wintypes.HANDLE(msvcrt.get_osfhandle(descriptor))
    return bool(ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode)))


with open(sys.argv[1], "w") as file:
    file.write(repr([is_console(0), is_console(1), is_console(2)]))
print("to stderr", file=sys.stderr)
