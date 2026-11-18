import functools

import facere as fac

MARK = "!"


def logged(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)

    return wrapper


@fac.rule(default=True)
@logged
def shout(target: fac.Output = fac.out("a.txt")):
    fac.write_text(target, "hi" + MARK)
