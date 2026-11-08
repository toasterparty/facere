"""A stand-in for a flashing tool: it copies the program to the file its port names."""

import argparse
import shutil

parser = argparse.ArgumentParser()
parser.add_argument("program")
parser.add_argument("-p", "--port", required=True)
options = parser.parse_args()
shutil.copy2(options.program, options.port)
print(f"flashed {options.port}")
