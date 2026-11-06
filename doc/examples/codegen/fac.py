import facere as fac
from tools import messages

SPECS = fac.sources("messages/*.toml")
KEYWORD_TABLE = "src/keywords.gperf"
KEYWORDS = fac.out("gen/keywords.c")
MESSAGE_RULES = [
    {"spec": spec, "header": fac.out(f"gen/{spec}", ".h"), "source": fac.out(f"gen/{spec}", ".c")}
    for spec in SPECS
]


@fac.rule(each=MESSAGE_RULES)
def message(spec: fac.Input, header: fac.Output, source: fac.Output):
    messages.generate(spec, header, source)


@fac.rule
def keywords(table: fac.Input = KEYWORD_TABLE, source: fac.Output = KEYWORDS):
    fac.run("gperf", "--language=ANSI-C", f"--output-file={source}", table)


SOURCES = fac.sources("src/**/*.c") + [rule["source"] for rule in MESSAGE_RULES] + [KEYWORDS]
HEADERS = [rule["header"] for rule in MESSAGE_RULES]

cc = fac.c.Toolchain(cflags=["-O2", "-Wall", "-I.", "-I" + fac.out("gen")])
cc.executable("server", SOURCES, inputs=HEADERS, default=True)
fac.c.compile_commands(default=True)
