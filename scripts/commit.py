#!/usr/bin/env python3
"""Commit files to GitHub ONLY after the unit tier passes.

Usage:
    python3 scripts/commit.py "<commit message>" <path> [<path> ...]

Pipeline (BalRam's standing rules, 2026-09-30), in order:
  1. Unit tier: scripts/tests/run_tests.py --tier unit must be green.
  2. Enforcement: scripts/enforce/*.py modules run over the ADDED lines
     of the files being committed (diffed against GitHub main via
     read-only contents-API GETs), in fixed module order:
       coding_standards -> security -> owner_guidelines
     Every module's violations are collected so the author fixes
     everything in one round. Any violation -- or a missing/crashing
     module (fail closed) -- aborts with non-zero exit before any
     mutating API call, printing the remediation protocol from
     scripts/enforce/remediation.py (fix the code, propose a rule
     change through discussion and agreement, or request a
     prod-critical exception -- no silent bypass).

The commit is atomic: one Git Trees API commit for all paths. Paths are
repo-relative, read from this script's working tree. A listed path that
exists locally is committed; one that exists only remotely is deleted
(tree entry with sha null). Files not listed are left alone.

Auth: GITHUB_TOKEN env var first; otherwise the Muse runtime credential
surrogate (see scripts/enforce/README.md).

GitHub is API-only, ever: this script makes no local pushes; all writes
go through api.github.com.

Stdlib only.
"""
import base64
import difflib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://api.github.com"
REPO = "technology-consults/vehicle"

# Enforcement modules, in fixed run order. Each is invoked as:
#   python3 scripts/enforce/<name>.py <repo-root>   (diff JSON on stdin)
# and prints "BLOCKED [<gate>] <path>:<lineno>: <snippet>" lines.
ENFORCE_MODULES = ("coding_standards", "security", "owner_guidelines")

_SURROGATE_BIN = "/opt/hatch/skills/skill-creator/bin"
if os.path.isdir(_SURROGATE_BIN) and _SURROGATE_BIN not in sys.path:
    sys.path.insert(0, _SURROGATE_BIN)

# Gate-failure remediation protocol (scripts/enforce/remediation.py):
# printed on every enforcement abort. Imported here so the failure path
# always carries the procedure; a broken import fails closed at startup.
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
from enforce import remediation


def api(method, path, body=None):
    from dynamic_credentials import add_surrogate_to_request
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        API + path, data=data, method=method,
        headers={"User-Agent": "muse-agent",
                 "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    else:
        add_surrogate_to_request(req, "custom.github",
                                 allowed_hosts=["api.github.com"])
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode() or "{}")


def run_unit_tier():
    """Run the unit tier. Return True iff green."""
    r = subprocess.run(
        [sys.executable, os.path.join(REPO_ROOT, "scripts", "tests",
                                      "run_tests.py"),
         "--tier", "unit"],
        cwd=REPO_ROOT)
    return r.returncode == 0


_RULESET_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def load_ruleset_version():
    """Read scripts/enforce/gates.json and return ruleset_version, or None
    (fail closed) when the file is unreadable or the version is missing /
    not semver-shaped. Every commit log prints the agreed ruleset version
    that enforced it."""
    path = os.path.join(REPO_ROOT, "scripts", "enforce", "gates.json")
    try:
        with open(path, encoding="utf-8") as f:
            inv = json.load(f)
    except (OSError, ValueError) as e:
        print("commit: ABORTED -- cannot read ruleset inventory %s: %s"
              % (path, e), file=sys.stderr)
        return None
    version = inv.get("ruleset_version")
    if not isinstance(version, str) or not _RULESET_SEMVER.match(version):
        print("commit: ABORTED -- ruleset_version missing or not semver in "
              "scripts/enforce/gates.json. Nothing was committed.",
              file=sys.stderr)
        return None
    return version


def remote_text(path):
    """File text at GitHub main, or None when the file is new."""
    try:
        data = api("GET", "/repos/%s/contents/%s?ref=main" %
                   (REPO, urllib.parse.quote(path)))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    if isinstance(data, dict) and data.get("encoding") == "base64":
        return base64.b64decode(data["content"]).decode("utf-8", "replace")
    return None


def diff_added(old_text, new_lines):
    """[(new_lineno, line)] added in new_lines vs old_text.

    old_text None means the file is new: every line counts as added.
    """
    if old_text is None:
        return list(enumerate(new_lines, 1))
    old = old_text.splitlines()
    new_no = 0
    out = []
    for line in difflib.unified_diff(old, new_lines, n=0, lineterm=""):
        if line.startswith("@@"):
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            new_no = int(m.group(1))
        elif line.startswith("+") and not line.startswith("+++"):
            out.append((new_no, line[1:]))
            new_no += 1
    return out


def build_diff_payload(paths):
    """{"files": {path: {"is_new": bool, "added": [[lineno, line], ...]}}}.

    Read-only: one contents-API GET per path (to diff against main).
    Deleted paths (not on local disk) contribute no added lines.
    """
    files = {}
    for p in paths:
        full = os.path.join(REPO_ROOT, p)
        if not os.path.isfile(full):
            continue
        with open(full, encoding="utf-8", errors="replace") as f:
            new_lines = f.read().splitlines()
        old_text = remote_text(p)
        files[p] = {"is_new": old_text is None,
                    "added": diff_added(old_text, new_lines)}
    return {"files": files}


