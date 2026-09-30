#!/usr/bin/env python3
"""Pre-commit security gates for the vehicle repo.

Reads a diff on stdin as JSON:
    {"files": {"<repo-rel path>": {"is_new": bool,
                                   "added": [[lineno, line], ...]}}}
argv[1] is the repo root.

Prints one line per violation:
    BLOCKED [<gate>] <path>:<lineno>: <snippet>
Exit 0 when clean, 1 on violations, 2 on usage/internal error.

Gates are documented on GATE_DEFS below; scripts/enforce/gates.json
mirrors that registry and a unit test enforces the match. Stdlib only.

The token-in-log gate's deliberate-act escape is its allowlist file
(scripts/enforce/allowlist_logging.txt). The secrets gate has no
allowlist: a committed credential is never legitimate (test fixtures
use fake values assembled at runtime).
"""
import json
import os
import re
import sys

# ---------------------------------------------------------------------------
# Gate registry: (name, one-line description, allowlist relpath or None).
# ---------------------------------------------------------------------------
GATE_DEFS = [
    ("secrets",
     "key-looking content in added lines: AWS key IDs, PEM headers, "
     "credential assignments with quoted values",
     None),
    ("token-in-log",
     "credential values must never be printed or logged",
     "scripts/enforce/allowlist_logging.txt"),
]

ENFORCE_DIR = os.path.dirname(os.path.abspath(__file__))

# Secrets gate patterns.
# Deliberately small: block the obvious leaks, stay quiet on ordinary code.
#  - AWS access key IDs have a fixed shape: AKIA + 16 uppercase alphanumerics.
#  - PEM headers are literal and unmistakable.
#  - Assignments only fire on a quoted value of 8+ chars, so short
#    placeholders stay quiet. Word boundaries avoid flagging words like
#    "tokenize". Case-insensitive catches API_KEY / ApiKey too.
SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    re.compile(r"(?i)\b(api_key|apikey|secret|token|password)\b"
               r"\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
]

# Credential words that must never reach print()/logging() as values.
_CRED_WORDS = r"(?:token|secret|api_key|apikey|password|passwd)"
# f-string interpolation of a credential variable, e.g. a formatted
# log line embedding the value.
_FSTRING_CRED = re.compile(
    r"(?i)(?:print|logger\.\w+|logging\.\w+)\s*\(\s*f['\"][^'\"]*\{"
    r"[^}'\"]*" + _CRED_WORDS + r"[^}'\"]*\}")
# A credential variable passed straight to print or a logger call.
_DIRECT_CRED_VAR = re.compile(
    r"(?i)(?:print|logger\.\w+|logging\.\w+)\s*\(\s*"
    r"[a-z_0-9]*" + _CRED_WORDS + r"[a-z_0-9]*\s*[,)]")


def load_allowlist(repo_root, rel):
    """Set of exempt paths/prefixes; empty (fail closed) when unavailable."""
    if not rel:
        return set()
    try:
        with open(os.path.join(repo_root, rel), encoding="utf-8") as f:
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


# --- gates -----------------------------------------------------------------

def check_secrets(diff, repo_root, _allow):
    """Block key-looking content in added lines."""
    out = []
    for path, info in diff["files"].items():
        for lineno, line in info["added"]:
            for pat in SECRET_PATTERNS:
                if pat.search(line):
                    out.append(("secrets", path, lineno,
                                line.strip()[:120]))
                    break
    return out


def check_token_in_log(diff, repo_root, allow):
    """Block printing/logging of credential values in added Python lines.

    Only the value-leaking shapes are flagged: f-string interpolation of
    a credential variable, or the variable passed directly. A string
    literal that merely mentions the word (e.g. a label) stays quiet.
    """
    out = []
    for path, info in diff["files"].items():
        if not path.endswith(".py") or is_exempt(path, allow):
            continue
        for lineno, line in info["added"]:
            if _FSTRING_CRED.search(line) or _DIRECT_CRED_VAR.search(line):
                out.append(("token-in-log", path, lineno,
                            line.strip()[:120]))
    return out


# --- entry point -------------------------------------------------------------

_CHECKS = {
    "secrets": check_secrets,
    "token-in-log": check_token_in_log,
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
