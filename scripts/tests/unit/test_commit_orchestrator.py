#!/usr/bin/env python3
"""Unit tests for the scripts/commit.py orchestrator.

Verifies the pipeline contract with the mutating API calls stubbed out:
  unit tier first -> enforcement modules in fixed order ->
  abort before ANY mutating Trees API call on any failure.

Convention: a main() printing "<N> passed, <M> failed", exit 0 on
success, 1 on failure.
"""
import importlib.util
import os
import sys

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


class FakeCompleted:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


_saved = {}


def setup(monkey_unit=True, module_rc=0, module_stdout=""):
    """Stub unit tier, subprocess, and the GitHub API. Returns recorders."""
    import subprocess as _sp
    calls = {"unit": 0, "modules": [], "api": []}
    _saved["run_unit_tier"] = mod.run_unit_tier
    _saved["subprocess_run"] = _sp.run
    _saved["api"] = mod.api
    _saved["build_diff_payload"] = mod.build_diff_payload

    def fake_unit():
        calls["unit"] += 1
        return monkey_unit

    def fake_run(cmd, **kwargs):
        # cmd: [python, scripts/enforce/<name>.py, repo_root]
        name = os.path.basename(cmd[1]).replace(".py", "")
        calls["modules"].append(name)
        return FakeCompleted(returncode=module_rc, stdout=module_stdout)

    def fake_api(method, path, body=None):
        calls["api"].append((method, path))
        if path.endswith("/git/ref/heads/main"):
            return {"object": {"sha": "base"}}
        if "/git/commits/base" in path:
            return {"tree": {"sha": "basetree"}}
        if path.endswith("/git/blobs"):
            return {"sha": "blobsha"}
        if path.endswith("/git/trees"):
            # record the tree entries for the deletion test
            calls["tree"] = body["tree"]
            return {"sha": "newtree"}
        if path.endswith("/git/commits"):
            return {"sha": "newcommit"}
        if path.endswith("/git/refs/heads/main"):
            return {}
        raise AssertionError("unexpected api call: %s %s" % (method, path))

    mod.run_unit_tier = fake_unit
    mod.subprocess.run = fake_run
    mod.api = fake_api
    # diff computation needs file reads; point at an empty payload
    mod.build_diff_payload = lambda paths: {"files": {}}
    return calls


def teardown():
    import subprocess as _sp
    mod.run_unit_tier = _saved["run_unit_tier"]
    _sp.run = _saved["subprocess_run"]
    mod.api = _saved["api"]
    mod.build_diff_payload = _saved["build_diff_payload"]


def test_happy_path_runs_everything_in_order():
    calls = setup()
    try:
        rc = mod.main(["commit.py", "msg", "scripts/commit.py"])
    finally:
        teardown()
    check("orchestrator: clean commit returns 0", rc == 0)
    check("orchestrator: unit tier ran", calls["unit"] == 1)
    check("orchestrator: modules ran in fixed order",
          calls["modules"] == ["coding_standards", "security",
                               "owner_guidelines"])
    check("orchestrator: mutating API calls happened only after gates",
          len(calls["api"]) > 0)


def test_unit_failure_aborts_before_enforcement():
    calls = setup(monkey_unit=False)
    try:
        rc = mod.main(["commit.py", "msg", "scripts/commit.py"])
    finally:
        teardown()
    check("orchestrator: unit failure returns non-zero", rc != 0)
    check("orchestrator: no enforcement modules ran",
          calls["modules"] == [])
    check("orchestrator: no API calls at all", calls["api"] == [])


def test_violation_aborts_before_mutation():
    blocked = "BLOCKED [secrets] scripts/a.py:1: x\n"
    calls = setup(module_rc=1, module_stdout=blocked)
    try:
        rc = mod.main(["commit.py", "msg", "scripts/commit.py"])
    finally:
        teardown()
    check("orchestrator: violation returns non-zero", rc != 0)
    check("orchestrator: no mutating API calls", calls["api"] == [])


def test_all_modules_run_despite_early_failure():
    # First module reports a violation; the rest must still run so the
    # author fixes everything in one round.
    blocked = "BLOCKED [py-compile] scripts/a.py:0: bad\n"
    calls = setup(module_rc=1, module_stdout=blocked)
    try:
        mod.main(["commit.py", "msg", "scripts/commit.py"])
    finally:
        teardown()
    check("orchestrator: all modules ran despite first failing",
          calls["modules"] == ["coding_standards", "security",
                               "owner_guidelines"])


