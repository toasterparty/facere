import os

import facere as fac


@fac.rule(default=True)
def unpack(obj: fac.Output = fac.out("main.o")):
    os.makedirs("third_party", exist_ok=True)
    fac.write_text("third_party/vendor.h", "vendor")
    fac.add_inputs(["third_party/vendor.h"])
    fac.write_text(obj, fac.read_text("third_party/vendor.h"))
