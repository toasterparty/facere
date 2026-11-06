import os

import facere as fac

ROOT_AT_COLLECTION = os.getcwd()


@fac.task(default=True)
def where():
    print(os.getcwd() == ROOT_AT_COLLECTION, os.path.basename(os.getcwd()), flush=True)
