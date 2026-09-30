#!/usr/bin/env python3
"""Unit tests for scripts/enforce/coding_standards.py.

Convention: a main() printing "<N> passed, <M> failed", exit 0 on
success, 1 on failure.

Every payload is built by string concatenation so this file's own added
lines never trip the gates it tests.
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
MOD_PATH = os.path.join(REPO_ROOT, "scripts", "enforce",
                        "coding_standards.py")

spec = importlib.util.spec_from_file_location("coding_standards_mod",
                                              MOD_PATH)
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


def mdiff(files):
    """{path: [(lineno, line), ...]} -> the module's diff dict."""
    return {"files": {p: {"is_new": False, "added": a}
                      for p, a in files.items()}}


# --- dangerous-calls ---------------------------------------------------------

def test_dangerous_eval():
    line = "x = " + "ev" + "al(" + "user_input)"
    out = mod.check_dangerous(mdiff({"scripts/a.py": [(1, line)]}),
                              REPO_ROOT, set())
    check("dangerous: eval blocked",
          len(out) == 1 and out[0][0] == "dangerous-calls")


def test_dangerous_exec():
    line = "ex" + "ec(" + "code)"
    out = mod.check_dangerous(mdiff({"scripts/a.py": [(1, line)]}),
                              REPO_ROOT, set())
    check("dangerous: exec blocked",
          len(out) == 1 and out[0][0] == "dangerous-calls")


def test_dangerous_os_system():
    line = "os." + "system(" + '"ls")'
    out = mod.check_dangerous(mdiff({"scripts/a.py": [(1, line)]}),
                              REPO_ROOT, set())
    check("dangerous: os.system blocked",
          len(out) == 1 and out[0][0] == "dangerous-calls")


def test_dangerous_shell_true():
    line = "subprocess.run(cmd, " + "shell" + " = " + "True" + ")"
    out = mod.check_dangerous(mdiff({"scripts/a.py": [(1, line)]}),
                              REPO_ROOT, set())
    check("dangerous: subprocess shell mode blocked",
          len(out) == 1 and out[0][0] == "dangerous-calls")


def test_dangerous_pickle():
    line = "pickle." + "loads(" + "data)"
    out = mod.check_dangerous(mdiff({"scripts/a.py": [(1, line)]}),
                              REPO_ROOT, set())
    check("dangerous: pickle.loads blocked",
          len(out) == 1 and out[0][0] == "dangerous-calls")


def test_dangerous_yaml_unsafe():
    line = "yaml." + "load(" + "text)"
    out = mod.check_dangerous(mdiff({"scripts/a.py": [(1, line)]}),
                              REPO_ROOT, set())
    check("dangerous: yaml.load without Loader blocked",
          len(out) == 1 and out[0][0] == "dangerous-calls")


def test_dangerous_yaml_safe_passes():
    line = "yaml." + "load(" + "text, Loader=yaml.SafeLoader)"
    out = mod.check_dangerous(mdiff({"scripts/a.py": [(1, line)]}),
                              REPO_ROOT, set())
    check("dangerous: yaml.load with Loader passes", out == [])


def test_dangerous_non_py_ignored():
    line = "x = " + "ev" + "al(" + "y)"
    out = mod.check_dangerous(mdiff({"ev-deals/index.html": [(1, line)]}),
                              REPO_ROOT, set())
    check("dangerous: non-.py files ignored", out == [])


def test_dangerous_allowlisted():
    line = "x = " + "ev" + "al(" + "y)"
    out = mod.check_dangerous(mdiff({"scripts/a.py": [(1, line)]}),
                              REPO_ROOT, {"scripts/a.py"})
    check("dangerous: allowlisted path exempt", out == [])


def test_dangerous_clean_passes():
    lines = [(1, "import subprocess"),
             (2, "subprocess.run(['ls'], check=True)"),
             (3, "json.loads(text)")]
    out = mod.check_dangerous(mdiff({"scripts/a.py": lines}),
                              REPO_ROOT, set())
    check("dangerous: clean code passes", out == [])


# --- bare-except -------------------------------------------------------------

def test_bare_except_blocked():
    line = "    " + "except" + ":"
    out = mod.check_bare_except(mdiff({"scripts/a.py": [(2, line)]}),
                                REPO_ROOT, set())
    check("bare-except: bare except blocked",
          len(out) == 1 and out[0][0] == "bare-except"
          and out[0][2] == 2)