def test_module_crash_fails_closed():
    calls = setup(module_rc=2, module_stdout="")
    try:
        rc = mod.main(["commit.py", "msg", "scripts/commit.py"])
    finally:
        teardown()
    check("orchestrator: module crash returns non-zero", rc != 0)
    check("orchestrator: crash -> no mutating API calls",
          calls["api"] == [])


def test_missing_local_file_with_remote_is_deletion():
    calls = setup()
    _saved["remote_text"] = mod.remote_text
    mod.remote_text = lambda p: "old content"  # exists remotely
    try:
        rc = mod.main(["commit.py", "msg", "scripts/tests/unit/gone.py"])
    finally:
        mod.remote_text = _saved["remote_text"]
        teardown()
    check("orchestrator: deletion commit returns 0", rc == 0)
    entries = calls.get("tree", [])
    check("orchestrator: deletion uses sha null",
          entries == [{"path": "scripts/tests/unit/gone.py", "mode": "100644",
                       "type": "blob", "sha": None}])


def test_missing_everywhere_is_error():
    calls = setup()
    _saved["remote_text"] = mod.remote_text
    mod.remote_text = lambda p: None
    try:
        rc = mod.main(["commit.py", "msg", "scripts/tests/unit/gone.py"])
    finally:
        mod.remote_text = _saved["remote_text"]
        teardown()
    check("orchestrator: unknown path returns non-zero", rc != 0)
    check("orchestrator: unknown path -> no API calls", calls["api"] == [])


def test_enforcement_real_modules_clean():
    # Regression test for the bytes/str subprocess wiring: run the REAL
    # modules as subprocesses (only the diff is stubbed).
    calls = setup()
    import subprocess as _sp
    _sp.run = _saved["subprocess_run"]  # real subprocess.run
    mod.build_diff_payload = lambda paths: {
        "files": {"scripts/a.py": {"is_new": True, "added": [(1, "X = 1")]}}}
    try:
        v = mod.run_enforcement(["scripts/a.py"])
    finally:
        teardown()
    check("orchestrator: real modules run clean on a clean diff", v == [])
    check("orchestrator: no API calls during enforcement", calls["api"] == [])


def test_enforcement_real_modules_block():
    calls = setup()
    import subprocess as _sp
    _sp.run = _saved["subprocess_run"]  # real subprocess.run
    bad_line = "x = " + "ev" + "al(" + "y)"
    mod.build_diff_payload = lambda paths: {
        "files": {"scripts/a.py": {"is_new": True,
                                   "added": [(1, bad_line)]}}}
    try:
        v = mod.run_enforcement(["scripts/a.py"])
    finally:
        teardown()
    check("orchestrator: real modules report violations",
          len(v) == 1 and v[0][0] == "dangerous-calls"
          and v[0][1] == "scripts/a.py" and v[0][2] == 1)


def test_enforcement_real_modules_raw_github():
    # The owner-guidelines gate must reuse the repo's own raw-URL checker.
    calls = setup()
    import subprocess as _sp
    _sp.run = _saved["subprocess_run"]  # real subprocess.run
    banned = "raw." + "githubusercontent.com"
    bad_line = "u = " + chr(34) + "https://" + banned + "/o/r/main/f" \
        + chr(34)
    mod.build_diff_payload = lambda paths: {
        "files": {"scripts/a.py": {"is_new": True,
                                   "added": [(1, bad_line)]}}}
    try:
        v = mod.run_enforcement(["scripts/a.py"])
    finally:
        teardown()
    check("orchestrator: real modules flag the raw-file CDN URL",
          len(v) == 1 and v[0][0] == "no-raw-github"
          and "api.github.com" in v[0][3])
    check("orchestrator: raw-url check made no API calls",
          calls["api"] == [])


def main():
    test_happy_path_runs_everything_in_order()
    test_unit_failure_aborts_before_enforcement()
    test_violation_aborts_before_mutation()
    test_all_modules_run_despite_early_failure()
    test_module_crash_fails_closed()
    test_missing_local_file_with_remote_is_deletion()
    test_missing_everywhere_is_error()
    test_enforcement_real_modules_clean()
    test_enforcement_real_modules_block()
    test_enforcement_real_modules_raw_github()
    print("%d passed, %d failed" % (_passed, _failed))
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
