#!/usr/bin/env python3
"""Gated commit for technology-consults/vehicle.

Thin shim to the agent toolkit's git-commit.py. Resolves the toolkit
checkout via the AGENT_TOOLS_ROOT environment variable, falling back to
this agent's workbench layout. Delegates with --repo and --workdir set
for this repo, so the full unit + enforcement gate suite runs before
every commit.

Usage:
    python3 scripts/commit.py "<commit message>" <path> [<path> ...]

Environment:
    AGENT_TOOLS_ROOT  Path to the agent-tools checkout (the directory
                      containing scripts/). Default: ~/workspace/repos/agent-tools.
                      Another agent on a different machine sets this to
                      their own checkout; see docs/technical/portability-notes.md.
"""
import os
import subprocess
import sys

REPO = "technology-consults/vehicle"


def default_toolkit_root():
    """Default toolkit location for this agent's workbench layout."""
    return os.path.join(os.path.expanduser("~"), "workspace",
                        "repos", "agent-tools")


def resolve_toolkit_root():
    """Return the agent-tools checkout dir, or exit with a clear error."""
    root = os.environ.get("AGENT_TOOLS_ROOT") or default_toolkit_root()
    if not os.path.isdir(os.path.join(root, "scripts")):
        sys.exit(
            "error: cannot find the agent toolkit: no scripts/ directory "
            "under %r. Set AGENT_TOOLS_ROOT to your agent-tools checkout "
            "(the directory containing scripts/)." % root)
    return root


def repo_root():
    """This repo's local clone root (the shim lives in <root>/scripts/)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def build_command(argv, toolkit_root, workdir):
    """The toolkit invocation for this repo; argv passes through."""
    return ([sys.executable,
             os.path.join(toolkit_root, "scripts", "git-commit.py"),
             "--repo", REPO,
             "--workdir", workdir] + list(argv))


def main(argv):
    cmd = build_command(argv, resolve_toolkit_root(), repo_root())
    sys.exit(subprocess.call(cmd))


if __name__ == "__main__":
    main(sys.argv[1:])
