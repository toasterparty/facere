import os
import shutil

import facere as fac


@fac.rule(
    each=[
        {"source": "a.md", "target": fac.out("a.html")},
        {"source": "b.md", "target": fac.out("b.html")},
    ]
)
def page(source: fac.Input, target: fac.Output):
    with open(source) as file, open(target, "w") as out:
        out.write(f"<p>{file.read()}</p>")


@fac.rule(default=True)
def index(
    pages: list[fac.Input] = [fac.out("a.html"), fac.out("b.html")],
    target: fac.Output = fac.out("index.html"),
):
    with open(target, "w") as out:
        out.write(" ".join(pages))


@fac.task
def clean():
    if os.path.exists(fac.out()):
        shutil.rmtree(fac.out())


@fac.task(name="list")
def list_(index: fac.Input = fac.out("index.html")):
    print(open(index).read(), flush=True)
