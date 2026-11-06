import textutil

import facere as fac


def tidy(text):
    return exclaim(text.strip())


def exclaim(text):
    return text + "!"


class Style:
    def apply(self, text):
        return text.upper()


@fac.rule(default=True)
def shout(source: fac.Input = "a.txt", target: fac.Output = fac.out("a.txt")):
    with open(source, encoding="utf-8") as file:
        text = file.read()
    with open(target, "w", encoding="utf-8") as file:
        file.write(textutil.wrap(Style().apply(tidy(text))))
