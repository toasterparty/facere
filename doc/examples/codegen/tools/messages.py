import tomllib
from pathlib import PurePosixPath

C_TYPES = {"string": "const char *", "int": "int"}


def generate(spec: str, header: str, source: str) -> None:
    name = PurePosixPath(spec).stem
    with open(spec, "rb") as file:
        fields = tomllib.load(file)["fields"]
    members = "".join(f"    {C_TYPES[kind]} {field};\n" for field, kind in fields.items())
    guard = f"MESSAGES_{name.upper()}_H"
    with open(header, "w", encoding="utf-8", newline="\n") as file:
        file.write(
            f"#ifndef {guard}\n#define {guard}\n\nstruct {name} {{\n{members}}};\n\nint {name}_validate(const struct {name} *message);\n\n#endif\n"
        )
    with open(source, "w", encoding="utf-8", newline="\n") as file:
        file.write(
            f'#include "messages/{name}.h"\n\nint {name}_validate(const struct {name} *message)\n{{\n    return message != 0;\n}}\n'
        )
