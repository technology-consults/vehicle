# Portability notes

Created: 2026-10-05. Last modified: 2026-10-05.

Code in this repo that only runs inside the Muse agent runtime is listed
here, one row per dependency. The `portability-row` enforcement gate
requires this file to be touched in the same commit that introduces a
new runtime-only dependency.

| Dependency | Used by | Why it is runtime-only |
|---|---|---|
| Agent toolkit location (`AGENT_TOOLS_ROOT`) | `scripts/commit.py` (shim) | The shim delegates every commit to the toolkit's `git-commit.py`. Default: `~/workspace/repos/agent-tools` (this machine's workbench). Outside the runtime, set `AGENT_TOOLS_ROOT` to the local agent-tools checkout (the directory containing `scripts/`); the shim exits with a clear error if `scripts/` is not found there. |
