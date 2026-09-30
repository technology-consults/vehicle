#!/usr/bin/env python3
"""Unit tests for the gates inventory (scripts/enforce/gates.json).

Asserts every module's GATE_DEFS matches the inventory exactly, and the
inventory's module order matches the orchestrator's ENFORCE_MODULES --
so a gate can never exist in code without being inventoried, or vice
versa.

Convention: a main() printing "<N> passed, <M> failed", exit 0 on
success, 1 on failure.
"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
ENFORCE_DIR = os.path.join(REPO_ROOT, "scripts", "enforce")

_passed = 0
_failed = 0


def check(name, cond):
    global _passed, _failed
    if cond:
        _passed += 1
    else:
        _failed += 1
        print("FAIL: %s" % name)


def load(name):
    path = os.path.join(ENFORCE_DIR, name + ".py")
    spec = importlib.util.spec_from_file_location(name + "_mod", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_inventory_matches_registry():
    with open(os.path.join(ENFORCE_DIR, "gates.json"),
              encoding="utf-8") as f:
        inv = json.load(f)
    commit_spec = importlib.util.spec_from_file_location(
        "commit_mod", os.path.join(REPO_ROOT, "scripts", "commit.py"))
    commit_mod = importlib.util.module_from_spec(commit_spec)
    commit_spec.loader.exec_module(commit_mod)

    check("inventory: module order matches orchestrator",
          inv["order"] == list(commit_mod.ENFORCE_MODULES))

    for name in inv["order"]:
        mod = load(name)
        inv_gates = inv["modules"][name]["gates"]
        reg = [(g[0], g[1], g[2]) for g in mod.GATE_DEFS]
        inv_t = [(g["name"], g["description"], g["allowlist"])
                 for g in inv_gates]
        check("inventory: %s gates match registry" % name, reg == inv_t)
        for gname, _desc, allow in mod.GATE_DEFS:
            if allow is None:
                continue
            full = os.path.join(REPO_ROOT, allow)
            check("inventory: %s allowlist exists (%s)" % (gname, allow),
                  os.path.isfile(full))

    check("inventory: baseline is a positive int",
          isinstance(inv["unit_tests_baseline"], int)
          and inv["unit_tests_baseline"] > 0)

    import re as _re
    check("inventory: ruleset_version present and semver",
          isinstance(inv.get("ruleset_version"), str)
          and bool(_re.match(r"^\d+\.\d+\.\d+$",
                             inv["ruleset_version"])))


def main():
    test_inventory_matches_registry()
    print("%d passed, %d failed" % (_passed, _failed))
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
