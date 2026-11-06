"""Copy CSV rows from stdin to stdout, reporting each row with a bad amount on stderr instead."""

import sys

header = sys.stdin.readline()
sys.stdout.write(header)
for row in sys.stdin:
    _, _, amount = row.strip().partition(",")
    if amount.isdecimal():
        sys.stdout.write(row)
    else:
        sys.stderr.write(row)
