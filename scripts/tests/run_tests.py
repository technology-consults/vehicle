#!/usr/bin/env python3
"""Unit-tier test runner for the vehicle repo.

Runs every unit test file in the repo, in a fixed discovery order:

    scripts/enforce/tests/test_*.py   (gate-module tests, unittest style)
    scripts/tests/unit/test_*.py      (gate-registry + orchestrator tests)
    src/crons/*/tests/test_*.py      (versioned cron job package tests)

Usage:
    python3 scripts/tests/run_tests.py [--tier unit]

Only the unit tier exists today; functional/regression coverage lives
inside the cron job packages' own suites when they define it.

Each test file is run as its own subprocess with the repo root as the
working directory. Two file conventions are supported and both are
trusted by exit code first:
  - check() style: a main() printing "<N> passed, <M> failed", exit 0/1.
  - unittest style: unittest.main(), exit 0/1 (the "Ran N tests / OK"
    lines are parsed for the summary count).

Exit 0 only when every file passes. Stdlib only.
"""
import argparse
import glob
import os
import re
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

COUNTS_RE = re.compile(r"(\d+)\s+passed,\s+(\d+)\s+failed")
UNITTEST_RAN_RE = re.compile(r"^Ran (\d+) tests?", re.MULTILINE)


def discover():
    """Test files in fixed order."""
    found = []
    found.extend(sorted(glob.glob(os.path.join(
        REPO_ROOT, "scripts", "enforce", "tests", "test_*.py"))))
    found.extend(sorted(glob.glob(os.path.join(
        REPO_ROOT, "scripts", "tests", "unit", "test_*.py"))))
    for job_dir in sorted(glob.glob(os.path.join(
            REPO_ROOT, "src", "crons", "*", "tests"))):
        found.extend(sorted(glob.glob(os.path.join(job_dir,
                                                   "test_*.py"))))
    return found


def run_one(path):
    """Run one test file. Return (ok, passed_checks, failed_checks, tail)."""
    try:
        r = subprocess.run(
            [sys.executable, path],
            capture_output=True, text=True, timeout=600, cwd=REPO_ROOT)
    except subprocess.TimeoutExpired:
        return False, 0, 0, "TIMEOUT after 600s"
    except Exception as e:  # noqa: BLE001 -- report, don't crash the suite
        return False, 0, 0, "RUNNER ERROR: %s" % e
    passed, failed = 0, 0
    for line in r.stdout.splitlines():
        m = COUNTS_RE.search(line)
        if m:
            passed += int(m.group(1))
            failed += int(m.group(2))
    if passed == 0 and failed == 0:
        # unittest style: count "Ran N tests" when the file passed.
        m = UNITTEST_RAN_RE.search(r.stdout + r.stderr)
        if m and r.returncode == 0:
            passed = int(m.group(1))
        elif r.returncode != 0:
            failed = 1  # at least one failure, exact count unknown
    tail = "\n".join((r.stdout + r.stderr).splitlines()[-6:])
    return r.returncode == 0, passed, failed, tail


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", default="unit",
                    choices=("unit",),
                    help="only the unit tier exists in this repo")
    ap.parse_args(argv)
    files = discover()
    if not files:
        print("run_tests: no unit test files found", file=sys.stderr)
        return 1
    total_p, total_f, bad = 0, 0, []
    for path in files:
        rel = os.path.relpath(path, REPO_ROOT)
        ok, p, f, tail = run_one(path)
        total_p += p
        total_f += f
        status = "PASS" if ok else "FAIL"
        print("[%s] %s (%d passed, %d failed)" % (status, rel, p, f))
        if not ok:
            bad.append(rel)
            print("---- tail of %s ----" % rel)
            print(tail)
            print("---- end tail ----")
    print("unit tier: %d file(s), %d check(s) passed, %d failed"
          % (len(files), total_p, total_f))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
