# phev-ev-suv-payment-watch

*Created: 2026-09-30 · Last modified: 2026-09-30*

Versioned-cron package for the **payment-only Ontario EV SUV deal scan**
(daily 08:42 America/Toronto). Track B (agentic): the script is the
orchestrator; the agent is a callable service via the handshake protocol.

Plain words: every morning this job researches current manufacturer lease
and finance special offers for fully electric (BEV) SUVs in Ontario,
configures payment calculators, judges which deals meet all four criteria
(BEV above-base trim, net ≈ $45k after rebates, **no** rate requirement,
bi-weekly payment within cap: lease-48 ≤ $265 / finance-72 ≤ $365), posts
the deal report, and updates the EV deals page (a second entry, marked
"2nd update (payment-only scan)").

This is the sibling of `phev-ev-suv-deal-watch` (08:00 rate-based scan):
`run.py` and `ev_common.py` are byte-identical vendored copies; only
`job_config.py` differs (no rate gate, two configs instead of three,
payment caps, portal entry id suffix `-b`).

Flow overview (plain words): `docs/technical/ev-deals-flow.md` in this repo.
Execution contract: `docs/technical/cron-execution-contract.md` in
`technology-consults/agent-tools`.

## Layout

| File | What it is |
|---|---|
| `run.py` | entrypoint: state machine + handshake (byte-identical in both EV scan jobs; job specifics come from `job_config`) |
| `job_config.py` | job-specific: criteria text, thresholds, portal entry shape, the four agent-step prompts, step validation |
| `ev_common.py` | shared deterministic library, **vendored byte-identical** in both EV scan jobs (math, schemas, HTML builders, GitHub push, state) |
| `tests/` | unit + functional + regression tests (run from the packaged code by the release tooling) |

## Agent-driven vs deterministic split

| Function | Where | Agent-driven or deterministic |
|---|---|---|
| Research manufacturer offers (sites, programs, rates, rebates) | `research` step | **agent** — live research, judgment |
| Configure payment calculators, harvest deep links | `calculators` step | **agent** — browser interaction, judgment |
| Finance amortization, bi-weekly math, EVAP exactly-once application, calculator-vs-math cross-check, mechanical qualification flags | `ev_common.compute_table` | **deterministic** |
| Deal verdicts, near-miss selection, "≈ $45k" judgment, report wording | `verdict` step | **agent** — judgment |
| Portal entry HTML build (from structured verdict data) | `ev_common.build_portal_entry` | **deterministic** |
| Portal push: GitHub API read-modify-write + Pages build verification | `ev_common.push_portal_entry` | **deterministic** |
| Match-Criteria widget HTML build | `ev_common.build_widget_html` | **deterministic** |
| Widget creation + goal-timeline entry (agent tools) | `deliver` step | **agent** — chat/tool capabilities only the agent has |
| Report hygiene (deal report ONLY, no housekeeping footers) | `ev_common.check_report_hygiene` + prompt | **deterministic** check on an agent-written report |

## Handshake flow

`research` → `calculators` → *(deterministic math)* → `verdict` →
*(deterministic portal push)* → `deliver` → exit 0. Four agent rounds max;
the 5-round budget fails loudly instead of delivering a partial result.
Each agent result must echo `run_id`; the schema is validated, then
step-specific checks run (calculator coverage, report hygiene,
timeline confirmation). A rejection re-asks the same step with a
correction note.

State survives across re-invocations in
`~/.cron_runner/job_state/<job>__<run_id>.json`
(override with `EVDEALS_STATE_DIR`). Stale files (>7 days) are cleaned on
run start.

## Running / testing

```sh
# one handshake round (prints the agent-request block, exits 10)
python3 run.py
# feed an agent result back
python3 run.py --agent-result '{"run_id": "...", ...}'

# tests (same invocation the release tooling uses)
cd src/crons/phev-ev-suv-payment-watch && python3 -m unittest discover -s tests -t .

# dry run: portal push is skipped, the would-be article is recorded instead
EVDEALS_DRY_RUN=1 python3 run.py
```

No network is touched in dry-run mode. Live runs need the
`custom.github` credential surrogate (same mechanism as the shared runner).

## Release

Per-job release, tag `phev-ev-suv-payment-watch-vYYYYMMDD.N`, pin
`(technology-consults/vehicle, <tag>)`. Built only from `git archive` via
`scripts/make_cron_release.py` (agent-tools); creating the GitHub release
needs BalRam's written approval — the tooling stages only, never publishes.

## Banned

`raw.githubusercontent.com` — fetching it triggers a phone approval prompt
(same violation as using the browser for GitHub). All GitHub reads go
through `api.github.com`. Enforced by `scripts/enforce/no_raw_github.py`.
