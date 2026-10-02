#!/usr/bin/env python3
"""Job config for phev-ev-suv-deal-watch (rate-based Ontario EV SUV scan).

Daily 08:00 America/Toronto. A deal must meet ALL four criteria:
  1. BEV SUV, trim above base (PHEVs/hybrids out of scope)
  2. Net price approx CAD $45,000 after manufacturer rebates
  3. Interest rate BELOW 3% APR
  4. Bi-weekly payment ($5,000 down, taxes in) in the $150-$200 band,
     on lease-48 / finance-72 / finance-84. Any config qualifying
     qualifies the deal.

This module holds everything that differs between the two EV scan jobs:
criteria text, thresholds, portal entry shape, and the four agent-step
prompts (research, calculators, verdict, deliver). The orchestration,
math, HTML building, and GitHub push live in ev_common.py.
"""
import json

import ev_common as C

JOB_ID = "phev-ev-suv-deal-watch"
TITLE = "EV SUV deal watch (Ontario)"
SCHEDULE_LABEL = "daily 08:00 America/Toronto"
CONFIGS = ["lease-48", "finance-72", "finance-84"]
CONFIG_LABELS = {
    "lease-48": "Lease 48 mo / 20k km/yr",
    "finance-72": "Finance 72 mo",
    "finance-84": "Finance 84 mo",
}
PORTAL_ID_SUFFIX = ""        # entry id: dYYYY-MM-DD
PORTAL_TITLE_SUFFIX = ""     # h2: just the long date
DELIVERY_CHAT = "de5d7ab8-9709-4e7c-a556-fd5f582b2f7e"  # SUV deal scan side chat

STEPS = ["research", "calculators", "verdict", "deliver"]


# --------------------------------------------------------------------------
# Mechanical qualification flags (deterministic; the verdict agent applies
# the remaining judgment: net ~= $45k, trim, near-misses).
# --------------------------------------------------------------------------
def qualify(config, rate_apr, biweekly):
    rate_ok = rate_apr < 3.0
    pay_ok = 150.0 <= biweekly <= 200.0
    return {"rate_ok": rate_ok,
            "payment_ok": pay_ok,
            "mechanical_qualifies": bool(rate_ok and pay_ok)}


# --------------------------------------------------------------------------
# Shared prompt blocks (plain words first)
# --------------------------------------------------------------------------
def worker_conduct():
    return (
        "WORKER CONDUCT (mandatory): Do ALL of this step yourself with your "
        "own tools: web search, page fetch/open, live browser tasks for site "
        "navigation and payment-calculator configuration, widget tools, "
        "chat/artifact tools. NEVER spawn subagents and NEVER delegate any "
        "part of this run to another agent: the scheduler-side worker has no "
        "durable chat owner for subagent follow-ups, and delegating kills the "
        "run before any report is produced. If the work feels like a lot for "
        "one pass, break it into sequential tool calls yourself - do not "
        "hand it off."
        "\n\nBROWSER FORM-SUBMIT RULE (standing user rule, 2026-10-02): "
        "never submit an HTML form or issue a POST request inside the live "
        "browser during this run - doing so fires an approval prompt to the "
        "user's phone, and a scheduled run must never surface an approval "
        "prompt. Do all searching and discovery with the web-search and "
        "page-fetch tools (browser_search, browser_open), never by typing "
        "into a site's search box and submitting it. Inside the live "
        "browser, navigate only by entering URLs directly and clicking "
        "links; payment-calculator configuration via URL-encoded options is "
        "fine. If a check genuinely requires a form submission, skip it and "
        "mark that check unverified instead of triggering the prompt. If a "
        "prompt appears anyway, do not wait on it - treat that step as "
        "blocked, mark it unverified, and continue the run.")


