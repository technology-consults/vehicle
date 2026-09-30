#!/usr/bin/env python3
"""Version pinning for the enforced ruleset (scripts/enforce/).

The enforced ruleset is the ENTIRE scripts/enforce/ directory: the gate
modules, gates.json, remediation.py, the README, and the allowlists. It
carries a version (gates.json "ruleset_version"), and every version pins
the sha256 content hash of the whole directory. scripts/commit.py
refuses to run unless the version is present and well-formed, and this
test fails unless the live content matches the pinned hash -- so the
version the owner discussed and agreed is exactly the version that
enforces every commit. A unilateral rule edit without re-pinning fails
this test and blocks the commit (fail closed).

AGREED-CHANGE RITUAL (after discussion and agreement, in ONE commit):
  1. Make the rule change under scripts/enforce/.
  2. Bump "ruleset_version" in scripts/enforce/gates.json (semver).
  3. Recompute the hash from the repo root:
       python3 -c "import sys; sys.path.insert(0,'scripts/tests/unit'); \
from test_ruleset_version import ruleset_hash; print(ruleset_hash())"
  4. Pin it: add RULESET_HASHES["<new version>"] = "<new hash>" below,
     and update RULESET_VERSION.
The hash assertion prints the actual hash on failure to make step 3 easy.

Convention: a main() printing "<N> passed, <M> failed", exit 0 on
success, 1 on failure.
"""
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
ENFORCE_DIR = os.path.join(REPO_ROOT, "scripts", "enforce")

RULESET_VERSION = "1.0.0"
RULESET_HASHES = {
    "1.0.0": "c4f1eae2208566fd1dd5db4ed1c6a1b1de42a51cc76cf6222e60b7eae5ab26bc",
}

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")

_passed = 0
_failed = 0


def check(name, cond, detail=""):
    global _passed, _failed
    if cond:
        _passed += 1
    else:
        _failed += 1
        print("FAIL: %s" % name)
        if detail:
            print("      %s" % detail)


def ruleset_hash(enforce_dir=ENFORCE_DIR):
    """sha256 over every file under scripts/enforce/ (excluding
    __pycache__): each entry feeds relpath + NUL + raw bytes into one
    hasher, entries sorted by relpath."""
    h = hashlib.sha256()
    entries = []
    for root, dirs, files in os.walk(enforce_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, enforce_dir)
            if "__pycache__" in rel.split(os.sep):
                continue
            entries.append((rel, full))
    for rel, full in sorted(entries):
        with open(full, "rb") as fh:
            data = fh.read()
        h.update(rel.encode("utf-8") + b"\0" + data)
    return h.hexdigest()


def load_inventory():
    with open(os.path.join(ENFORCE_DIR, "gates.json"),
              encoding="utf-8") as f:
        return json.load(f)


def test_version_matches_inventory():
    inv = load_inventory()
    check("ruleset: version constant matches gates.json",
          inv.get("ruleset_version") == RULESET_VERSION,
          "gates.json=%r constant=%r" % (inv.get("ruleset_version"),
                                         RULESET_VERSION))


def test_version_is_semver():
    check("ruleset: version is semver", bool(SEMVER.match(RULESET_VERSION)),
          "version=%r" % RULESET_VERSION)
    for v in RULESET_HASHES:
        check("ruleset: pinned version %r is semver" % v,
              bool(SEMVER.match(v)))


def test_version_has_pin():
    check("ruleset: current version has a hash pin",
          RULESET_VERSION in RULESET_HASHES and
          RULESET_HASHES[RULESET_VERSION] != "__PIN_AFTER_EDITS__")


def test_hash_pin_matches():
    inv = load_inventory()
    version = inv.get("ruleset_version")
    actual = ruleset_hash()
    expected = RULESET_HASHES.get(version)
    detail = ("If you just made an AGREED rule change: bump "
              "ruleset_version, recompute with:\n"
              "      python3 -c \"import sys; "
              "sys.path.insert(0,'scripts/tests/unit'); "
              "from test_ruleset_version import ruleset_hash; "
              "print(ruleset_hash())\"\n"
              "      expected=%r\n"
              "      actual  =%r" % (expected, actual))
    check("ruleset: content hash matches pin for v%s" % version,
          expected is not None and actual == expected, detail)


def main():
    test_version_matches_inventory()
    test_version_is_semver()
    test_version_has_pin()
    test_hash_pin_matches()
    print("%d passed, %d failed" % (_passed, _failed))
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
