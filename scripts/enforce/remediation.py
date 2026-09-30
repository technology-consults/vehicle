#!/usr/bin/env python3
"""Gate-failure remediation protocol for the vehicle repo.

This module IS the documentation of the owner's standing procedure for
what to do when a pre-commit enforcement gate blocks a commit
(2026-09-30). scripts/commit.py prints it on EVERY gate failure via
report(). No prose copy of this procedure lives in any text file.

Stdlib only.
"""
import datetime
import sys

# The decision tree, printed verbatim on every gate failure.
PROTOCOL_TEXT = """\
GATE FAILURE -- remediation protocol
=====================================
A pre-commit enforcement gate blocked this commit. Exactly three
legitimate responses exist:

(1) CODE VIOLATION -- your diff trips a gate.
    Fix your code. No approval needed. Re-run scripts/commit.py.

(2) RULE IS WRONG -- the gate misfires on legitimate code.
    Do NOT change the rule yourself. Enforced rules, gates, and
    enforcement mechanisms are locked: no unilateral edits by you
    or by him alone. Propose the change via a task pair (your change
    task blocked on his agreement task -- see rule_change_templates()
    below), discuss it, and change the rule only after you both
    agree. If the misfire blocks prod-critical work right now, also
    use (3) for the immediate exception. Agreed rule changes must
    bump ruleset_version in gates.json and re-pin the content hash
    in scripts/tests/unit/test_ruleset_version.py in the same commit
    (the test prints the new hash on failure).

(3) EXCEPTION -- you need past the gate WITHOUT changing the rule.
    Never bypass silently: there is no --force. First decide
    criticality. CRITICAL means this repo's public output is affected:
    the EV deals pages failing to build or serve on GitHub Pages, a
    deal-scan job package broken or unfetchable from GitHub, or
    GitHub code-fetch for a deploy failing.
    - CRITICAL: build the task pair with task_templates(..., critical=True):
      your task (blocked, assigned to you) with blockedBy on his
      approval task (pending_review, assigned to him, priority
      prod-critical, poke hourly). The hourly poke nudges him in
      the For review thread until he approves or rejects.
    - NON-CRITICAL: task_templates(..., critical=False): the same
      pair, but the approval task carries NO priority and NO poke
      flag -- it rides the normal board review stream. The gate
      stays as-is either way; only this commit goes past it, with
      his written approval on the task.

The only legitimate past-a-gate paths: fix the code, or change a
rule/allowlist after discussion and agreement. All changes are
committed and reviewed. No silent bypass exists.
"""


def _today():
    day = datetime.date.today()
    return day.strftime("%Y%m%d"), day.isoformat()


def task_templates(gate, path, lineno, snippet, reason, thread="vehicle",
                   seq=1, *, critical):
    """Return (my_task, approval_task) dicts for a gate exception.

    Shapes match the board's task records (id, thread, title, status,
    created, updated, due, detail, where, assigned_to, blockedBy).
    critical is keyword-only with NO default: the caller must decide,
    never silently assumed.
      - critical=True: the approval task carries priority prod-critical
        and poke hourly. CRITICAL means this repo's public output is
        affected: the EV deals pages failing to build or serve on
        GitHub Pages, a deal-scan job package broken or unfetchable
        from GitHub, or GitHub code-fetch for a deploy failing.
      - critical=False: the approval task carries NEITHER priority
        NOR poke -- it rides the normal board review stream.
    My task is blocked on the approval task in both cases. seq
    disambiguates multiple exceptions created the same day.
    """
    ymd, iso = _today()
    approval_id = "%s.gate-exception-approval-%s-%d" % (thread, ymd, seq)
    my_id = "%s.gate-exception-%s-%d" % (thread, ymd, seq)
    where = "%s thread" % thread

    if critical:
        crit_reason = "Prod-critical reason: %s. " % reason
        nudge = "the hourly poke cron handles nudging."
        why = "Why prod-critical: %s. " % reason
    else:
        crit_reason = "Reason: %s. " % reason
        nudge = "it rides the normal board review stream."
        why = "Why this exception is needed: %s. " % reason

    my_task = {
        "id": my_id,
        "thread": thread,
        "title": "Gate exception: %s blocked %s:%d" % (gate, path,
                                                       lineno),
        "status": "blocked",
        "created": iso,
        "updated": iso,
        "due": None,
        "detail": ("Gate '%s' blocked the commit at %s:%d (%s). "
                   "%sWaiting on approval task %s; %s"
                   % (gate, path, lineno, snippet, crit_reason,
                      approval_id, nudge)),
        "where": where,
        "assigned_to": "Bandhu",
        "blockedBy": [approval_id],
    }
    approval_task = {
        "id": approval_id,
        "thread": thread,
        "title": "Approval: gate exception for %s (%s:%d)"
                 % (gate, path, lineno),
        "status": "pending_review",
        "created": iso,
        "updated": iso,
        "due": None,
        "detail": ("Exception request: allow the commit past gate '%s' "
                   "at %s:%d (%s) WITHOUT changing the rule. %s"
                   "Approving unblocks %s."
                   % (gate, path, lineno, snippet, why, my_id)),
        "where": where,
        "assigned_to": "BalRam",
    }
    if critical:
        approval_task["priority"] = "prod-critical"
        approval_task["poke"] = "hourly"
    return my_task, approval_task


