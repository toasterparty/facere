import sys

import facere as fac


@fac.rule
def copy(source: fac.Input = "a.txt", target: fac.Output = fac.out("a.txt")):
    fac.write_text(target, fac.read_text(source))


@fac.rule
def quick(target: fac.Output = fac.out("quick.txt")):
    fac.write_text(target, "quick")


@fac.rule
def greedy(target: fac.Output = fac.out("greedy.txt")):
    fac.give_lock()


# Once it gives the lock, an invocation it starts on the same output directory need not wait.
@fac.task
def serve():
    fac.give_lock()
    fac.give_lock()
    fac.run(sys.executable, "-m", "facere", "quick")


@fac.task
def give():
    fac.give_lock()


@fac.task
def tamper_then_give(copied: fac.Input = fac.out("a.txt")):
    fac.write_text(copied, "tampered")
    fac.give_lock()
