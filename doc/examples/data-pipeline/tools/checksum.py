"""Print the SHA-256 of each file named on the command line."""

import hashlib
import sys

for path in sys.argv[1:]:
    with open(path, "rb") as file:
        print(f"{hashlib.sha256(file.read()).hexdigest()}  {path}")
