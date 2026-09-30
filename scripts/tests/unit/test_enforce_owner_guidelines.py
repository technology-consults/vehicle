#!/usr/bin/env python3
"""Unit tests for scripts/enforce/owner_guidelines.py.

Convention: a main() printing "<N> passed, <M> failed", exit 0 on
success, 1 on failure.

The banned raw-file host is spelled only via concatenation in this file,
so the check under test never flags its own test suite. The two-word
push literal is likewise built at runtime.
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
MOD_PATH = os.path.join(REPO_ROOT, "scripts", "enforce",
                        "owner_guidelines.py")

# The no-raw-github gate needs the repo's own checker present.
RAW_CHECKER_PATH = os.path.join(REPO_ROOT, "scripts", "enforce",
                                "no_raw_github.py")
HAS_CHECKER = os.path.isfile(RAW_CHECKER_PATH)

spec = importlib.util.spec_from_file_location("owner_guidelines_mod",
                                              MOD_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

BANNED = "raw." + "githubusercontent.com"

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


# --- no-raw-github (reuses the repo's own checker) ---------------------------

def test_no_raw_github_blocked():
    if not HAS_CHECKER:
        check("no-raw-github: checker present locally", False)
        return
    url = "https://" + BANNED + "/o/r/main/f.py"
    line = "URL = " + chr(34) + url + chr(34)
    out = mod.check_no_raw_github(mdiff({"scripts/a.py": [(3, line)]}),
                                  REPO_ROOT, set())
    check("no-raw-github: raw URL in added lines blocked",
          len(out) == 1 and out[0][0] == "no-raw-github"
          and out[0][2] == 3)
    check("no-raw-github: message points at the api.github.com equivalent",
          "api.github.com/repos/o/r/contents/f.py?ref=main" in out[0][3]
          and "banned" in out[0][3])


def test_no_raw_github_html_too():
    if not HAS_CHECKER:
        check("no-raw-github: checker present locally", False)
        return
    url = "https://" + BANNED + "/o/r/main/x"
    out = mod.check_no_raw_github(mdiff({"ev-deals/index.html": [(1, url)]}),
                                  REPO_ROOT, set())
    check("no-raw-github: html files scanned too",
          len(out) == 1 and out[0][0] == "no-raw-github")


def test_no_raw_github_clean_passes():
    if not HAS_CHECKER:
        check("no-raw-github: checker present locally", False)
        return
    lines = [(1, "https://api.github.com/repos/o/r/contents/f?ref=main"),
             (2, "# no raw file links here")]
    out = mod.check_no_raw_github(mdiff({"scripts/a.py": lines}),
                                  REPO_ROOT, set())
    check("no-raw-github: api.github.com links pass", out == [])


def test_no_raw_github_missing_checker_fails_closed():
    # reset the module's checker cache so the missing path is exercised
    mod._raw_checker = None
    try:
        out = mod.check_no_raw_github(
            mdiff({"scripts/a.py": [(1, "x = 1")]}),
            "/nonexistent-root", set())
    finally:
        mod._raw_checker = None  # force reload on next use
    check("no-raw-github: missing checker fails closed, not open",
          len(out) == 1 and out[0][0] == "no-raw-github"
          and "missing" in out[0][3])


def test_no_raw_github_allowlisted():
    if not HAS_CHECKER:
        check("no-raw-github: checker present locally", False)
        return
    url = "https://" + BANNED + "/o/r/main/f.py"
    out = mod.check_no_raw_github(mdiff({"scripts/a.py": [(1, url)]}),
                                  REPO_ROOT, {"scripts/a.py"})
    check("no-raw-github: allowlisted path exempt", out == [])


# --- no-git-push -------------------------------------------------------------

def test_no_git_push_blocked():
    line = "run(" + chr(34) + "gi" + "t " + "pu" + "sh" + chr(34) + ")"
    out = mod.check_no_git_push(mdiff({"scripts/deploy.py": [(2, line)]}),
                                REPO_ROOT, set())
    check("no-git-push: local push in scripts blocked",
          len(out) == 1 and out[0][0] == "no-git-push"
          and out[0][2] == 2)


def test_no_git_push_html_ignored():
    line = "x = " + chr(34) + "gi" + "t " + "pu" + "sh" + chr(34)
    out = mod.check_no_git_push(mdiff({"notes.md": [(1, line)]}),
                                REPO_ROOT, set())
    check("no-git-push: only .py/.sh scanned", out == [])


def test_no_git_push_clean_passes():
    lines = [(1, "# GitHub is API-only: no local pushes here"),
             (2, "api(" + chr(34) + "POST" + chr(34) + ")")]
    out = mod.check_no_git_push(mdiff({"scripts/a.py": lines}),
                                REPO_ROOT, set())
    check("no-git-push: clean scripts pass", out == [])


# --- no-video ----------------------------------------------------------------

def test_no_video_blocked():
    out = mod.check_no_video(
        {"files": {"ev-deals/clip.mp4": {"is_new": True, "added": []}}},
        REPO_ROOT, set())
    check("no-video: mp4 blocked",
          len(out) == 1 and out[0][0] == "no-video")


def test_no_video_case_insensitive():
    out = mod.check_no_video(
        {"files": {"ev-deals/CLIP.MOV": {"is_new": True, "added": []}}},
        REPO_ROOT, set())
    check("no-video: extension match is case-insensitive",
          len(out) == 1 and out[0][0] == "no-video")


def test_no_video_clean_passes():
    out = mod.check_no_video(
        {"files": {"ev-deals/index.html": {"is_new": True, "added": []}}},
        REPO_ROOT, set())
    check("no-video: html passes", out == [])


# --- pdf-naming --------------------------------------------------------------

def test_pdf_naming_blocked():
    out = mod.check_pdf_naming(
        {"files": {"random-report.pdf": {"is_new": True, "added": []}}},
        REPO_ROOT, set())
    check("pdf-naming: non-documentation pdf blocked",
          len(out) == 1 and out[0][0] == "pdf-naming")


def test_pdf_naming_combined_passes():
    out = mod.check_pdf_naming(
        {"files": {"vehicle-documentation.pdf":
                   {"is_new": True, "added": []}}},
        REPO_ROOT, set())
    check("pdf-naming: single combined documentation pdf passes",
          out == [])


# --- docs-home ---------------------------------------------------------------

def test_docs_home_blocked():
    out = mod.check_docs_home(
        {"files": {"docs/notes.md": {"is_new": True, "added": []}}},
        REPO_ROOT, set())
    check("docs-home: new md directly under docs/ blocked",
          len(out) == 1 and out[0][0] == "docs-home")


def test_docs_home_technical_passes():
    out = mod.check_docs_home(
        {"files": {"docs/technical/notes.md":
                   {"is_new": True, "added": []}}},
        REPO_ROOT, set())
    check("docs-home: docs/technical/ passes", out == [])


def test_docs_home_root_readme_out_of_scope():
    out = mod.check_docs_home(
        {"files": {"README.md": {"is_new": True, "added": []}}},
        REPO_ROOT, set())
    check("docs-home: repo-root README out of scope", out == [])


def test_docs_home_existing_grandfathered():
    out = mod.check_docs_home(
        {"files": {"docs/notes.md": {"is_new": False,
                                     "added": [(1, "x")]}}},
        REPO_ROOT, set())
    check("docs-home: existing docs grandfathered", out == [])


# --- gate registry sanity ----------------------------------------------------

def test_gate_defs_documented():
    names = [g[0] for g in mod.GATE_DEFS]
    check("registry: five owner gates",
          names == ["no-raw-github", "no-git-push", "no-video",
                    "pdf-naming", "docs-home"])
    check("registry: every gate has a check function",
          all(n in mod._CHECKS for n in names))
    check("registry: every allowlist is under scripts/enforce/",
          all(g[2] is None or g[2].startswith("scripts/enforce/")
              for g in mod.GATE_DEFS))


def main():
    test_no_raw_github_blocked()
    test_no_raw_github_html_too()
    test_no_raw_github_clean_passes()
    test_no_raw_github_missing_checker_fails_closed()
    test_no_raw_github_allowlisted()
    test_no_git_push_blocked()
    test_no_git_push_html_ignored()
    test_no_git_push_clean_passes()
    test_no_video_blocked()
    test_no_video_case_insensitive()
    test_no_video_clean_passes()
    test_pdf_naming_blocked()
    test_pdf_naming_combined_passes()
    test_docs_home_blocked()
    test_docs_home_technical_passes()
    test_docs_home_root_readme_out_of_scope()
    test_docs_home_existing_grandfathered()
    test_gate_defs_documented()
    print("%d passed, %d failed" % (_passed, _failed))
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
