import facere as fac

MARK = "!"


class Style:
    class Mark:
        def apply(self, text):
            return text + MARK

    def apply(self, text):
        return self.Mark().apply(text.upper())


@fac.rule(default=True)
def shout(target: fac.Output = fac.out("a.txt")):
    fac.write_text(target, Style().apply("hi"))