def loyalty_rules():
    return (
        "LOYALTY RATES (standing user rule): BalRam qualifies for Kia loyalty "
        "ONLY. For Kia vehicles, loyalty-reduced rates may be used - state the "
        "reduction explicitly (e.g. 2.49% = 3.49% base - 1-pt loyalty). For ALL "
        "other manufacturers, never use loyalty-discounted rates or loyalty "
        "checkbox options - evaluate only the publicly advertised non-loyalty "
        "rate. If a brand's advertised rate already bakes in a loyalty "
        "reduction (e.g. Hyundai's advertised rates bake in a 1% loyalty cut, "
        "so non-loyalty = advertised + 1pt), report the standard non-loyalty "
        "rate instead; if no non-loyalty rate is published, flag the candidate "
        "as failing the rate criterion. Mazda's advertised lease rates are "
        "already the non-loyalty rate (mazda.ca disclaimer verified "
        "2026-09-24; loyalty floors to 0%).")


def evap_context():
    return (
        "FEDERAL EV INCENTIVE (EVAP, corrected 2026-09-30, verified against "
        "Transport Canada): in 2026, up to $5,000 for battery-electric vehicles "
        "on a final transaction value of $50,000 or less (no cap for "
        "Canadian-made EVs); amounts step down each January 1 from 2027. "
        "Applied at point of sale by the dealer; a 48-month lease earns the "
        "full amount. For any candidate whose total price is below the cap, "
        "use the website's select-option/build-and-price step if available to "
        "apply the EVAP amount and FOLD it into the reported figures - the "
        "headline bi-weekly payment is what the buyer would actually pay (net "
        "price minus manufacturer rebate minus EVAP, then $5,000 down). Always "
        "note the pre-EVAP net price (after manufacturer rebates only) "
        "alongside the post-EVAP figures so the rebate's effect is visible. "
        "The rebate is applied EXACTLY ONCE per candidate: if the "
        "manufacturer's own calculator already applies the federal amount "
        "(e.g. Kia's EV-rebate checkbox), keep it and do NOT subtract it "
        "again; otherwise subtract the eligible amount explicitly. A candidate "
        "above the $50,000 cap, or otherwise ineligible, is shown WITHOUT the "
        "rebate and with a one-line reason - never force the rebate in. "
        "Ontario has no provincial rebate.")


def verification_rules():
    return (
        "VERIFICATION (mandatory - runs every time, BEFORE the report is "
        "written):\n"
        "1. Every rate, MSRP, rebate, and payment figure in the report must "
        "come from a page opened during THIS run. Baseline figures below may "
        "tell you where to look but never substitute for re-verification - if "
        "a page is unreachable, say so and mark the candidate unverified "
        "rather than carrying the old number forward.\n"
        "2. Market scope: every program cited must be confirmed as a Canadian "
        "(Ontario where applicable) offer. US, Korean, or European programs "
        "are never presented as Canadian. If a program's market is ambiguous, "
        "label it unconfirmed - do not generalize across markets.\n"
        "3. Measurement standards: when comparing specifications across "
        "sources (cargo volume, range, etc.), confirm both figures use the "
        "same standard (SAE vs VDA, EPA vs WLTP vs NRCan). If standards "
        "differ, convert to one ruler and label it, or show each with its "
        "standard marked - never present mixed-standard figures as a direct "
        "comparison.\n"
        "4. Inferences labeled: any business interpretation (e.g. 'looks like "
        "a clearance bonus', 'likely ends when...') is labeled as inference, "
        "not stated as fact.\n"
        "5. If any check in 1-4 cannot be completed for a figure, the report "
        "says so plainly instead of presenting the figure as verified.")


def links_rules():
    return (
        "LINKS (standing user rule): Do not share homepages or unconfigured "
        "offer pages. For each deal reported, navigate the manufacturer site, "
        "select Ontario, select the relevant EV SUV and deal, open the payment "
        "calculator, fill in BIWEEKLY frequency and $5,000 down - configuring "
        "LEASE at 48 months with 20,000 km/year allowance, and FINANCE at "
        "both 72 and 84 months - then copy the FINAL address-bar URL and "
        "share that. If the site encodes the selections (province, vehicle, "
        "payment frequency, term, down payment) in the URL, that deep link is "
        "ideal. If it does not (SPA/page-state only), still share the deepest "
        "resulting URL you reached - not the homepage - and briefly note "
        "which selections actually persisted in the URL versus page state "
        "(e.g. province baked in, payment config in page state). "
        "Toyota-style build codes that restore the full configuration are "
        "acceptable equivalents. Verify every URL you report by opening it - "
        "never invent or guess URLs.")


