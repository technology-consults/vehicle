#!/usr/bin/env python3
"""Enforce: no raw.githubusercontent.com URLs in committed code.

Fetching raw files over the web is banned (same violation as using the
browser for GitHub - it triggers a phone approval prompt). All GitHub
reads go through api.github.com. This check fails the commit on any
occurrence and points at the API equivalent.

A raw URL looks like this (host split so this very docstring is not
flagged by the check):
    https://raw. + githubusercontent.com/{owner}/{repo}/{ref}/{path}
The API equivalent is:
    https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={ref}

Usage:
    python3 scripts/enforce/no_raw_github.py [file ...]
With no file arguments, scans all git-tracked files (git ls-files).

Note on refs containing slashes: raw.githubusercontent.com cannot
unambiguously encode a branch name with a slash, so the ref is taken as
the single path segment after {repo}. If your ref has a slash, resolve
the ambiguity by hand when rewriting the URL.
"""
import os
import re
import subprocess
import sys

RAW_RE = re.compile(
    r"https://raw\.githubusercontent\.com/"
    r"(?P<owner>[^/\s\"'<>]+)/"
    r"(?P<repo>[^/\s\"'<>]+)/"
    r"(?P<ref>[^/\s\"'<>]+)/"
    r"(?P<path>[^\"'<>\s]*)"
)


def api_equivalent(match):
    """Convert a raw.githubusercontent.com regex match to the API URL."""
    return ("https://api.github.com/repos/{owner}/{repo}/contents/{path}"
            "?ref={ref}".format(
                owner=match.group("owner"), repo=match.group("repo"),
                path=match.group("path"), ref=match.group("ref")))


def check(files):
    """Return a list of violation dicts for the given files.

    Each violation: {"file", "line", "raw_url", "api_url"}.
    """
    violations = []
    for path in files:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                for lineno, line in enumerate(fh, 1):
                    for m in RAW_RE.finditer(line):
                        violations.append({
                            "file": path,
                            "line": lineno,
                            "raw_url": m.group(0),
                            "api_url": api_equivalent(m),
                        })
        except (OSError, UnicodeError):
            continue
    return violations


def tracked_files():
    """All git-tracked files, relative to the repo root."""
    out = subprocess.run(["git", "ls-files", "-z"],
                         capture_output=True, text=True, check=False)
    if out.returncode != 0:
        return []
    root = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                          capture_output=True, text=True, check=False)
    top = root.stdout.strip() if root.returncode == 0 else os.getcwd()
    return [os.path.join(top, p) for p in out.stdout.split("\0") if p]


def main(argv):
    files = argv[1:] or tracked_files()
    violations = check(files)
    if not violations:
        print("no_raw_github: OK (%d file(s) scanned)" % len(files))
        return 0
    print("no_raw_github: FAILED - raw.githubusercontent.com is banned "
          "(use api.github.com instead):", file=sys.stderr)
    for v in violations:
        print("  %s:%d: %s" % (v["file"], v["line"], v["raw_url"]),
              file=sys.stderr)
        print("    use instead: %s" % v["api_url"], file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
