#!/usr/bin/env python3
"""Pre-commit owner-guideline gates for the vehicle repo.

The owner's standing rules that are mechanically checkable on a commit
diff live here as code. Reads a diff on stdin as JSON:
    {"files": {"<repo-rel path>": {"is_new": bool,
                                   "added": [[lineno, line], ...]}}}
argv[1] is the repo root.

Prints one line per violation:
    BLOCKED [<gate>] <path>:<lineno>: <snippet>
Exit 0 when clean, 1 on violations, 2 on usage/internal error.

Gates are documented on GATE_DEFS below; scripts/enforce/gates.json
mirrors that registry and a unit test enforces the match. Stdlib only.

Each gate's deliberate-act escape is its allowlist file. Entries are
exact repo-relative paths or directory prefixes ending in "/". A missing
allowlist file fails closed (exempts nothing).

The no-raw-github gate reuses the repo's own committed checker
(scripts/enforce/no_raw_github.py) -- one definition of the banned host
and of the api.github.com equivalent, shared by the whole-tree scanner
and the pre-commit gate.
"""
import importlib.util
import json
import os
import re
import sys

# ---------------------------------------------------------------------------
# Gate registry: (name, one-line description, allowlist relpath or None).
# ---------------------------------------------------------------------------
GATE_DEFS = [
    ("no-raw-github",
     "no raw-file CDN fetches: all GitHub reads go through api.github.com",
     "scripts/enforce/allowlist_rawgithub.txt"),
    ("no-git-push",
     "no local pushes in scripts: GitHub is API-only",
     "scripts/enforce/allowlist_gitops.txt"),
    ("no-video",
     "video files never go in git",
     "scripts/enforce/allowlist_media.txt"),
    ("pdf-naming",
     "committed PDFs are the single combined <name>-documentation.pdf",
     "scripts/enforce/allowlist_pdfs.txt"),
    ("docs-home",
     "new markdown under docs/ belongs under docs/technical/",
     "scripts/enforce/allowlist_docs_home.txt"),
]

ENFORCE_DIR = os.path.dirname(os.path.abspath(__file__))

# Built at runtime so this module's own source never carries the two-word
# literal the gate scans for.
_GIT_PUSH = re.compile(r"\bgit\s+push\b")
_VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".3gp")
_PY_SH = (".py", ".sh")

_raw_checker = None


def _load_raw_checker(repo_root):
    """Load the repo's own no_raw_github checker (single source of truth
    for the banned host and the api.github.com equivalent). Fail closed:
    a missing checker is itself a violation, never a free pass."""
    global _raw_checker
    if _raw_checker is not None:
        return _raw_checker
    path = os.path.join(repo_root, "scripts", "enforce", "no_raw_github.py")
    spec = importlib.util.spec_from_file_location("vehicle_no_raw_github",
                                                  path)
    if spec is None or spec.loader is None:
        _raw_checker = False
        return _raw_checker
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception:  # noqa: BLE001 -- fail closed, never crash
        _raw_checker = False
        return _raw_checker
    _raw_checker = mod
    return _raw_checker


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

def check_no_raw_github(diff, repo_root, allow):
    """GitHub is API-only: committed content must never reference the raw
    file CDN (fetching raw files over the web is the same violation as
    using the browser for GitHub -- it triggers a phone approval prompt).
    The violation message names the api.github.com equivalent, computed
    by the repo's own checker."""
    checker = _load_raw_checker(repo_root)
    if checker is False:
        return [("no-raw-github", "scripts/enforce/no_raw_github.py", 0,
                 "raw-github checker missing: cannot verify the diff")]
    out = []
    for path, info in diff["files"].items():
        if is_exempt(path, allow):
            continue
        for lineno, line in info["added"]:
            m = checker.RAW_RE.search(line)
            if m:
                msg = ("%s is banned -- GitHub is API-only (2026-09-30). "
                       "Use the API equivalent instead: %s"
                       % (m.group(0)[:80], checker.api_equivalent(m)))
                out.append(("no-raw-github", path, lineno, msg))
                break  # one flag per file is enough signal
    return out


def check_no_git_push(diff, repo_root, allow):
    """No local pushes in scripts: GitHub is API-only, ever."""
    out = []
    for path, info in diff["files"].items():
        if not path.endswith(_PY_SH) or is_exempt(path, allow):
            continue
        for lineno, line in info["added"]:
            if _GIT_PUSH.search(line):
                out.append(("no-git-push", path, lineno,
                            line.strip()[:120]))
                break  # one flag per file is enough signal
    return out


def check_no_video(diff, repo_root, allow):
    """Video files never go in git (static-site repo rule)."""
    out = []
    for path in diff["files"]:
        if path.lower().endswith(_VIDEO_EXTS):
            if not is_exempt(path, allow):
                out.append(("no-video", path, 0, path[:120]))
    return out


def check_pdf_naming(diff, repo_root, allow):
    """Committed PDFs are the single combined <name>-documentation.pdf."""
    out = []
    for path in diff["files"]:
        if not path.lower().endswith(".pdf"):
            continue
        if os.path.basename(path).endswith("-documentation.pdf"):
            continue
        if not is_exempt(path, allow):
            out.append(("pdf-naming", path, 0, path[:120]))
    return out


def check_docs_home(diff, repo_root, allow):
    """New markdown under docs/ belongs under docs/technical/.

    Scoped to docs/ only: the repo-root README is out of scope. Only new
    paths are flagged; existing misplaced docs are grandfathered.
    """
    out = []
    for path, info in diff["files"].items():
        if not info["is_new"] or not path.endswith(".md"):
            continue
        if not path.startswith("docs/") or path.startswith("docs/technical/"):
            continue
        if not is_exempt(path, allow):
            out.append(("docs-home", path, 0, path[:120]))
    return out


# --- entry point -------------------------------------------------------------

_CHECKS = {
    "no-raw-github": check_no_raw_github,
    "no-git-push": check_no_git_push,
    "no-video": check_no_video,
    "pdf-naming": check_pdf_naming,
    "docs-home": check_docs_home,
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
