import sys

import facere as fac

READ_STDIN = "import sys; sys.stdout.write(sys.stdin.read())"


@fac.task(default=True)
def feed():
    unfed = fac.run(sys.executable, "-c", READ_STDIN, quiet=True)
    fed = fac.run(sys.executable, "-c", READ_STDIN, stdin="in.txt", quiet=True)
    print(f"{unfed!r} {fed!r}")
