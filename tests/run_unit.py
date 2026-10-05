#!/usr/bin/env python3
"""Unit-tier entry point for the toolkit's git-commit.py.

Runs this repo's unit tier:
  1. tests/test_shim.py -- the toolkit shim's own tests
  2. scripts/tests/run_tests.py --tier unit -- the repo's unit tests

Exit 0 = everything passes. Non-zero = failures, DO NOT COMMIT.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)


def run(cmd):
    r = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True,
                       timeout=600)
    print(r.stdout, end="")
    if r.stderr:
        print(r.stderr, end="", file=sys.stderr)
    return r.returncode == 0


def main():
    ok = True
    print("unit: tests/test_shim.py ...")
    if not run([sys.executable, os.path.join(HERE, "test_shim.py")]):
        print("unit: test_shim.py FAILED")
        ok = False
    print("unit: scripts/tests/run_tests.py --tier unit ...")
    if not run([sys.executable,
                os.path.join(REPO_ROOT, "scripts", "tests", "run_tests.py"),
                "--tier", "unit"]):
        print("unit: repo unit tier FAILED")
        ok = False
    print("unit tier: %s" % ("GREEN" if ok else "RED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
