import sys

import facere as fac


@fac.rule(default=True)
def answer(target: fac.Output = fac.out("answer.txt")):
    answer = fac.capture(sys.executable, "-c", "print(6 * 7, end='')")
    with open(target, "w") as file:
        file.write(answer)
