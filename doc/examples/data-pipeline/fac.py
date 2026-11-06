"""Regional sales figures cleaned, totaled, and reported, showing each thing fac.run can do for a command. It needs nothing but Python."""

import os
import shutil
import sys

import facere as fac

fac.env(LC_ALL="C", PYTHONUTF8="1")

CURRENCY = "USD"
TITLE = "Sales by item"
CLEAN_TOOL = "tools/clean.py"
TOTAL_TOOL = "tools/total.py"
TABLE_TOOL = "tools/table.py"
CHECKSUM_TOOL = "tools/checksum.py"
SOURCES = fac.sources("data/*.csv")
CLEAN_RULES = [
    {
        "source": source,
        "cleaned": fac.out(source),
        "rejects": fac.out(source, ".rejects.txt"),
    }
    for source in SOURCES
]
CLEANED = [rule["cleaned"] for rule in CLEAN_RULES]
TOTALS = fac.out("totals.csv")
SUMMARY = fac.out("summary.txt")
TOTAL_OUTPUTS = [TOTALS, SUMMARY]
REPORT = fac.out("report.txt")
CHECKSUMS = fac.out("checksums.txt")


@fac.rule(each=CLEAN_RULES)
def clean_data(
    source: fac.Input, cleaned: fac.Output, rejects: fac.Output, tool: fac.Input = CLEAN_TOOL
):
    fac.run(sys.executable, tool, stdin=source, stdout=cleaned, stderr=rejects)


@fac.rule
def total(
    tables: list[fac.Input] = CLEANED,
    tool: fac.Input = TOTAL_TOOL,
    outputs: list[fac.Output] = TOTAL_OUTPUTS,
):
    env = {"REPORT_CURRENCY": CURRENCY}
    fac.run(sys.executable, tool, outputs, tables, env=env, timeout=60)


@fac.rule
def report(
    totals: fac.Input = TOTALS,
    summary: fac.Input = SUMMARY,
    tool: fac.Input = TABLE_TOOL,
    output: fac.Output = REPORT,
    title: str = TITLE,
):
    table = fac.run(sys.executable, tool, totals, quiet=True)
    fac.write_text(output, f"{title}\n\n{table}\nTotal: {fac.read_text(summary)}")


@fac.rule(default=True)
def checksums(
    report_file: fac.Input = REPORT,
    totals: fac.Input = TOTALS,
    tool: fac.Input = CHECKSUM_TOOL,
    output: fac.Output = CHECKSUMS,
):
    fac.run(
        sys.executable,
        os.path.abspath(tool),
        os.path.basename(report_file),
        os.path.basename(totals),
        cwd=fac.out(),
        stdout=output,
    )


@fac.task
def show(path: fac.Input = REPORT):
    print(fac.read_text(path), end="")


@fac.task
def clean():
    if os.path.exists(fac.out()):
        shutil.rmtree(fac.out())
