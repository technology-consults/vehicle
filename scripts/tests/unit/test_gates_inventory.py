#!/usr/bin/env python3
"""Unit tests for the gates inventory (scripts/enforce/gates.json).

The commit orchestrator is now the agent toolkit's git-commit.py, reached
via the scripts/commit.py shim. This test asserts every local module's
GATE_DEFS matches the inventory exactly, and that the shim delegates to
the toolkit.

Convention: a main() printing "<N> passed, <M> failed", exit 0 on
success, 1 on failure.
"""
import importlib.util
import json
import os
import re as _re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
ENFORCE_DIR = os.path.join(REPO_ROOT, "scripts", "enforce")
SHIM_PATH = os.path.join(REPO_ROOT, "scripts", "commit.py")

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


def try_load(name):
    try:
        return load(name)
    except SystemExit:
        return None
    except Exception:
        return None


def modules_with_gate_defs():
    out = []
    for fn in sorted(os.listdir(ENFORCE_DIR)):
        if not fn.endswith(".py"):
            continue
        name = fn[:-3]
        mod = try_load(name)
        if mod is not None and hasattr(mod, "GATE_DEFS"):
            out.append(name)
    return out


def test_inventory_matches_code():
    with open(os.path.join(ENFORCE_DIR, "gates.json"),
              encoding="utf-8") as f:
        inv = json.load(f)
    local = modules_with_gate_defs()
    check("inventory: every local gate module is inventoried",
          set(local) == set(inv["modules"].keys()))
    for name in inv["modules"].keys():
        mod = load(name)
        inv_gates = inv["modules"][name]["gates"]
        reg = [(g[0], g[1], g[2]) for g in mod.GATE_DEFS]
        inv_t = [(g["name"], g["description"], g["allowlist"])
                 for g in inv_gates]
        check("inventory: %s gates match code" % name, reg == inv_t)
    check("inventory: ruleset_version present and semver",
          isinstance(inv.get("ruleset_version"), str)
          and bool(_re.match(r"^\d+\.\d+\.\d+$",
                             inv["ruleset_version"])))


def test_shim_delegates():
    spec = importlib.util.spec_from_file_location("commit_mod", SHIM_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cmd = mod.build_command(["m", "p"], "/t", "/w")
    check("shim: delegates to toolkit",
          cmd[1] == os.path.join("/t", "scripts", "git-commit.py"))


def main():
    test_inventory_matches_code()
    test_shim_delegates()
    print("%d passed, %d failed" % (_passed, _failed))
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
