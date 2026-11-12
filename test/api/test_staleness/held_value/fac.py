import dataclasses

import facere as fac


@dataclasses.dataclass(frozen=True)
class Style:
    marks: frozenset[str]

    def apply(self, text):
        return text.upper() + "".join(sorted(self.marks))


STYLE = Style(frozenset({"!", "?", "~", "#", "*", "+"}))


@fac.rule(default=True)
def shout(target: fac.Output = fac.out("a.txt"), style=STYLE):
    fac.write_text(target, style.apply("hi"))


@fac.rule(default=True)
def whisper(target: fac.Output = fac.out("b.txt")):
    fac.write_text(target, STYLE.apply("ho"))
