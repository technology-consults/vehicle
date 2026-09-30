# scripts/enforce/ — the commit gate rules (plain words)

_Last modified: 2026-09-30_

This folder holds the rules that check every commit to this repo **before**
it lands on GitHub. Nothing goes in unless it passes. Think of it as a
bouncer for code: the commit script (`scripts/commit.py`) runs the tests
first, then runs every rule here over the changed lines. If any rule
objects, the commit stops and tells you exactly what to do.

## The three rule files

**coding_standards.py** — keeps the code clean:
- every Python file must actually run (it gets compiled as a check)
- no dangerous tricks (things that run random code, shell commands, or
  unpack data in unsafe ways)
- no bare `except:` — always say which error you expect
- no cache junk (`__pycache__`, `.pyc` files) in commits
- new code comes with tests in the same commit

**security.py** — keeps secrets out:
- blocks anything that looks like a real key or password
- blocks printing a password/secret/token to the screen or logs

**owner_guidelines.py** — BalRam's standing rules, written as checks:
- **no-raw-github**: never link to or fetch from the raw-file download
  site (raw dot githubusercontent dot com). That address is banned
  because it pops a permission prompt on his phone. All GitHub reads go
  through the proper address, api.github.com. This check reuses the
  repo's own `no_raw_github.py` so there is one definition of the rule.
- **no-git-push**: scripts never push directly; GitHub changes always go
  through the GitHub website-address (API) route
- **no-video**: video files don't belong in this repo
- **pdf-naming**: PDFs in the repo are the single combined
  `<name>-documentation.pdf`
- **docs-home**: new write-ups under `docs/` go in `docs/technical/`

## The deliberate-act escape (allowlists)

Every rule that allows exceptions has an `allowlist_*.txt` file. If a
rule blocks something you genuinely need, you add the file's path to the
allowlist — that is the deliberate, recorded act. A missing allowlist
file blocks everything (safe default).

## What happens when a rule blocks you

`scripts/commit.py` prints the **remediation protocol** (it lives in
`remediation.py`, not in a text file, so it can't drift out of date).
Three options, no shortcuts:
1. Fix your code and try again.
2. If the rule itself is wrong, propose the change as a task pair and
   change it only after discussion and agreement.
3. If you need past the rule without changing it, request an exception
   the same way. There is deliberately no "skip the checks" button.

## Versions (so everyone agrees on which rules are live)

`gates.json` lists every rule and carries the ruleset version
(`ruleset_version`, currently 1.0.0). The version test in
`scripts/tests/unit/test_ruleset_version.py` fingerprints the whole
folder: if anyone edits a rule without bumping the version and
re-recording the fingerprint in the same commit, the test suite fails
and the commit is refused.

## Running the checks by hand

- Whole-tree scan (the older helper): `python3 scripts/enforce/run_checks.py`
- Full unit tests: `python3 scripts/tests/run_tests.py --tier unit`
- The real path: `python3 scripts/commit.py "<message>" <file> ...`
  runs tests, then these rules, then makes the commit in one step.

Rules deliberately NOT copied here (they don't fit this repo):
- platform-CLI rule — this repo publishes nothing to social platforms.
- portability-notes row — this repo has no portability-notes doc; the
  runtime dependencies are documented in the job READMEs instead.
