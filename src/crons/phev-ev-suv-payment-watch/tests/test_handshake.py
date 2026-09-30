"""Functional test: full handshake with canned agent results.

Drives run.py through all four agent steps using the canned results in
canned.py, then asserts:
  - final report prints widget token + deal report
  - both regression cases flow through (unverified market, bogus payment)
  - state file lands in EVDEALS_STATE_DIR
  - portal push is a no-op in dry-run mode

Unit-tier gate: fails loudly instead of delivering a partial result.
"""
import copy
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager, redirect_stdout, redirect_stderr

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # tests dir (canned)
import ev_common as C

import run as RUN


@contextmanager
def isolated_env():
    """Fresh temp state dir + dry-run mode for the whole run."""
    with tempfile.TemporaryDirectory() as d:
        old_env = dict(os.environ)
        os.environ["EVDEALS_STATE_DIR"] = os.path.join(d, "state")
        os.environ["EVDEALS_DRY_RUN"] = "1"
        try:
            yield os.path.join(d, "state")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def run_step(args, agent_result=None):
    """Run run.main() capturing stdout+stderr and the SystemExit code.

    Args: --agent-result payloads are JSON dicts with a "__RUN_ID__"
    placeholder; run_ids maps step names to the run's run_id.
    Returns (code, stdout, stderr).
    """
    argv = []
    if agent_result is not None:
        argv = ["--agent-result", json.dumps(agent_result)]
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    with redirect_stdout(out_buf), redirect_stderr(err_buf):
        try:
            RUN.main(argv)
        except SystemExit as e:
            return e.code, out_buf.getvalue(), err_buf.getvalue()
    raise AssertionError("run.main() returned instead of exiting")


def extract_request(out):
    start_marker = "@@AGENT-REQUEST-BEGIN@@"
    end_marker = "@@AGENT-REQUEST-END@@"
    start = out.find(start_marker)
    assert start != -1, "expected an agent-request block on stdout"
    end = out.find(end_marker, start)
    assert end != -1, "agent-request block is not closed"
    payload = json.loads(out[start + len(start_marker):end])
    return payload


class HandshakeTest(unittest.TestCase):
    def test_full_run(self):
        import canned  # noqa: E402
        with isolated_env() as statedir:
            # round 1: start -> research request
            code, out, _ = run_step([])
            self.assertEqual(code, 10)
            req = extract_request(out)
            self.assertEqual(req["job"], "phev-ev-suv-payment-watch")
            self.assertEqual(req["step"], "research")
            run_id = req["run_id"]

            def with_id(obj):
                obj = copy.deepcopy(obj)
                return json.loads(json.dumps(obj).replace("__RUN_ID__",
                                                         run_id))

            # round 2: research result -> calculators request
            code, out, _ = run_step([], with_id(canned.RESEARCH))
            self.assertEqual(code, 10)
            req = extract_request(out)
            self.assertEqual(req["step"], "calculators")
            task = req["task"]
            self.assertIn("Niro EV", task)
            self.assertIn("ID.4", task)

            # round 3: calculators result -> math interlude -> verdict req
            code, out, _ = run_step([], with_id(canned.CALCULATORS))
            self.assertEqual(code, 10)
            req = extract_request(out)
            self.assertEqual(req["step"], "verdict")
            task = req["task"]
            # regression 2: bogus 84-mo payment flagged as mismatch
            self.assertIn('"payment_match": false', task)

            # round 4: verdict result -> portal dry-run -> deliver request
            code, out, _ = run_step([], with_id(canned.VERDICT))
            self.assertEqual(code, 10)
            req = extract_request(out)
            self.assertEqual(req["step"], "deliver")
            self.assertIn("Match Criteria", req["task"])
            # dry-run: no commit, artifact recorded under state dir
            portal = C.load_state(req["job"], run_id)["portal"]
            self.assertTrue(portal["dry_run"])
            self.assertTrue(os.path.exists(portal["artifact"]))

            # round 5: deliver result -> final report on stdout, exit 0
            code, out, _ = run_step([], with_id(canned.DELIVER))
            self.assertEqual(code, 0)
            self.assertIn("widget:mock-token-123", out)
            self.assertIn("**1 deal** met all four criteria", out)

            # state file present in the temp state dir
            self.assertTrue(os.path.exists(
                C.state_path("phev-ev-suv-payment-watch", run_id)))

    def test_schema_rejection_reasks_step(self):
        import canned  # noqa: E402
        with isolated_env():
            code, out, _ = run_step([])
            req = extract_request(out)
            run_id = req["run_id"]
            bad = {"run_id": run_id, "garbage": True}
            code, out, _ = run_step([], bad)
            # rejected result re-asks the same step (still exit 10),
            # correction notice prepended
            self.assertEqual(code, 10)
            req = extract_request(out)
            self.assertEqual(req["step"], "research")
            self.assertIn("CORRECTION NEEDED", req["task"])
            self.assertEqual(req["attempt"], 2)

    def test_missing_run_id_fails_loud(self):
        with isolated_env():
            code, out, err = run_step([], {"no_run_id": True})
            self.assertEqual(code, 1)
            self.assertIn("missing run_id", err)

    def test_bad_timeline_flag_reasks_deliver(self):
        import canned  # noqa: E402
        with isolated_env() as statedir:
            code, out, _ = run_step([])
            run_id = extract_request(out)["run_id"]

            def with_id(obj):
                obj = copy.deepcopy(obj)
                return json.loads(json.dumps(obj).replace("__RUN_ID__",
                                                         run_id))
            for canned_step in (canned.RESEARCH, canned.CALCULATORS,
                                canned.VERDICT):
                code, out, _ = run_step([], with_id(canned_step))
                self.assertEqual(code, 10)
            bad = with_id(canned.DELIVER)
            bad["timeline_logged"] = False
            code, out, _ = run_step([], bad)
            self.assertEqual(code, 10)
            req = extract_request(out)
            self.assertEqual(req["step"], "deliver")
            self.assertIn("CORRECTION NEEDED", req["task"])

    def test_no_partial_delivery_on_deterministic_failure(self):
        # a javascript: deep link passes the verdict schema but must be
        # refused by the deterministic HTML builder -> loud failure (exit 1),
        # never a partial portal push or partial report
        import canned  # noqa: E402
        with isolated_env():
            code, out, _ = run_step([])
            run_id = extract_request(out)["run_id"]

            def with_id(obj):
                obj = copy.deepcopy(obj)
                return json.loads(json.dumps(obj).replace("__RUN_ID__",
                                                         run_id))
            for canned_step in (canned.RESEARCH, canned.CALCULATORS):
                code, out, _ = run_step([], with_id(canned_step))
                self.assertEqual(code, 10)
            bad_verdict = with_id(canned.VERDICT)
            bad_verdict["deals"][0]["options"][0]["link"] = "javascript:alert(1)"
            code, out, err = run_step([], bad_verdict)
            self.assertEqual(code, 1)
            self.assertIn("refusing non-http(s) link", err)
            self.assertNotIn("widget:mock-token-123", out)


if __name__ == "__main__":
    unittest.main()
