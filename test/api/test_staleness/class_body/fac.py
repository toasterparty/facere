import facere as fac

MARK = "!"


def upper(self, text):
    return text.upper()


class Style:
    mark = MARK
    transform = upper

    def apply(self, text):
        return self.transform(text) + self.mark


@fac.rule(default=True)
def shout(target: fac.Output = fac.out("a.txt")):
    fac.write_text(target, Style().apply("hi"))
