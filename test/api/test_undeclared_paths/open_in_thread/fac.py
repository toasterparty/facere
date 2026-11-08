import threading

import facere as fac


@fac.rule(default=True)
def use(result: fac.Output = fac.out("result.txt")):
    thread = threading.Thread(target=fac.read_text, args=("tool.cfg",))
    thread.start()
    thread.join()
    fac.write_text(result, "done")
