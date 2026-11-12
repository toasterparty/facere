import re

import facere as fac

PATTERN = r"\s+"
UNSET = object()


def squeeze(text, pattern=re.compile(PATTERN), mark=UNSET):
    return pattern.sub(" ", text) + ("" if mark is UNSET else str(mark))


@fac.rule(default=True)
def tidy(target: fac.Output = fac.out("a.txt")):
    fac.write_text(target, squeeze("a   b"))