def criteria_text():
    return (
        "QUALIFYING CRITERIA (a deal must meet ALL of these):\n"
        "1. Vehicle: fully electric (BEV) SUV, trim ABOVE the base model. "
        "PHEVs and conventional hybrids are OUT OF SCOPE.\n"
        "2. Net price approx CAD $45,000 AFTER deducting any manufacturer "
        "rebate/cash incentive (note MSRP, rebate, and net price separately; "
        "freight/PDI/taxes excluded from the $45k comparison).\n"
        "3. Interest rate BELOW 3% APR (lease or finance - state which, plus "
        "term in months).\n"
        "4. Estimated BI-WEEKLY payment with $5,000 down in the $150-$200 "
        "band, taxes included, evaluated on THREE configurations per "
        "candidate: (a) LEASE at 48 months with 20,000 km/year allowance; "
        "(b) FINANCE at 72 months; (c) FINANCE at 84 months. A deal qualifies "
        "if ANY of the three configurations meets all criteria.")


def baseline_text():
    return (
        "BRANDS TO CHECK (EVs only): Hyundai, Kia, Toyota, Mitsubishi, Mazda, "
        "Subaru, Honda, Ford, Chevrolet, VW, Nissan.\n"
        "BASELINE from recent sweeps (tax-included bi-weekly, $5,000 down, "
        "Ontario - tells you where to look, NEVER a substitute for "
        "re-verification): 2026 Kia Niro EV Wind+ - lease ~$189.49 @ 2.49% "
        "(3.49% base - 1-pt loyalty), finance-72 ~$290.08 @ 1.49%; 2025 VW "
        "ID.4 Pro RWD - finance 0.99% at 72/84 mo, lease 0.00% at 24/36/48 mo "
        "($5,000 cash incentive); Subaru Solterra (1.49-1.99% lease); "
        "Chevrolet Equinox EV (6.9% lease / ~5.19% finance); Nissan Ariya "
        "(~3.40% lease / 6.90% finance); Ford Mustang Mach-E (6.49%); Hyundai "
        "Kona Electric Preferred (advertised 4.99% is loyalty-tied -> 5.99% "
        "non-loyalty); Honda Prologue (net ~$56,515 pre-EVAP); Toyota bZ "
        "(base trim, 6.89% lease). Mazda and Mitsubishi have no BEV SUV.")


# --------------------------------------------------------------------------
# Step prompts + schemas
# --------------------------------------------------------------------------
def research_task(state):
    return "\n\n".join([
        "You are the RESEARCH worker for the versioned cron job "
        "\"phev-ev-suv-deal-watch\" (Ontario EV SUV deal scan, RATE-BASED). "
        "Today is %s (America/Toronto)." % state["long_date"],
        worker_conduct(),
        "GOAL: research current manufacturer lease and finance special "
        "offers in ONTARIO, Canada for fully electric (BEV) SUVs/crossovers.",
        criteria_text(),
        loyalty_rules(),
        evap_context(),
        baseline_text(),
        verification_rules(),
        links_rules(),
        "RETURN: a single JSON object matching the schema in this request. "
        "Echo \"run_id\" back exactly as given. \"candidates\" lists every "
        "BEV SUV candidate you found advertised programs for - even "
        "unpromising ones (the verdict step decides). For each candidate, "
        "\"advertised\" records each advertised program (kind lease|finance, "
        "rate_apr, term_hint, source_url). \"offer_period\" is the programs' "
        "offer period as shown on the sites (e.g. \"09/01/2026 - "
        "09/30/2026\"). \"msrp\" and \"mfr_rebate\" are in CAD; "
        "\"evap_eligible\"/\"evap_path\" record your EVAP assessment per the "
        "rules above.",
    ])


