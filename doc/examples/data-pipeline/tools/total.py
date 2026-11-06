"""Usage: total.py OUT_CSV OUT_TXT CSV... Total each item across the CSV files, writing the totals to OUT_CSV and their sum, in the currency REPORT_CURRENCY names, to OUT_TXT."""

import os
import sys

out_csv, out_txt, *paths = sys.argv[1:]
totals = {}
for path in paths:
    with open(path, encoding="utf-8") as file:
        next(file)
        for row in file:
            item, _, amount = row.strip().partition(",")
            totals[item] = totals.get(item, 0) + int(amount)

with open(out_csv, "w", encoding="utf-8", newline="\n") as file:
    file.writelines(f"{item},{totals[item]}\n" for item in sorted(totals))
with open(out_txt, "w", encoding="utf-8", newline="\n") as file:
    file.write(f"{sum(totals.values())} {os.environ['REPORT_CURRENCY']}\n")
