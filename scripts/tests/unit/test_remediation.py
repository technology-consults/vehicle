#!/usr/bin/env python3
"""Unit tests for scripts/enforce/remediation.py.

Convention: a main() printing "<N> passed, <M> failed", exit 0 on
success, 1 on failure.

No literal gate payloads in this file: sample violations use fake
snippets so the file's own added lines never trip the gates.
"""
import contextlib
import importlib.util
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
MOD_PATH = os.path.join(REPO_ROOT, "scripts", "enforce", "remediation.py")
COMMIT_PATH = os.path.join(REPO_ROOT, "scripts", "commit.py")

spec = importlib.util.spec_from_file_location("remediation_mod", MOD_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

_passed = 0
_failed = 0


def check(name, cond):
    global _passed, _failed
    if cond:
        _passed += 1
    else:
        _failed += 1
        print("FAIL: %s" % name)


def test_protocol_branches():
    t = mod.PROTOCOL_TEXT
    check("protocol: branch (1) code violation", "(1) CODE VIOLATION" in t)
    check("protocol: branch (2) rule is wrong", "(2) RULE IS WRONG" in t)
    check("protocol: branch (3) exception", "(3) EXCEPTION" in t)
    check("protocol: no silent bypass stated",
          "No silent bypass exists" in t)
    check("protocol: no --force flag by design",
          "--force" in t and "Never bypass silently" in t)
    check("protocol: task_templates referenced", "task_templates(" in t)


def test_task_templates_critical():
    mine, approval = mod.task_templates(
        "secrets", "x.py", 3, "fake snippet", "pages are down",
        thread="vehicle", seq=2, critical=True)
    check("templates: returns 2-tuple",
          isinstance(mine, dict) and isinstance(approval, dict))
    check("templates: my task blocked on approval id",
          mine["blockedBy"] == [approval["id"]])
    check("templates: id naming",
          re.fullmatch(r"vehicle\.gate-exception-\d{8}-2", mine["id"])
          is not None
          and re.fullmatch(r"vehicle\.gate-exception-approval-\d{8}-2",
                           approval["id"]) is not None)
    check("templates: my task assigned to Bandhu, blocked",
          mine["assigned_to"] == "Bandhu" and mine["status"] == "blocked")
    check("templates: approval assigned to BalRam, pending_review",
          approval["assigned_to"] == "BalRam"
          and approval["status"] == "pending_review")
    check("templates: critical approval priority prod-critical",
          approval.get("priority") == "prod-critical")
    check("templates: critical approval poke hourly",
          approval.get("poke") == "hourly")
    check("templates: detail states gate, file:line, reason",
          "secrets" in mine["detail"] and "x.py:3" in mine["detail"]
          and "pages are down" in mine["detail"]
          and "secrets" in approval["detail"]
          and "x.py:3" in approval["detail"]
          and "pages are down" in mine["detail"])
    check("templates: thread honored",
          mod.task_templates("g", "f.py", 1, "s", "r", thread="tr",
                             critical=True)[0]["thread"] == "tr")
    check("templates: default thread vehicle",
          mod.task_templates("g", "f.py", 1, "s", "r",
                             critical=True)[0]["thread"] == "vehicle")


def test_task_templates_non_critical():
    mine, approval = mod.task_templates(
        "secrets", "x.py", 3, "fake snippet", "docs typo fix",
        thread="vehicle", seq=1, critical=False)
    check("templates: non-critical returns 2-tuple",
          isinstance(mine, dict) and isinstance(approval, dict))
    check("templates: non-critical my task still blocked on approval",
          mine["blockedBy"] == [approval["id"]]
          and mine["status"] == "blocked"
          and mine["assigned_to"] == "Bandhu")
    check("templates: non-critical approval still pending_review/BalRam",
          approval["assigned_to"] == "BalRam"
          and approval["status"] == "pending_review")
    check("templates: non-critical approval has NO priority key",
          "priority" not in approval)
    check("templates: non-critical approval has NO poke key",
          "poke" not in approval)
    check("templates: non-critical detail has no prod-critical wording",
          "prod-critical" not in mine["detail"].lower()
          and "prod-critical" not in approval["detail"].lower())
    check("templates: non-critical detail has no hourly wording",
          "hourly" not in mine["detail"].lower())
    check("templates: non-critical detail states gate, file:line, reason",
          "secrets" in mine["detail"] and "x.py:3" in mine["detail"]
          and "docs typo fix" in mine["detail"])


def test_task_templates_critical_required():
    try:
        mod.task_templates("secrets", "x.py", 3, "s", "r")
        raised = False
    except TypeError:
        raised = True
    check("templates: critical keyword is required (TypeError)",
          raised)
    # positional critical must also fail -- keyword-only
    try:
        mod.task_templates("secrets", "x.py", 3, "s", "r", "vehicle", 1,
                           True)
        raised_pos = False
    except TypeError:
        raised_pos = True
    check("templates: critical is keyword-only", raised_pos)


def test_protocol_branch3_criticality():
    t = mod.PROTOCOL_TEXT
    check("protocol: branch (3) states the criticality test",
          "CRITICAL means this repo's public output is affected" in t)
    check("protocol: branch (3) lists the concrete critical cases",
          "EV deals pages failing to build or serve" in t
          and "deal-scan job package broken or unfetchable" in t)
    check("protocol: branch (3) critical sub-path uses critical=True",
          "critical=True" in t and "poke" in t.lower())
    check("protocol: branch (3) non-critical sub-path uses critical=False",
          "critical=False" in t
          and "normal board review stream" in t)
    check("protocol: branch (3) gate stays as-is either way",
          "stays as-is either way" in t)


def test_report_prints():
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        mod.report([("secrets", "x.py", 3, "fake snippet")])
    out = buf.getvalue()
    check("report: prints the violation", "BLOCKED [secrets] x.py:3" in out)
    check("report: prints the protocol", "GATE FAILURE" in out
          and "(3) EXCEPTION" in out)
    # empty violations: protocol still prints, no crash
    buf2 = io.StringIO()
    with contextlib.redirect_stderr(buf2):
        mod.report([])
    check("report: empty violations prints protocol",
          "GATE FAILURE" in buf2.getvalue())


def test_protocol_branch2_locked():
    t = mod.PROTOCOL_TEXT
    check("protocol: branch (2) forbids self-service edits",
          "Do NOT change the rule yourself" in t)
    check("protocol: branch (2) locked wording",
          "no unilateral edits by you" in t)
    check("protocol: branch (2) references rule_change_templates",
          "rule_change_templates()" in t)
    check("protocol: closing paragraph locked",
          "change a\nrule/allowlist after discussion and agreement" in t)


def test_rule_change_templates_wiring():
    mine, agreement = mod.rule_change_templates(
        "secrets", "allow test fixture", "false positive on fixtures",
        thread="vehicle", seq=1)
    check("rule-change: returns 2-tuple",
          isinstance(mine, dict) and isinstance(agreement, dict))
    check("rule-change: my task blocked on agreement id",
          mine["blockedBy"] == [agreement["id"]])
    check("rule-change: id naming",
          re.fullmatch(r"vehicle\.rule-change-\d{8}-1", mine["id"])
          is not None
          and re.fullmatch(r"vehicle\.rule-change-approval-\d{8}-1",
                           agreement["id"]) is not None)
    check("rule-change: my task assigned to Bandhu, blocked",
          mine["assigned_to"] == "Bandhu" and mine["status"] == "blocked")
    check("rule-change: agreement assigned to BalRam, pending_review",
          agreement["assigned_to"] == "BalRam"
          and agreement["status"] == "pending_review")
    check("rule-change: agreement has no hourly poke",
          "poke" not in agreement)
    check("rule-change: agreement has no prod-critical priority",
          "priority" not in agreement)
    check("rule-change: detail states gate, change, reason",
          "secrets" in mine["detail"]
          and "allow test fixture" in mine["detail"]
          and "false positive on fixtures" in mine["detail"]
          and "secrets" in agreement["detail"]
          and "allow test fixture" in agreement["detail"])
    check("rule-change: thread honored",
          mod.rule_change_templates("g", "c", "r",
                                    thread="tr")[0]["thread"] == "tr")
    check("rule-change: exception path still hourly when critical",
          mod.task_templates("g", "f.py", 1, "s", "r", thread="vehicle",
                             critical=True)[1].get("poke") == "hourly")


def test_commit_has_no_bypass_flag():
    with open(COMMIT_PATH, encoding="utf-8") as f:
        src = f.read()
    check("commit.py: no --force flag", "--force" not in src)
    check("commit.py: no --bypass flag", "--bypass" not in src)
    check("commit.py: uses remediation.report",
          "remediation.report(violations)" in src)


def main():
    test_protocol_branches()
    test_protocol_branch2_locked()
    test_protocol_branch3_criticality()
    test_task_templates_critical()
    test_task_templates_non_critical()
    test_task_templates_critical_required()
    test_rule_change_templates_wiring()
    test_report_prints()
    test_commit_has_no_bypass_flag()
    print("%d passed, %d failed" % (_passed, _failed))
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
