import facere as fac


@fac.override(fac.c.object_file, scope="*.release")
def for_size(rule):
    rule.cflags = rule.cflags + ["-Os"]
