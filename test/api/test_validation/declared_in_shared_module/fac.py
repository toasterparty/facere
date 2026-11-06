import tools.tasks  # noqa: F401 - the import declares the task

import facere as fac


@fac.task(default=True)
def nothing():
    pass
