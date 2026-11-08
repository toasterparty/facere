import facere as fac

SETTING = fac.read_text("setting.txt")


@fac.rule(default=True)
def use(result: fac.Output = fac.out("result.txt"), setting=SETTING):
    fac.write_text(result, setting)
