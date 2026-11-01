import sys

print("out")
print("err", file=sys.stderr)
sys.exit(int(sys.argv[1]))
