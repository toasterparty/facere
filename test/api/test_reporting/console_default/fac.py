import sys

import facere as fac

fac.console(fac.Console.ON_FAILURE)


@fac.rule(default=True)
def hidden(target: fac.Output = fac.out("hidden.txt")):
    fac.run(sys.executable, "-c", "print('hidden')")
    open(target, "w").close()


@fac.rule
def overridden(target: fac.Output = fac.out("overridden.txt")):
    fac.run(sys.executable, "-c", "print('overridden')", console=fac.Console.AFTER)
    open(target, "w").close()


@fac.task
def live():
    fac.run(sys.executable, "-c", "print('live')")
