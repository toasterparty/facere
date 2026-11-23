import sys

import facere as fac

# Ctrl-C ends it without the traceback Python would print among Facere's lines.
SERVE = "import os, signal, sys, time; signal.signal(signal.SIGINT, signal.SIG_DFL); open(sys.argv[1], 'w').write(str(os.getpid())); time.sleep(60)"


@fac.task
def serve(source: fac.Input = "source.txt"):
    with open(fac.out("starts.txt"), "a", encoding="utf-8") as file:
        file.write(fac.read_text(source))
    fac.run(sys.executable, "-c", SERVE, fac.out("pid"))
