#!/usr/bin/env python3
"""Unit tests for scripts/commit.py (the toolkit shim).

Tests the shim's path resolution and delegation logic -- no network,
no real commits.

Convention: a main() printing "<N> passed, <M> failed", exit 0 on
success, 1 on failure.
"""
import importlib.util
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
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


def test_env_var_wins():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "scripts"))
        old = os.environ.get("AGENT_TOOLS_ROOT")
        os.environ["AGENT_TOOLS_ROOT"] = d
        try:
            check("shim: AGENT_TOOLS_ROOT is honored when valid",
                  mod.resolve_toolkit_root() == d)
        finally:
            if old is None:
                del os.environ["AGENT_TOOLS_ROOT"]
            else:
                os.environ["AGENT_TOOLS_ROOT"] = old


def test_env_var_missing_scripts_fails_clearly():
    with tempfile.TemporaryDirectory() as d:
        old = os.environ.get("AGENT_TOOLS_ROOT")
        os.environ["AGENT_TOOLS_ROOT"] = d
        try:
            try:
                mod.resolve_toolkit_root()
                exited = False
                msg = ""
            except SystemExit as e:
                exited = True
                msg = str(e)
        finally:
            if old is None:
                del os.environ["AGENT_TOOLS_ROOT"]
            else:
                os.environ["AGENT_TOOLS_ROOT"] = old
        check("shim: bad AGENT_TOOLS_ROOT exits", exited)
        check("shim: error names AGENT_TOOLS_ROOT",
              "AGENT_TOOLS_ROOT" in msg)


def test_default_resolves_on_this_machine():
    old = os.environ.pop("AGENT_TOOLS_ROOT", None)
    try:
        root = mod.resolve_toolkit_root()
    finally:
        if old is not None:
            os.environ["AGENT_TOOLS_ROOT"] = old
    check("shim: default toolkit root resolves here",
          os.path.isfile(os.path.join(root, "scripts", "git-commit.py")))


def test_build_command():
    cmd = mod.build_command(["msg", "a/b.md"], "/toolkit", "/workdir")
    check("shim: delegates to the toolkit's git-commit.py",
          cmd[1] == os.path.join("/toolkit", "scripts", "git-commit.py"))
    check("shim: --repo is pinned to this repo",
          "--repo" in cmd and
          cmd[cmd.index("--repo") + 1] ==
          "technology-consults/vehicle")
    check("shim: --workdir is passed",
          "--workdir" in cmd and
          cmd[cmd.index("--workdir") + 1] == "/workdir")
    check("shim: user args pass through untouched",
          cmd[-2:] == ["msg", "a/b.md"])


def test_shim_help_reaches_toolkit():
    r = subprocess.run([sys.executable, MOD_PATH, "--help"],
                       capture_output=True, text=True, timeout=60)
    out = r.stdout + r.stderr
    check("shim: --help exits 0", r.returncode == 0)
    check("shim: --help shows the toolkit's git-commit.py usage",
          "git-commit.py" in out and "--workdir" in out)


def main():
    test_env_var_wins()
    test_env_var_missing_scripts_fails_clearly()
    test_default_resolves_on_this_machine()
    test_build_command()
    test_shim_help_reaches_toolkit()
    print("%d passed, %d failed" % (_passed, _failed))
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
