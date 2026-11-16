import os
import time

import facere as fac

HEADER = fac.out("x.h")


def wait_for(path):
    deadline = time.monotonic() + 30
    while not os.path.exists(path):
        assert time.monotonic() < deadline, f"{path} never appeared"
        time.sleep(0.005)


@fac.rule
def header(target: fac.Output = HEADER):
    fac.write_text(target, "one")


# Reports the header only once `reader`, which checks it as it starts, has come and gone.
@fac.rule
def reporter(header_file: fac.OrderOnly = HEADER, target: fac.Output = fac.out("reporter.txt")):
    open(fac.out("reporter.started"), "w").close()
    wait_for(fac.out("reader.txt"))
    fac.add_inputs([header_file])
    fac.write_text(target, fac.read_text(header_file))


# Changes another rule's output and changes it back, until its timestamps show it.
@fac.rule
def vandal(header_file: fac.OrderOnly = HEADER, target: fac.Output = fac.out("vandal.txt")):
    wait_for(fac.out("reporter.started"))
    before = os.stat(header_file).st_mtime_ns
    while os.stat(header_file).st_mtime_ns == before:
        fac.write_text(header_file, "two")
        fac.write_text(header_file, "one")
    fac.write_text(target, "done")


@fac.rule
def reader(
    header_file: fac.Input = HEADER,
    vandal_file: fac.Input = fac.out("vandal.txt"),
    target: fac.Output = fac.out("reader.txt"),
):
    fac.write_text(target, fac.read_text(header_file))