_BLOCKED_RE = re.compile(r"^BLOCKED \[([^\]]+)\] (.+):(\d+)(?:: (.*))?$")


def run_enforcement(paths):
    """Run every enforcement module over the added-lines diff.

    Returns [(gate, path, lineno, snippet)]. All modules run even when an
    earlier one fails, so one round fixes everything. Fail closed: a
    missing or crashing module is itself a violation. Issues only
    read-only GETs (to compute the diff); never touches the Trees API.
    Callers must abort before any mutating API call when non-empty.
    """
    payload = json.dumps(build_diff_payload(paths))
    violations = []
    for mod in ENFORCE_MODULES:
        script = os.path.join(REPO_ROOT, "scripts", "enforce", mod + ".py")
        if not os.path.isfile(script):
            violations.append((mod + "/missing", script, 0,
                               "enforcement module missing"))
            continue
        try:
            r = subprocess.run(
                [sys.executable, script, REPO_ROOT],
                input=payload, capture_output=True, text=True,
                cwd=REPO_ROOT, timeout=120)
        except Exception as e:  # noqa: BLE001 -- fail closed, never crash
            violations.append((mod + "/error", script, 0, str(e)[:120]))
            continue
        if r.returncode == 2:
            err = (r.stderr.strip().splitlines() or ["module error"])[0]
            violations.append((mod + "/error", script, 0, err[:120]))
            continue
        if r.returncode not in (0, 1):
            violations.append((mod + "/error", script, 0,
                               "exit %d" % r.returncode))
            continue
        blocked = 0
        for line in r.stdout.splitlines():
            m = _BLOCKED_RE.match(line)
            if m:
                blocked += 1
                violations.append(
                    (m.group(1), m.group(2), int(m.group(3)),
                     m.group(4) or ""))
        if r.returncode == 1 and blocked == 0:
            violations.append((mod + "/error", script, 0,
                               "reported failure with no BLOCKED lines"))
    return violations


def main(argv=None):
    argv = sys.argv if argv is None else argv
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    message, paths = argv[1], argv[2:]

    upserts, deletes = [], []
    for p in paths:
        if os.path.isabs(p) or ".." in p.split(os.sep):
            print("commit: path must be repo-relative: %s" % p,
                  file=sys.stderr)
            return 2
        full = os.path.join(REPO_ROOT, p)
        if os.path.isfile(full):
            upserts.append(p)
        elif remote_text(p) is not None:
            deletes.append(p)  # exists remotely only: delete it
        else:
            print("commit: not a file: %s" % p, file=sys.stderr)
            return 2

    ruleset_version = load_ruleset_version()
    if ruleset_version is None:
        return 1
    print("commit: enforcing ruleset v%s" % ruleset_version)

    print("commit: running unit tier (gate)...")
    if not run_unit_tier():
        print("commit: ABORTED -- unit tier failed. Fix the tests, then "
              "retry. Nothing was committed.", file=sys.stderr)
        return 1
    print("commit: unit tier green -- running enforcement modules...")
    violations = run_enforcement(upserts)
    if violations:
        # Every gate failure prints the remediation protocol (see
        # scripts/enforce/remediation.py). Bypass flags are forbidden
        # by design; test_remediation.py asserts none exist here.
        remediation.report(violations)
        print("commit: ABORTED -- enforcement violations. "
              "Nothing was committed.", file=sys.stderr)
        return 1
    print("commit: enforcement green -- committing %d file(s), "
          "deleting %d" % (len(upserts), len(deletes)))

    base_commit = api("GET", "/repos/%s/git/ref/heads/main" % REPO)[
        "object"]["sha"]
    base_tree = api("GET", "/repos/%s/git/commits/%s" % (REPO, base_commit))[
        "tree"]["sha"]
    tree = []
    for p in upserts:
        with open(os.path.join(REPO_ROOT, p), "rb") as f:
            raw = f.read()
        blob = api("POST", "/repos/%s/git/blobs" % REPO,
                   {"content": base64.b64encode(raw).decode(),
                    "encoding": "base64"})
        tree.append({"path": p, "mode": "100644", "type": "blob",
                     "sha": blob["sha"]})
    for p in deletes:
        # Trees API deletion: sha null (mode/type still required by the API)
        tree.append({"path": p, "mode": "100644", "type": "blob",
                     "sha": None})
    new_tree = api("POST", "/repos/%s/git/trees" % REPO,
                   {"base_tree": base_tree, "tree": tree})["sha"]
    commit = api("POST", "/repos/%s/git/commits" % REPO,
                 {"message": message, "tree": new_tree,
                  "parents": [base_commit]})
    api("PATCH", "/repos/%s/git/refs/heads/main" % REPO,
        {"sha": commit["sha"]})
    print("commit: %s" % commit["sha"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
