import facere as fac


@fac.override(fac.c.object_file, match="*.release")
def for_size(rule):
    rule.cflags = rule.cflags + ["-Os"]
