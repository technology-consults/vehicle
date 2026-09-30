#!/usr/bin/env python3
"""Run all enforce checks in scripts/enforce/.

Each check is a no_*.py module in this directory exposing check(files)
and runnable as a script (exit 0 = pass). This runner executes every
check as a subprocess over the same file list and fails if any check
fails.

Usage:
    python3 scripts/enforce/run_checks.py [file ...]
With no file arguments, each check scans its own default (git-tracked
files).

This is the ad-hoc whole-tree scanner. The gated commit path is
scripts/commit.py, which runs the unit tier and then the full
scripts/enforce/ gate suite (coding_standards, security,
owner_guidelines) over the commit's added lines before anything lands.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main(argv):
    files = argv[1:]
    check_scripts = sorted(
        f for f in os.listdir(HERE)
        if f.startswith("no_") and f.endswith(".py")
        and os.path.isfile(os.path.join(HERE, f)))
    if not check_scripts:
        print("run_checks: no checks found", file=sys.stderr)
        return 1
    failed = []
    for script in check_scripts:
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, script)] + files,
            capture_output=True, text=True)
        sys.stdout.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        if proc.returncode != 0:
            failed.append(script)
    if failed:
        print("run_checks: FAILED (%s)" % ", ".join(failed),
              file=sys.stderr)
        return 1
    print("run_checks: all %d check(s) passed" % len(check_scripts))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
