import facere as fac


@fac.rule
def first(obj: fac.Output = fac.out("first.o")):
    fac.add_inputs(["first.h"])
    fac.write_text(obj, fac.read_text("first.h"))


@fac.rule(default=True)
def second(
    first_obj: fac.Input = fac.out("first.o"),
    ok: fac.Input = "ok.txt",
    obj: fac.Output = fac.out("second.o"),
):
    assert fac.read_text(ok) == "ok"
    fac.write_text(obj, "second")
