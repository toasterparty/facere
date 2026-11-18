import re

import facere as fac

PATTERN = r"\s+"
UNSET = object()


@fac.rule(default=True)
def tidy(target: fac.Output = fac.out("a.txt"), pattern=re.compile(PATTERN), mark=UNSET):
    fac.write_text(target, pattern.sub(" ", "a   b") + ("" if mark is UNSET else str(mark)))
