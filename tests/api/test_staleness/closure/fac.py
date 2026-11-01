import facere as fac


def define(suffix):
    @fac.rule(default=True)
    def shout(source: fac.Input = "a.txt", target: fac.Output = fac.out("a.txt")):
        with open(source) as file, open(target, "w") as out:
            out.write(file.read() + suffix)


define("!")
