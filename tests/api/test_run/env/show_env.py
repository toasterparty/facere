import os

names = ["FACERE_TEST_INHERITED", "FACERE_TEST_SET", "FACERE_TEST_UNSET"]
print(*(os.environ.get(name) for name in names), end="")