def calculators_task(state):
    cands = state["research"]["candidates"]
    lines = []
    for i, c in enumerate(cands):
        lines.append(
            "[%d] %s %s (trim: %s, above_base=%s) MSRP $%s, rebate $%s, "
            "EVAP: eligible=%s path=%s; advertised=%s" % (
                i, c["make"], c["model"], c["trim"], c["above_base"],
                c["msrp"], c["mfr_rebate"], c["evap_eligible"],
                c["evap_path"],
                "; ".join("%s %s%% (%s)" % (a["kind"], a["rate_apr"],
                                            a["term_hint"])
                          for a in c["advertised"])))
    return "\n\n".join([
        "You are the CALCULATOR worker for the versioned cron job "
        "\"phev-ev-suv-deal-watch\" (Ontario EV SUV deal scan, RATE-BASED). "
        "Today is %s (America/Toronto)." % state["long_date"],
        worker_conduct(),
        "For EACH candidate below, open the manufacturer's payment "
        "calculator / build-and-price for Ontario and configure, with "
        "BI-WEEKLY frequency, $5,000 down, taxes included:\n"
        "  (a) LEASE: 48 months, 20,000 km/year allowance;\n"
        "  (b) FINANCE: 72 months;\n"
        "  (c) FINANCE: 84 months.\n"
        "Record the rate APR actually used, the headline bi-weekly payment, "
        "and the FINAL address-bar URL (deep link). Note whether the federal "
        "EV rebate was applied by the site's own calculator option "
        "(calculator_applied_evap=true) or not. Note which selections "
        "persisted in the URL versus page state (url_notes). If a "
        "configuration genuinely cannot be produced (no program, no "
        "calculator), mark unavailable=true with the reason - never invent "
        "a payment.",
        loyalty_rules(),
        evap_context(),
        links_rules(),
        "CANDIDATES (from the research step):\n" + "\n".join(lines),
        "RETURN: a single JSON object matching the schema in this request - "
        "one entry per (candidate, config). Echo \"run_id\" back exactly as "
        "given.",
    ])


def verdict_task(state):
    table = json.dumps(state["computed"], indent=1, sort_keys=True)
    return "\n\n".join([
        "You are the VERDICT worker for the versioned cron job "
        "\"phev-ev-suv-deal-watch\" (Ontario EV SUV deal scan, RATE-BASED). "
        "Today is %s (America/Toronto)." % state["long_date"],
        worker_conduct(),
        "Judge the scan results and write the report. Do not redo the "
        "research - the figures below were gathered live this run.",
        "MECHANICAL RESULTS (computed deterministically from the research + "
        "calculator figures - do not recompute; use the flags):\n" + table,
        "Flag meanings: rate_ok = APR below 3%%; payment_ok = bi-weekly in "
        "$150-$200; mechanical_qualifies = both. script_biweekly is an "
        "independent recomputation of finance payments (principal = net - "
        "EVAP - $5,000 down, amortized at the stated APR; bi-weekly = "
        "monthly x 12/26); payment_match=false means the calculator figure "
        "disagrees with the math by more than $3 - treat such figures as "
        "unverified unless you can justify the gap (fees, taxes). Lease "
        "payments come from the site calculators and cannot be recomputed. "
        "evap_how tells you how the $5,000 federal incentive was applied "
        "(site-applied vs explicitly-subtracted vs ineligible) - it is "
        "applied exactly once, never double-counted.",
        "YOUR JUDGMENT:\n"
        "- Apply the remaining criteria: net price approx $45,000 after "
        "manufacturer rebates, trim above base. \"Approx\" is your call - "
        "state it plainly.\n"
        "- A deal qualifies when ANY configuration meets all four criteria.\n"
        "- If NO deal qualifies: say so plainly, then list up to 3 "
        "near-misses (failing one criterion but unusually good; bi-weekly up "
        "to a $260 MAX on any configuration).\n"
        "- Inferences must be labeled as inference, not stated as fact.",
        "DELIVERY HYGIENE (standing rule): the report carries ONLY the deal "
        "report - never append housekeeping footers, approval requests, or "
        "task notes.",
        "FORMAT:\n"
        "- verdict_line: one line, e.g. \"**1 deal** met all four criteria\" "
        "(use **bold** around the leading count).\n"
        "- criteria_rows: the Match Criteria panel rows (Setting/Value "
        "objects), updating Offer period to what you found this run.\n"
        "- report_markdown: the DEALS section in markdown - the deal-level "
        "verdict line first, then one bold group header per deal "
        "(Model/Trim, MSRP, rebate, net pre-EVAP -> post-EVAP), then a "
        "per-option table with exactly TWO columns (Option | Rate -> "
        "bi-weekly payment); the Option cell is a short labeled markdown "
        "link to the deep link; bold the qualifying payment (that bolding "
        "alone marks qualification - no status column).\n"
        "- deals: the same deals as structured data for the portal page - "
        "header_text (may use **bold**), options (label, link, rate_text, "
        "payment_text, qualifies), notes (plain strings).",
        "RETURN: a single JSON object matching the schema in this request. "
        "Echo \"run_id\" back exactly as given.",
    ])


