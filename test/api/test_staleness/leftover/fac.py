import facere as fac


@fac.rule(default=True)
def emit(spec: fac.Input = "spec.txt", header: fac.Output = fac.out("services.h")):
    text = fac.read_text(spec)
    if text:
        fac.write_text(header, text)