def test_named_except_passes():
    lines = [(1, "try:"),
             (2, "    pass"),
             (3, "except ValueError:"),
             (4, "    pass"),
             (5, "except Exception as e:"),
             (6, "    pass")]
    out = mod.check_bare_except(mdiff({"scripts/a.py": lines}),
                                REPO_ROOT, set())
    check("bare-except: named excepts pass", out == [])


# --- no-cache ----------------------------------------------------------------

def test_no_cache_pycache():
    out = mod.check_no_cache(
        {"files": {"scripts/enforce/__pycache__/x.pyc":
                   {"is_new": True, "added": []}}},
        REPO_ROOT, set())
    check("no-cache: __pycache__ blocked",
          len(out) == 1 and out[0][0] == "no-cache")


def test_no_cache_ds_store():
    out = mod.check_no_cache(
        {"files": {".DS_Store": {"is_new": True, "added": []}}},
        REPO_ROOT, set())
    check("no-cache: .DS_Store blocked (case-insensitive)",
          len(out) == 1 and out[0][0] == "no-cache")


def test_no_cache_clean_passes():
    out = mod.check_no_cache(
        {"files": {"scripts/a.py": {"is_new": True, "added": []}}},
        REPO_ROOT, set())
    check("no-cache: clean diff passes", out == [])


# --- tests-with-code ---------------------------------------------------------

def test_tests_with_code_flagged():
    line = "def " + "new_feature():"
    out = mod.check_tests_with_code(
        mdiff({"scripts/new_tool.py": [(1, line)]}), REPO_ROOT, set())
    check("tests-with-code: new def without test flagged",
          len(out) == 1 and out[0][0] == "tests-with-code")


def test_tests_with_code_src_dir():
    line = "class " + "NewThing:"
    out = mod.check_tests_with_code(
        mdiff({"src/crons/job/run.py": [(1, line)]}), REPO_ROOT, set())
    check("tests-with-code: src/ is a code dir",
          len(out) == 1 and out[0][0] == "tests-with-code")


def test_tests_with_code_html_not_code():
    line = "<div>"  # not a def/class line anyway
    out = mod.check_tests_with_code(
        mdiff({"ev-deals/index.html": [(1, line)]}), REPO_ROOT, set())
    check("tests-with-code: html never triggers", out == [])


def test_tests_with_code_satisfied_by_test_file():
    line = "def " + "new_feature():"
    out = mod.check_tests_with_code(
        mdiff({"scripts/new_tool.py": [(1, line)],
               "scripts/tests/unit/test_new_tool.py": [(1, "x")]}),
        REPO_ROOT, set())
    check("tests-with-code: test file in diff satisfies", out == [])


def test_tests_with_code_test_files_exempt():
    line = "def " + "helper():"
    out = mod.check_tests_with_code(
        mdiff({"scripts/tests/unit/test_x.py": [(1, line)]}),
        REPO_ROOT, set())
    check("tests-with-code: test files never trigger", out == [])


# --- gate registry sanity ----------------------------------------------------

def test_gate_defs_documented():
    names = [g[0] for g in mod.GATE_DEFS]
    check("registry: five coding gates",
          names == ["py-compile", "dangerous-calls", "bare-except",
                    "no-cache", "tests-with-code"])
    check("registry: every gate has a check function",
          all(n in mod._CHECKS for n in names))


def main():
    test_dangerous_eval()
    test_dangerous_exec()
    test_dangerous_os_system()
    test_dangerous_shell_true()
    test_dangerous_pickle()
    test_dangerous_yaml_unsafe()
    test_dangerous_yaml_safe_passes()
    test_dangerous_non_py_ignored()
    test_dangerous_allowlisted()
    test_dangerous_clean_passes()
    test_bare_except_blocked()
    test_named_except_passes()
    test_no_cache_pycache()
    test_no_cache_ds_store()
    test_no_cache_clean_passes()
    test_tests_with_code_flagged()
    test_tests_with_code_src_dir()
    test_tests_with_code_html_not_code()
    test_tests_with_code_satisfied_by_test_file()
    test_tests_with_code_test_files_exempt()
    test_gate_defs_documented()
    print("%d passed, %d failed" % (_passed, _failed))
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