def deliver_task(state):
    widget_html = C.build_widget_html(state["verdict"]["criteria_rows"])
    v = state["verdict"]
    portal = state["portal"]
    if portal.get("dry_run"):
        portal_note = "portal push ran in DRY-RUN mode (no commit made)"
    else:
        portal_note = ("portal entry pushed (commit %s, Pages build %s)"
                       % (portal.get("commit_sha", "?")[:7],
                          portal.get("pages_build")))
    timeline_line = ("%s %s: %s; %s."
                     % (JOB_ID, state["run_date"], v["verdict_line"],
                        portal_note))
    return "\n\n".join([
        "You are the DELIVERY worker for the versioned cron job "
        "\"phev-ev-suv-deal-watch\" (Ontario EV SUV deal scan, RATE-BASED). "
        "Today is %s (America/Toronto)." % state["long_date"],
        worker_conduct(),
        "Two small steps, both with your own tools - then you are done:\n"
        "1. Create the Match Criteria widget: call widget.create (kind "
        "\"html\", fallback_text \"Match criteria\") with EXACTLY this "
        "HTML:\n" + widget_html + "\n"
        "Return the widget token it gives you.\n"
        "2. Log the run outcome to the goal timeline: call "
        "user_goal.create_entry on goal \"%s\" with EXACTLY this text:\n"
        "%s" % (C.GOAL_ID, timeline_line),
        "DELIVERY HYGIENE (standing rule): the chat report carries ONLY the "
        "deal report - the widget token and report below are the whole "
        "message; housekeeping (this timeline entry, the portal push) stays "
        "out of it.",
        "RETURN: a single JSON object matching the schema in this request: "
        "run_id (echo it back exactly), widget_token, timeline_logged "
        "(true only if the timeline entry was actually created).",
    ])


def build_step_request(step, state, correction=None):
    """Return (task, schema) for a step. correction prepends a fix notice."""
    builders = {
        "research": (research_task, C.research_schema),
        "calculators": (calculators_task,
                        lambda: C.calculators_schema(CONFIGS)),
        "verdict": (verdict_task, C.verdict_schema),
        "deliver": (deliver_task, C.deliver_schema),
    }
    task_fn, schema_fn = builders[step]
    task = task_fn(state)
    if correction:
        task = ("CORRECTION NEEDED - your last result for this step was "
                "rejected:\n%s\n\nPlease redo the step and return a result "
                "that fixes the problem above. Everything below still "
                "applies.\n\n" % correction) + task
    return task, schema_fn()


def validate_step_result(step, result, state):
    """Extra checks beyond the JSON schema. Returns (ok, error_message)."""
    if step == "calculators":
        return C.validate_calculators(CONFIGS, state["research"], result)
    if step == "verdict":
        return C.check_report_hygiene(result.get("report_markdown", ""))
    if step == "deliver":
        if result.get("timeline_logged") is not True:
            return False, "timeline_logged must be true: the goal-timeline " \
                          "entry has to be created before finishing."
        return True, ""
    return True, ""
