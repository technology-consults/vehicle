#!/usr/bin/env python3
"""Unit tests for scripts/enforce/security.py.

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
MOD_PATH = os.path.join(REPO_ROOT, "scripts", "enforce", "security.py")

spec = importlib.util.spec_from_file_location("security_mod", MOD_PATH)
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


# --- secrets -----------------------------------------------------------------

def test_secrets_aws_key():
    line = "key = " + '"AKIA' + "IOSFODNN7EXAMPLE" + '"'
    out = mod.check_secrets(mdiff({"scripts/a.py": [(1, line)]}),
                            REPO_ROOT, set())
    check("secrets: AWS key ID blocked",
          len(out) == 1 and out[0][0] == "secrets")


def test_secrets_private_key():
    line = "-----BEGIN " + "PRIVATE KEY-----"
    out = mod.check_secrets(mdiff({"scripts/a.py": [(1, line)]}),
                            REPO_ROOT, set())
    check("secrets: PEM header blocked",
          len(out) == 1 and out[0][0] == "secrets")


def test_secrets_rsa_key():
    line = "-----BEGIN " + "RSA PRIVATE KEY-----"
    out = mod.check_secrets(mdiff({"scripts/a.py": [(1, line)]}),
                            REPO_ROOT, set())
    check("secrets: RSA PEM header blocked",
          len(out) == 1 and out[0][0] == "secrets")


def test_secrets_assignment():
    q = chr(39)
    line = "api_" + "key = " + q + "sk-live-abc123xyz" + q
    out = mod.check_secrets(mdiff({"scripts/a.py": [(1, line)]}),
                            REPO_ROOT, set())
    check("secrets: credential assignment blocked",
          len(out) == 1 and out[0][0] == "secrets")


def test_secrets_case_insensitive():
    q = chr(34)
    line = "API_" + "KEY: " + q + "sk-live-abc123xyz" + q
    out = mod.check_secrets(mdiff({"scripts/a.py": [(1, line)]}),
                            REPO_ROOT, set())
    check("secrets: case-insensitive assignment blocked",
          len(out) == 1 and out[0][0] == "secrets")


def test_secrets_no_false_positives():
    lines = [(1, "def tokenize(text):"),
             (2, "token = None"),
             (3, 'api_key = os.environ.get("API_KEY")'),
             (4, 'password = ""'),
             (5, "# the secret sauce is hard work")]
    out = mod.check_secrets(mdiff({"scripts/a.py": lines}),
                            REPO_ROOT, set())
    check("secrets: ordinary code passes", out == [])


def test_secrets_any_file_type():
    q = chr(39)
    line = "pw: " + "pass" + "word" + " = " + q + "hunter2hunter2" + q
    out = mod.check_secrets(mdiff({"ev-deals/index.html": [(1, line)]}),
                            REPO_ROOT, set())
    check("secrets: scans every file type, not just .py",
          len(out) == 1 and out[0][0] == "secrets")


# --- token-in-log ------------------------------------------------------------

def test_token_in_log_fstring():
    line = 'print(f"' + "tok" + "en={api_" + "token}" + '")'
    out = mod.check_token_in_log(mdiff({"scripts/a.py": [(1, line)]}),
                                 REPO_ROOT, set())
    check("token-in-log: f-string credential interpolation blocked",
          len(out) == 1 and out[0][0] == "token-in-log")


def test_token_in_log_direct_var():
    line = "logger.info(" + "api_" + "key" + ")"
    out = mod.check_token_in_log(mdiff({"scripts/a.py": [(1, line)]}),
                                 REPO_ROOT, set())
    check("token-in-log: credential variable passed to logger blocked",
          len(out) == 1 and out[0][0] == "token-in-log")


def test_token_in_log_label_passes():
    lines = [(1, 'print("token expired, refreshing")'),
             (2, 'logger.info("api_key loaded from env")')]
    out = mod.check_token_in_log(mdiff({"scripts/a.py": lines}),
                                 REPO_ROOT, set())
    check("token-in-log: mere word mentions pass", out == [])


def test_token_in_log_non_py_ignored():
    line = "print(" + "api_" + "key" + ")"
    out = mod.check_token_in_log(mdiff({"notes.txt": [(1, line)]}),
                                 REPO_ROOT, set())
    check("token-in-log: non-.py files ignored", out == [])


def test_token_in_log_allowlisted():
    line = 'print(f"{' + "sec" + "ret})"
    out = mod.check_token_in_log(mdiff({"scripts/a.py": [(1, line)]}),
                                 REPO_ROOT, {"scripts/a.py"})
    check("token-in-log: allowlisted path exempt", out == [])


# --- gate registry sanity ----------------------------------------------------

def test_gate_defs_documented():
    names = [g[0] for g in mod.GATE_DEFS]
    check("registry: two security gates",
          names == ["secrets", "token-in-log"])
    check("registry: secrets has no allowlist (never legitimate)",
          mod.GATE_DEFS[0][2] is None)
    check("registry: every gate has a check function",
          all(n in mod._CHECKS for n in names))


def main():
    test_secrets_aws_key()
    test_secrets_private_key()
    test_secrets_rsa_key()
    test_secrets_assignment()
    test_secrets_case_insensitive()
    test_secrets_no_false_positives()
    test_secrets_any_file_type()
    test_token_in_log_fstring()
    test_token_in_log_direct_var()
    test_token_in_log_label_passes()
    test_token_in_log_non_py_ignored()
    test_token_in_log_allowlisted()
    test_gate_defs_documented()
    print("%d passed, %d failed" % (_passed, _failed))
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
