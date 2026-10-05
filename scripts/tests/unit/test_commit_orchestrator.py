#!/usr/bin/env python3
"""Unit tests for the scripts/commit.py shim.

The orchestrator is now the agent toolkit's git-commit.py (reached via
the shim). This test verifies the shim resolves the toolkit and
delegates with --repo/--workdir pinned for this repo.

Convention: a main() printing "<N> passed, <M> failed", exit 0 on
success, 1 on failure.
"""
import importlib.util
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
MOD_PATH = os.path.join(REPO_ROOT, "scripts", "commit.py")

spec = importlib.util.spec_from_file_location("commit_mod", MOD_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

_passed = 0
_failed = 0


def check(name, cond):
    global _passed, _failed
    if cond:
        _passed += 1
    else:
        _failed += 1
        print("FAIL: %s" % name)


def test_resolve_toolkit():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "scripts"))
        old = os.environ.get("AGENT_TOOLS_ROOT")
        os.environ["AGENT_TOOLS_ROOT"] = d
        try:
            check("shim: AGENT_TOOLS_ROOT honored",
                  mod.resolve_toolkit_root() == d)
        finally:
            if old is None:
                del os.environ["AGENT_TOOLS_ROOT"]
            else:
                os.environ["AGENT_TOOLS_ROOT"] = old


def test_build_command_pins_repo():
    cmd = mod.build_command(["m", "p"], "/t", "/w")
    check("shim: delegates to toolkit git-commit.py",
          cmd[1] == os.path.join("/t", "scripts", "git-commit.py"))
    check("shim: --repo pinned",
          cmd[cmd.index("--repo") + 1] == "technology-consults/vehicle")


def main():
    test_resolve_toolkit()
    test_build_command_pins_repo()
    print("%d passed, %d failed" % (_passed, _failed))
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
