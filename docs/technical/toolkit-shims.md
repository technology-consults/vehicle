# Toolkit shims

Created: 2026-10-05. Last modified: 2026-10-05.

## What a shim is

Every repo in the workbench commits through the shared agent toolkit
(`technology-consults/agent-tools`), not through its own copy of the
commit machinery. Each repo keeps one thin shim — `scripts/commit.py` —
that resolves the toolkit location and delegates with `--repo` and
`--workdir` pinned for that repo. All gates (unit tier, enforcement
modules) run inside the toolkit before anything is committed.

## The convention

- `scripts/commit.py` is the only entry point for commits in this repo.
  Usage: `python3 scripts/commit.py "<message>" <path> [<path> ...]`
- The shim finds the toolkit via the `AGENT_TOOLS_ROOT` environment
  variable. When unset, it falls back to `~/workspace/repos/agent-tools`
  (this agent's workbench layout).
- If no `scripts/` directory exists at the resolved location, the shim
  exits with a clear error telling the user to set `AGENT_TOOLS_ROOT`.
- The shim never hardcodes a machine-specific path; the only default
  is built from the home directory at runtime. See `portability-notes.md`
  for the `AGENT_TOOLS_ROOT` row.

## Unit tier adapter

The toolkit looks for `tests/run_unit.py`. This repo's test suite is
`scripts/tests/run_tests.py --tier unit`; `tests/run_unit.py` runs both
`tests/test_shim.py` and the repo's unit tier.

## For another agent on another machine

1. Check out `technology-consults/agent-tools` somewhere.
2. Set `AGENT_TOOLS_ROOT` to that checkout (the directory containing
   `scripts/`).
3. Run `python3 scripts/commit.py "<message>" <path> ...` from this repo.
   The toolkit's credential store supplies the GitHub credential; no
   tokens are read from files or pasted anywhere.

## Shims in this repo

| Shim | Delegates to | Pinned `--repo` |
|---|---|---|
| `scripts/commit.py` | toolkit `scripts/git-commit.py` | `technology-consults/vehicle` |
