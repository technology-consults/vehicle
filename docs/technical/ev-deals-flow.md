# EV Deals Flow — Ontario EV SUV daily scan

_Created: 2026-09-30 · Last modified: 2026-10-02_

Plain words first: every morning, two automatic scans look for electric-SUV deals in Ontario and report back. This page is the map — it tells you where every piece of that flow lives. The actual instructions each scan follows live in the versioned job packages in this repo (see "Where the logic lives" below); the scheduler's saved definitions carry only the schedule, the delivery target, and the pinned package version.

## The two scans

Both scans are cron jobs owned by the goal `sub-3-phev-ev-suv-deal-in-ontario` (goal id `goal_e8a8f8022330`). Both report to the SUV deal scan side chat (`de5d7ab8-9709-4e7c-a556-fd5f582b2f7e`) and both log their outcome to the goal timeline.

| # | Cron id | Title | Fires (America/Toronto) | What it checks |
|---|---------|-------|-------------------------|----------------|
| 1 | `phev-ev-suv-deal-watch` | EV SUV deal watch (Ontario) | daily 8:00 ET | rate-based scan: qualifies only if rate < 3% APR **and** payment $150–$200 bi-weekly |
| 2 | `phev-ev-suv-payment-watch` | EV SUV payment-only scan (Ontario) | daily 8:42 ET | payment-only scan: no rate requirement; qualifies if lease ≤ $265 or finance ≤ $365 bi-weekly |

## Where the logic lives

- The scan logic lives in this repo as versioned job packages: `src/crons/phev-ev-suv-deal-watch/` (08:00 rate-based scan) and `src/crons/phev-ev-suv-payment-watch/` (08:42 payment-only scan). Each package holds the entrypoint (`run.py` — the script is the orchestrator, the agent is a callable service via the handshake), the job-specific criteria (`job_config.py`), the shared math and helpers (`ev_common.py`, byte-identical in both), and its tests. Each package is released per job (a `<job>-vYYYYMMDD.N` GitHub Release); the scheduler's saved cron definition carries only the schedule, the delivery target, and the pinned package version.
- Mirror copy of every scheduler definition: the `crons/` folder of the `technology-consults/cross-thread-task-status-tracker` repo (also served as a review page at https://technology-consults.github.io/cross-thread-task-status-tracker/crons/), synced from the scheduler daily at 6:42 ET by the `cron-definitions-sync` job. The scheduler is the source of truth for *when* each job fires — the mirror is read-only.
- Local read-only copies of the scheduler definitions: `~/workspace/goals/sub-3-phev-ev-suv-deal-in-ontario/crons/daily/phev-ev-suv-deal-watch__daily@08:00:00.md` and `~/workspace/goals/sub-3-phev-ev-suv-deal-in-ontario/crons/daily/phev-ev-suv-payment-watch__daily@08:42:00.md`.
- Plain-English standing criteria summary: the goal file `~/workspace/goals/sub-3-phev-ev-suv-deal-in-ontario/GOAL.md`.
- Execution contract (script-as-orchestrator, handshake rules): `docs/technical/cron-execution-contract.md` in `technology-consults/agent-tools`.

## What counts as a deal (both scans)

1. Fully electric (BEV) SUV, trim **above** the base model. PHEVs and hybrids are out of scope (rule change 2026-09-28).
2. Net price ≈ CAD $45,000 after manufacturer rebates (freight/PDI/taxes excluded from the comparison).
3. $5,000 down, payments quoted bi-weekly, taxes included.
4. Federal EV rebate (EVAP) folded into the payments: $5,000 for BEVs in 2026, applied at final transaction values of $50,000 or less (no cap for Canadian-made EVs). Applied exactly once; the pre-rebate net price is always shown alongside. Ontario has no provincial rebate.
5. Kia loyalty rates may be used (BalRam qualifies for Kia loyalty only); every other brand is judged on its publicly advertised non-loyalty rate.

**Rate scan (8:00)** also requires: interest rate below 3% APR, and bi-weekly payment in the $150–$200 band — checked on three setups per candidate: 48-month lease (20,000 km/yr), 72-month finance, 84-month finance. A deal qualifies if **any** setup meets all four criteria. If nothing qualifies, it reports the most tempting near-misses (max 3, up to $260 bi-weekly).

**Payment-only scan (8:42)** drops the rate requirement (APR shown for reference only) and checks two setups per candidate: 48-month lease qualifies at ≤ $265 bi-weekly, 72-month finance qualifies at ≤ $365 bi-weekly. A deal qualifies if **any** setup meets the criteria. Sources (standing rule 2026-10-02): manufacturer build-and-price configurators are preferred; dealership websites are a fallback only — within 50 km of postal code L6Y 0Z4, Ontario, location confirmed from the dealer's own site, figures labeled dealer-sourced. Out-of-radius dealer data is never used; otherwise the candidate is marked unverifiable.

## Outputs

Each run produces:

1. A chat report in the SUV deal scan side chat: a "Match Criteria" panel (collapsible HTML widget) on top, then a Deals section — one group header per deal (model/trim · MSRP · rebate · net price) with a per-setup table (Option | Rate → bi-weekly payment); the qualifying payment is bolded — that bolding alone marks qualification.
2. A goal-timeline entry (`user_goal.create_entry` on `goal_e8a8f8022330`) logging the run outcome.
3. A new entry on the EV deals page (see below).

## The EV deals page

- Source in this repo: `ev-deals/index.html` (page version label `v2` in the source).
- Live page: https://technology-consults.github.io/vehicle/ev-deals/ (GitHub Pages, served from this repo).
- What it shows: the daily scan results as shared in the chat — newest entry first, two entries each morning. Each entry mirrors that day's chat message: a dated heading, a verdict line (how many deals met the criteria), a Match Criteria table, and one deal block per deal (header line + per-setup table; qualifying payments wrapped in `<span class="qual">`). New entries are prepended directly below the `<!-- NEWEST ENTRY GOES DIRECTLY BELOW THIS LINE -->` marker, newest first.
- Publishing: each job's final "PORTAL UPDATE" steps describe it. The worker edits the local working copy at `~/workspace/repos/vehicle/ev-deals/index.html`, then runs `python3 ~/workspace/repos/bandhu-portal/scripts/push_ev_deals.py`, which commits the page to this repo via the GitHub API. GitHub Pages rebuilds in about 1–2 minutes. No portal KV involved (the page moved off Cloudflare workers.dev on 2026-09-30).
