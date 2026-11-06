"""Print the CSV file named on the command line as an aligned table."""

import sys

with open(sys.argv[1], encoding="utf-8") as file:
    rows = [line.strip().split(",") for line in file]
width = max(len(item) for item, _ in rows)
for item, amount in rows:
    print(f"{item:<{width}}  {amount:>6}")
