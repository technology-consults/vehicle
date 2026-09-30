#!/usr/bin/env python3
"""Pre-commit code-quality gates for the vehicle repo.

Reads a diff on stdin as JSON:
    {"files": {"<repo-rel path>": {"is_new": bool,
                                   "added": [[lineno, line], ...]}}}
argv[1] is the repo root (used to read working-tree files for the
byte-compile gate).

Prints one line per violation:
    BLOCKED [<gate>] <path>:<lineno>: <snippet>
Exit 0 when clean, 1 on violations, 2 on usage/internal error.

Gates are documented on GATE_DEFS below; scripts/enforce/gates.json
mirrors that registry and a unit test enforces the match. Stdlib only.

Each gate's deliberate-act escape is its allowlist file
(scripts/enforce/allowlist_<name>.txt). Entries are exact repo-relative
paths or directory prefixes ending in "/". A missing allowlist file
fails closed (exempts nothing).
"""
import json
import os
import re
import sys

# ---------------------------------------------------------------------------
# Gate registry: (name, one-line description, allowlist relpath or None).
# Keep descriptions free of trigger literals (see the gates themselves).
# ---------------------------------------------------------------------------
GATE_DEFS = [
    ("py-compile",
     "every committed .py file must byte-compile",
     None),
    ("dangerous-calls",
     "no eval/exec calls, os.system, subprocess shell mode, "
     "pickle deserialization, or unsafe yaml loading in added lines",
     "scripts/enforce/allowlist_dangerous.txt"),
    ("bare-except",
     "no bare except clauses in added Python lines (name the exception)",
     "scripts/enforce/allowlist_style.txt"),
    ("no-cache",
     "no __pycache__ / .pyc / .pyo / .DS_Store paths in the diff",
     "scripts/enforce/allowlist_cache.txt"),
    ("tests-with-code",
     "new def/class in code dirs needs a test file in the same diff",
     "scripts/enforce/allowlist_notests.txt"),
]

ENFORCE_DIR = os.path.dirname(os.path.abspath(__file__))

# Dangerous-call patterns over added .py lines. Each pattern's source text
# carries a literal backslash right after the keyword, so the pattern can
# never match the line that defines it.
_DANGEROUS = [
    re.compile(r"\beval\s*\("),
    re.compile(r"\bexec\s*\("),
    re.compile(r"\bos\.system\s*\("),
    re.compile(r"shell\s*=\s*True"),
    re.compile(r"\bpickle\.loads?\s*\("),
]

_BARE_EXCEPT = re.compile(r"^\s*except\s*:")
_NEW_DEF = re.compile(r"^\s*(?:async\s+)?def\s+\w|^\s*class\s+\w")

# Directories whose Python files count as "code" for tests-with-code.
# vehicle: scripts/ (enforce + commit tooling), src/ (versioned cron job
# packages), docs/ (doc builders, if any).
_CODE_DIRS = ("scripts/", "src/", "docs/")

_CACHE_MARKERS = ("__pycache__", ".pyc", ".pyo", ".ds_store")


def _allowlist_path(repo_root, rel):
    return os.path.join(repo_root, rel)


def load_allowlist(repo_root, rel):
    """Set of exempt paths/prefixes; empty (fail closed) when unavailable."""
    if not rel:
        return set()
    try:
        with open(_allowlist_path(repo_root, rel), encoding="utf-8") as f:
            return {ln.strip() for ln in f
                    if ln.strip() and not ln.strip().startswith("#")}
    except OSError:
        print("warning: allowlist %s missing; no exemptions" % rel,
              file=sys.stderr)
        return set()


def is_exempt(path, allow):
    if path in allow:
        return True
    return any(path.startswith(p) for p in allow if p.endswith("/"))


def _is_test_path(path):
    return "/tests/" in path or os.path.basename(path).startswith("test_")


def _yaml_load_unsafe(line):
    # yaml.load without an explicit Loader executes arbitrary code.
    # The needle is built at runtime so this source never carries it.
    needle = "yaml." + "load("
    if needle not in line:
        return False
    return "Loader" not in line


