#!/usr/bin/env python3
"""Entrypoint for the Ontario EV-SUV deal-scan versioned cron jobs.

This file is byte-identical in src/crons/phev-ev-suv-deal-watch/ and
src/crons/phev-ev-suv-payment-watch/ - everything job-specific comes from
the sibling job_config.py. The shared deterministic library is ev_common.py
(vendored identically in both packages).

Handshake flow (script-as-orchestrator, max 5 rounds):
  research (agent) -> calculators (agent) -> [deterministic: payment math,
  EVAP exactly-once, mechanical flags] -> verdict (agent) ->
  [deterministic: portal entry build + GitHub API push] -> deliver (agent:
  Match-Criteria widget + goal-timeline entry) -> exit 0 with the final
  report on stdout.

State: the script is re-invoked fresh on every handshake round, so progress
lives in a state file (see ev_common.state_path). Each agent result must
echo run_id; a missing/mismatched run_id fails loudly.

Exit codes: 10 = agent step requested (handshake); 0 = success; anything
else = loud failure (never a partial delivery).
"""
import argparse
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ev_common as C
import job_config as J

JOB_ID = J.JOB_ID


def request_step(state, step, correction=None):
    """Issue an agent request for step, enforcing the 5-round budget."""
    if state["rounds_used"] >= C.MAX_ROUNDS:
        C.fail_loud(
            "handshake round budget (%d) exhausted at step %r; failing "
            "loudly instead of delivering a partial result"
            % (C.MAX_ROUNDS, step))
    state["rounds_used"] += 1
    task, schema = J.build_step_request(step, state, correction=correction)
    C.save_state(JOB_ID, state)
    C.emit_request(task, schema, state["run_id"], JOB_ID, step,
                   state["rounds_used"])


def start_run():
    C.cleanup_stale_state()
    now = C.today_toronto()
    run_id = C.new_run_id()
    state = {
        "run_id": run_id,
        "job_id": JOB_ID,
        "step": J.STEPS[0],
        "rounds_used": 0,
        "run_date": now.strftime("%Y-%m-%d"),
        "long_date": C.long_date(now),
        "started_at": now.isoformat(),
    }
    request_step(state, J.STEPS[0])


def advance(state, result):
    """Handle a validated agent result: run deterministic phases, advance."""
    step = state["step"]
    try:
        if step == "research":
            state["research"] = result
            state["step"] = "calculators"
        elif step == "calculators":
            state["calculators"] = result
            state["computed"] = C.compute_table(J, state["research"], result)
            state["step"] = "verdict"
        elif step == "verdict":
            state["verdict"] = result
            entry_id = "d%s%s" % (state["run_date"], J.PORTAL_ID_SUFFIX)
            h2 = state["long_date"] + J.PORTAL_TITLE_SUFFIX
            article = C.build_portal_entry(
                J, entry_id, h2,
                result["verdict_line"], result["criteria_rows"],
                result["deals"])
            dry = os.environ.get("EVDEALS_DRY_RUN") == "1"
            state["portal"] = C.push_portal_entry(J, entry_id, article,
                                                  dry_run=dry)
            state["step"] = "deliver"
        elif step == "deliver":
            state["deliver"] = result
            C.save_state(JOB_ID, state)
            print(result["widget_token"])
            print()
            print(state["verdict"]["report_markdown"])
            sys.exit(0)
    except Exception:  # deterministic phase failed -> loud, no partial output
        C.fail_loud("deterministic phase after step %r failed:\n%s"
                    % (step, traceback.format_exc()))
    request_step(state, state["step"])


def continue_run(raw):
    try:
        result = json.loads(raw)
    except ValueError as e:
        C.fail_loud("agent result is not valid JSON: %s" % e)
    if not isinstance(result, dict):
        C.fail_loud("agent result must be a JSON object")
    run_id = result.get("run_id")
    if not run_id:
        C.fail_loud("agent result is missing run_id")
    state = C.load_state(JOB_ID, run_id)
    step = state["step"]
    if step not in J.STEPS:
        C.fail_loud("state file has unknown step %r" % (step,))
    task, schema = J.build_step_request(step, state)
    try:
        C.validate_against_schema(result, schema)
    except C.SchemaError as e:
        request_step(state, step,
                     correction="schema validation failed: %s" % e)
    ok, err = J.validate_step_result(step, result, state)
    if not ok:
        request_step(state, step, correction=err)
    return advance(state, result)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="versioned cron job: " + JOB_ID)
    ap.add_argument("--agent-result", default=None,
                    help="JSON result from the agent for the current step")
    args = ap.parse_args(argv)
    if args.agent_result is None:
        return start_run()
    return continue_run(args.agent_result)


if __name__ == "__main__":
    sys.exit(main())
