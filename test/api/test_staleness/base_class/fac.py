import facere as fac


class Style:
    def apply(self, text):
        return text.upper()


class Loud(Style):
    pass


@fac.rule(default=True)
def shout(target: fac.Output = fac.out("a.txt")):
    fac.write_text(target, Loud().apply("hi"))
