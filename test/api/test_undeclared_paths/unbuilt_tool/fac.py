import facere as fac

TOOL = fac.out("tool")


@fac.rule
def build_tool(tool: fac.Output = TOOL):
    fac.write_text(tool, "")


@fac.rule(default=True)
def use(result: fac.Output = fac.out("result.txt")):
    fac.run(fac.out("tool"), stdout=result)