def rule_change_templates(gate, proposed_change, reason, thread="vehicle",
                          seq=1):
    """Return (my_task, agreement_task) dicts for a proposed rule change.

    Enforced rules, gates, and enforcement mechanisms are LOCKED: no
    unilateral edits by the agent or by him alone. A change needs
    discussion and agreement, recorded as a task pair: my change task
    blocked on his agreement task. The agreement task rides the normal
    review stream -- no hourly poke (that path is reserved for
    prod-critical exceptions via task_templates). seq disambiguates
    multiple proposals created the same day. Agreed changes bump
    ruleset_version in gates.json and re-pin the content hash in
    scripts/tests/unit/test_ruleset_version.py in the same commit.
    """
    ymd, iso = _today()
    agreement_id = "%s.rule-change-approval-%s-%d" % (thread, ymd, seq)
    my_id = "%s.rule-change-%s-%d" % (thread, ymd, seq)
    where = "%s thread" % thread

    my_task = {
        "id": my_id,
        "thread": thread,
        "title": "Rule change: %s -- %s" % (gate, proposed_change[:60]),
        "status": "blocked",
        "created": iso,
        "updated": iso,
        "due": None,
        "detail": ("Proposed change to locked gate '%s': %s. "
                   "Why: %s. Blocked on agreement task %s; the rule is "
                   "changed only after discussion and agreement."
                   % (gate, proposed_change, reason, agreement_id)),
        "where": where,
        "assigned_to": "Bandhu",
        "blockedBy": [agreement_id],
    }
    agreement_task = {
        "id": agreement_id,
        "thread": thread,
        "title": "Agreement: rule change for gate '%s'" % gate,
        "status": "pending_review",
        "created": iso,
        "updated": iso,
        "due": None,
        "detail": ("Proposed change to locked gate '%s': %s. Why: %s. "
                   "Enforced rules are locked -- no unilateral edits. "
                   "Agreeing unblocks %s to make the change (script + "
                   "tests + gates.json, committed and reviewed)."
                   % (gate, proposed_change, reason, my_id)),
        "where": where,
        "assigned_to": "BalRam",
    }
    return my_task, agreement_task


def report(violations):
    """Print collected violations followed by the remediation protocol.

    violations: [(gate, path, lineno, snippet), ...] as collected by
    scripts/commit.py. Pure print, no side effects.
    """
    print("commit: enforcement violations:", file=sys.stderr)
    for gate, path, lineno, snippet in violations:
        print("commit: BLOCKED [%s] %s:%d: %s"
              % (gate, path, lineno, snippet[:120]), file=sys.stderr)
    print(PROTOCOL_TEXT, file=sys.stderr)