# --- gates -----------------------------------------------------------------

def check_py_compile(diff, repo_root, _allow):
    """Every committed .py file must compile (no cache files written)."""
    out = []
    for path in diff["files"]:
        if not path.endswith(".py"):
            continue
        full = os.path.join(repo_root, path)
        if not os.path.isfile(full):
            continue  # deletion: nothing to compile
        try:
            with open(full, "rb") as f:
                src = f.read()
            compile(src, full, "exec")
        except (SyntaxError, ValueError) as e:
            out.append(("py-compile", path, 0, str(e).splitlines()[0][:120]))
    return out


def check_dangerous(diff, repo_root, allow):
    """Block code-execution primitives in added Python lines."""
    out = []
    for path, info in diff["files"].items():
        if not path.endswith(".py") or is_exempt(path, allow):
            continue
        for lineno, line in info["added"]:
            hit = False
            for pat in _DANGEROUS:
                if pat.search(line):
                    hit = True
                    break
            if not hit and _yaml_load_unsafe(line):
                hit = True
            if hit:
                out.append(("dangerous-calls", path, lineno,
                            line.strip()[:120]))
    return out


def check_bare_except(diff, repo_root, allow):
    """Block bare `except:` clauses in added Python lines."""
    out = []
    for path, info in diff["files"].items():
        if not path.endswith(".py") or is_exempt(path, allow):
            continue
        for lineno, line in info["added"]:
            if _BARE_EXCEPT.match(line):
                out.append(("bare-except", path, lineno,
                            line.strip()[:120]))
    return out


def check_no_cache(diff, repo_root, allow):
    """Block interpreter cache artifacts from entering git."""
    out = []
    for path in diff["files"]:
        low = path.lower()
        if any(m in low for m in _CACHE_MARKERS):
            if not is_exempt(path, allow):
                out.append(("no-cache", path, 0, path[:120]))
    return out


def check_tests_with_code(diff, repo_root, allow):
    """New def/class in code dirs requires a test file in the same diff.

    Standing rule: suites are updated in the same changeset as the code.
    Test files themselves (and allowlisted paths) never trigger it.
    """
    files = diff["files"]
    if any(_is_test_path(p) for p in files):
        return []
    out = []
    for path, info in files.items():
        if _is_test_path(path) or is_exempt(path, allow):
            continue
        if not path.endswith(".py"):
            continue
        if not path.startswith(_CODE_DIRS):
            continue
        for lineno, line in info["added"]:
            if _NEW_DEF.match(line):
                out.append(("tests-with-code", path, lineno,
                            line.strip()[:120]))
                break  # one flag per file is enough signal
    return out


# --- entry point -------------------------------------------------------------

_CHECKS = {
    "py-compile": check_py_compile,
    "dangerous-calls": check_dangerous,
    "bare-except": check_bare_except,
    "no-cache": check_no_cache,
    "tests-with-code": check_tests_with_code,
}


def check_all(diff, repo_root):
    allowlists = {name: load_allowlist(repo_root, rel)
                  for name, _desc, rel in GATE_DEFS}
    out = []
    for name, _desc, _rel in GATE_DEFS:
        out.extend(_CHECKS[name](diff, repo_root, allowlists[name]))
    return out


def read_diff():
    try:
        raw = sys.stdin.read()
    except OSError as e:
        print("error: cannot read stdin: %s" % e, file=sys.stderr)
        sys.exit(2)
    try:
        diff = json.loads(raw)
    except ValueError as e:
        print("error: invalid diff JSON: %s" % e, file=sys.stderr)
        sys.exit(2)
    if not isinstance(diff, dict) or "files" not in diff:
        print("error: diff JSON needs a 'files' object", file=sys.stderr)
        sys.exit(2)
    return diff


def main(argv):
    if len(argv) != 2:
        print("usage: %s <repo-root> < diff.json" % argv[0], file=sys.stderr)
        return 2
    violations = check_all(read_diff(), argv[1])
    for gate, path, lineno, snippet in violations:
        print("BLOCKED [%s] %s:%d: %s" % (gate, path, lineno, snippet))
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
