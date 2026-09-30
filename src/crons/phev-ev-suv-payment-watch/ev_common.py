#!/usr/bin/env python3
"""Shared deterministic library for the Ontario EV-SUV deal-scan cron jobs.

Vendored IDENTICALLY into:
  src/crons/phev-ev-suv-deal-watch/ev_common.py
  src/crons/phev-ev-suv-payment-watch/ev_common.py
If you change this file, apply the byte-identical change to both copies.
(Per-job release tarballs are self-contained: each package carries its own
copy. There is deliberately no cross-job import.)

Contents:
  - handshake helpers (agent-request emission, exit codes, round budget)
  - minimal JSON-schema validator (stdlib only)
  - payment math (finance amortization, EVAP exactly-once rule)
  - mechanical qualification-flag helpers
  - deterministic HTML builders (portal entry, chat Match-Criteria widget)
  - report-hygiene check (deal alerts carry ONLY the deal report)
  - GitHub API portal push (contents API only)
  - run-state helpers (state survives across handshake re-invocations)

BANNED: raw.githubusercontent.com - fetching it triggers a phone approval
prompt (BalRam 2026-09-30: same violation as using the browser for GitHub).
All GitHub reads go through https://api.github.com (contents API, git trees
API, tarball endpoint). See scripts/enforce/no_raw_github.py.
"""
import base64
import html
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python < 3.9 fallback
    ZoneInfo = None

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
API = "https://api.github.com"
PORTAL_REPO = "technology-consults/vehicle"
PORTAL_PATH = "ev-deals/index.html"
PORTAL_MARKER = "NEWEST ENTRY GOES DIRECTLY BELOW THIS LINE"

HANDSHAKE_EXIT = 10   # run.py -> runner: "I need an agent step"
MAX_ROUNDS = 5        # handshake rounds before failing loudly
FAIL_EXIT = 1         # any other non-zero exit is a plain (loud) failure

AGENT_REQ_BEGIN = "@@AGENT-REQUEST-BEGIN@@"
AGENT_REQ_END = "@@AGENT-REQUEST-END@@"

TORONTO_TZ = "America/Toronto"
EVAP_BEV_2026 = 5000.0      # federal EV incentive, BEV, 2026 (corrected 2026-09-30)
EVAP_CAP = 50000.0          # final transaction value cap; Canadian-made exempt
DOWN_PAYMENT = 5000.0
PAYMENT_TOLERANCE = 3.0     # $ tolerance: agent calculator figure vs script math

GOAL_ID = "goal_e8a8f8022330"

CONFIG_TERMS = {"lease-48": 48, "finance-72": 72, "finance-84": 84}

# Standing delivery-hygiene rule (2026-09-30): deal alerts carry ONLY the
# deal report - no housekeeping footers, approval requests, or task notes.
HYGIENE_DENYLIST = (
    "approval request", "for review", "task:", "cron fix", "cron pin",
    "pin flip", "versioned-cron", "housekeeping",
)

sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
try:
    from dynamic_credentials import add_surrogate_to_request
except ImportError:  # pragma: no cover - lets unit tests run w/o the surrogate
    add_surrogate_to_request = None


# --------------------------------------------------------------------------
# Loud failure
# --------------------------------------------------------------------------
def fail_loud(msg):
    """Fail loudly: never deliver a partial result as final, never swallow."""
    print("JOB FAILED (loud, no partial delivery): %s" % msg, file=sys.stderr)
    raise SystemExit(FAIL_EXIT)


# --------------------------------------------------------------------------
# Handshake
# --------------------------------------------------------------------------
def emit_request(task, schema, run_id, job_id, step, attempt):
    """Print the agent-request block and exit 10 (handshake)."""
    req = {"need": "agent-step",
           "task": task,
           "schema": schema,
           "attempt": attempt,
           "run_id": run_id,
           "job": job_id,
           "step": step}
    print(AGENT_REQ_BEGIN)
    print(json.dumps(req, indent=2, sort_keys=True))
    print(AGENT_REQ_END)
    raise SystemExit(HANDSHAKE_EXIT)


# --------------------------------------------------------------------------
# Minimal JSON-schema validator (stdlib only)
# --------------------------------------------------------------------------
class SchemaError(Exception):
    pass


def validate_against_schema(data, schema, path="$"):
    """Validate data against a small subset of JSON Schema.

    Supports: type (object/array/string/number/integer/boolean), required,
    properties, items, enum, minimum, maximum, minLength, minItems.
    Raises SchemaError with a JSON-path-style location on mismatch.
    """
    stype = schema.get("type")
    if stype == "object":
        if not isinstance(data, dict):
            raise SchemaError("%s: expected object, got %s"
                              % (path, type(data).__name__))
        for req_key in schema.get("required", []):
            if req_key not in data:
                raise SchemaError("%s: missing required field %r"
                                  % (path, req_key))
        for key, subschema in schema.get("properties", {}).items():
            if key in data:
                validate_against_schema(data[key], subschema,
                                        "%s.%s" % (path, key))
    elif stype == "array":
        if not isinstance(data, list):
            raise SchemaError("%s: expected array, got %s"
                              % (path, type(data).__name__))
        if "minItems" in schema and len(data) < schema["minItems"]:
            raise SchemaError("%s: expected at least %d items, got %d"
                              % (path, schema["minItems"], len(data)))
        item_schema = schema.get("items", {})
        for i, item in enumerate(data):
            validate_against_schema(item, item_schema, "%s[%d]" % (path, i))
    elif stype == "string":
        if not isinstance(data, str):
            raise SchemaError("%s: expected string, got %s"
                              % (path, type(data).__name__))
        if "minLength" in schema and len(data) < schema["minLength"]:
            raise SchemaError("%s: string shorter than minLength %d"
                              % (path, schema["minLength"]))
        if "enum" in schema and data not in schema["enum"]:
            raise SchemaError("%s: %r not in enum %r"
                              % (path, data, schema["enum"]))
    elif stype == "number":
        if isinstance(data, bool) or not isinstance(data, (int, float)):
            raise SchemaError("%s: expected number, got %s"
                              % (path, type(data).__name__))
        if "minimum" in schema and data < schema["minimum"]:
            raise SchemaError("%s: %r below minimum %r"
                              % (path, data, schema["minimum"]))
        if "maximum" in schema and data > schema["maximum"]:
            raise SchemaError("%s: %r above maximum %r"
                              % (path, data, schema["maximum"]))
    elif stype == "integer":
        if isinstance(data, bool) or not isinstance(data, int):
            raise SchemaError("%s: expected integer, got %s"
                              % (path, type(data).__name__))
        if "minimum" in schema and data < schema["minimum"]:
            raise SchemaError("%s: %r below minimum %r"
                              % (path, data, schema["minimum"]))
        if "maximum" in schema and data > schema["maximum"]:
            raise SchemaError("%s: %r above maximum %r"
                              % (path, data, schema["maximum"]))
    elif stype == "boolean":
        if not isinstance(data, bool):
            raise SchemaError("%s: expected boolean, got %s"
                              % (path, type(data).__name__))
    else:
        raise SchemaError("%s: unsupported schema type %r" % (path, stype))
    return True


# --------------------------------------------------------------------------
# Agent-result schemas (parameterized by the job's config list)
# --------------------------------------------------------------------------
def research_schema():
    return {
        "type": "object",
        "required": ["run_id", "offer_period", "candidates"],
        "properties": {
            "run_id": {"type": "string", "minLength": 1},
            "offer_period": {"type": "string", "minLength": 1},
            "candidates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["make", "model", "trim", "above_base",
                                 "msrp", "mfr_rebate", "advertised",
                                 "source_url", "market_confirmed",
                                 "evap_eligible", "evap_path", "notes"],
                    "properties": {
                        "make": {"type": "string", "minLength": 1},
                        "model": {"type": "string", "minLength": 1},
                        "trim": {"type": "string", "minLength": 1},
                        "above_base": {"type": "boolean"},
                        "msrp": {"type": "number", "minimum": 0},
                        "mfr_rebate": {"type": "number", "minimum": 0},
                        "advertised": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["kind", "rate_apr",
                                             "term_hint", "source_url"],
                                "properties": {
                                    "kind": {"type": "string",
                                             "enum": ["lease", "finance"]},
                                    "rate_apr": {"type": "number",
                                                 "minimum": 0},
                                    "term_hint": {"type": "string"},
                                    "source_url": {"type": "string",
                                                   "minLength": 1},
                                },
                            },
                        },
                        "source_url": {"type": "string", "minLength": 1},
                        "market_confirmed": {"type": "boolean"},
                        "evap_eligible": {"type": "boolean"},
                        "evap_path": {"type": "string",
                                      "enum": ["site-applied",
                                               "explicit-subtract",
                                               "ineligible"]},
                        "notes": {"type": "string"},
                    },
                },
            },
        },
    }


def calculators_schema(configs):
    return {
        "type": "object",
        "required": ["run_id", "configs"],
        "properties": {
            "run_id": {"type": "string", "minLength": 1},
            "configs": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "required": ["candidate_index", "config", "rate_apr",
                                 "biweekly_payment", "deep_link", "url_notes",
                                 "calculator_applied_evap", "verified_live"],
                    "properties": {
                        "candidate_index": {"type": "integer", "minimum": 0},
                        "config": {"type": "string", "enum": list(configs)},
                        "rate_apr": {"type": "number", "minimum": 0},
                        "biweekly_payment": {"type": "number", "minimum": 0},
                        "deep_link": {"type": "string", "minLength": 1},
                        "url_notes": {"type": "string"},
                        "calculator_applied_evap": {"type": "boolean"},
                        "verified_live": {"type": "boolean"},
                        "unavailable": {"type": "boolean"},
                        "unavailable_reason": {"type": "string"},
                    },
                },
            },
        },
    }


def verdict_schema():
    option_schema = {
        "type": "object",
        "required": ["label", "link", "rate_text", "payment_text",
                     "qualifies"],
        "properties": {
            "label": {"type": "string", "minLength": 1},
            "link": {"type": "string", "minLength": 1},
            "rate_text": {"type": "string"},
            "payment_text": {"type": "string", "minLength": 1},
            "qualifies": {"type": "boolean"},
        },
    }
    return {
        "type": "object",
        "required": ["run_id", "verdict_line", "criteria_rows",
                     "report_markdown", "deals"],
        "properties": {
            "run_id": {"type": "string", "minLength": 1},
            "verdict_line": {"type": "string", "minLength": 1},
            "criteria_rows": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "required": ["setting", "value"],
                    "properties": {
                        "setting": {"type": "string", "minLength": 1},
                        "value": {"type": "string"},
                    },
                },
            },
            "report_markdown": {"type": "string", "minLength": 1},
            "deals": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["header_text", "options", "notes"],
                    "properties": {
                        "header_text": {"type": "string", "minLength": 1},
                        "options": {"type": "array", "minItems": 1,
                                    "items": option_schema},
                        "notes": {"type": "array",
                                  "items": {"type": "string"}},
                    },
                },
            },
        },
    }


def deliver_schema():
    return {
        "type": "object",
        "required": ["run_id", "widget_token", "timeline_logged"],
        "properties": {
            "run_id": {"type": "string", "minLength": 1},
            "widget_token": {"type": "string", "minLength": 1},
            "timeline_logged": {"type": "boolean"},
        },
    }


# --------------------------------------------------------------------------
# Payment math
# --------------------------------------------------------------------------
def finance_monthly(principal, apr, term_months):
    """Amortized monthly payment. principal<0 is clamped to 0."""
    if term_months <= 0:
        raise ValueError("term_months must be positive")
    principal = max(0.0, float(principal))
    r = float(apr) / 100.0 / 12.0
    n = int(term_months)
    if r == 0:
        return principal / n
    return principal * r / (1.0 - (1.0 + r) ** (-n))


def finance_biweekly(principal, apr, term_months):
    """Bi-weekly payment = monthly x 12 / 26."""
    return finance_monthly(principal, apr, term_months) * 12.0 / 26.0


def evap_for_candidate(candidate, calculator_applied_evap):
    """EVAP exactly-once rule. Returns (amount, how).

    The calculator's own observation wins: if the site's calculator already
    applied the federal amount, it is kept and never subtracted again.
    Otherwise the eligible amount is subtracted explicitly. Ineligible
    candidates get 0 with a reason - the rebate is never forced in.
    """
    if not candidate.get("evap_eligible") or \
            candidate.get("evap_path") == "ineligible":
        return 0.0, "ineligible"
    if calculator_applied_evap:
        return EVAP_BEV_2026, "site-applied"
    return EVAP_BEV_2026, "explicitly-subtracted"


def compute_table(job_config, research, calc_results):
    """Deterministic math interlude between the calculators and verdict steps.

    For every (candidate, config): net price, EVAP exactly-once, finance
    amortization cross-check against the agent's calculator figure, and the
    job's mechanical qualification flags. Lease payments cannot be
    recomputed (no residual) - they stay calculator-sourced.
    """
    candidates = research["candidates"]
    rows = []
    for cfg in calc_results["configs"]:
        idx = cfg["candidate_index"]
        if idx >= len(candidates):
            raise IndexError("candidate_index %d out of range (%d "
                             "candidates)" % (idx, len(candidates)))
        cand = candidates[idx]
        net = float(cand["msrp"]) - float(cand["mfr_rebate"])
        row = {"candidate_index": idx,
               "config": cfg["config"],
               "make": cand["make"],
               "model": cand["model"],
               "trim": cand["trim"],
               "net_pre_evap": round(net, 2),
               "verified_live": bool(cfg["verified_live"]),
               "deep_link": cfg["deep_link"]}
        if cfg.get("unavailable"):
            row["unavailable"] = True
            row["unavailable_reason"] = cfg.get("unavailable_reason", "")
            rows.append(row)
            continue
        row["unavailable"] = False
        evap, how = evap_for_candidate(cand, cfg["calculator_applied_evap"])
        row["evap_applied"] = evap
        row["evap_how"] = how
        if cand.get("evap_eligible") and cand.get("evap_path") != how and \
                how != "ineligible":
            row["evap_path_note"] = (
                "research assessed evap_path=%r but the calculator %s the "
                "rebate; calculator observation wins"
                % (cand.get("evap_path"),
                   "applied" if cfg["calculator_applied_evap"] else "did not apply"))
        principal = max(0.0, net - evap - DOWN_PAYMENT)
        row["principal"] = round(principal, 2)
        row["agent_rate_apr"] = cfg["rate_apr"]
        row["agent_biweekly"] = cfg["biweekly_payment"]
        term = CONFIG_TERMS[cfg["config"]]
        if cfg["config"].startswith("finance"):
            script_bi = finance_biweekly(principal, cfg["rate_apr"], term)
            row["script_biweekly"] = round(script_bi, 2)
            row["payment_match"] = (
                abs(script_bi - cfg["biweekly_payment"]) <= PAYMENT_TOLERANCE)
        else:
            row["script_biweekly"] = None
            row["payment_match"] = None  # lease: calculator-sourced
        row["flags"] = job_config.qualify(cfg["config"], cfg["rate_apr"],
                                          cfg["biweekly_payment"])
        rows.append(row)
    return rows


def validate_calculators(configs, research, result):
    """Every candidate must have every required config (or be marked
    unavailable with a reason). Returns (ok, error_message)."""
    n = len(research["candidates"])
    seen = {}
    for cfg in result["configs"]:
        idx = cfg["candidate_index"]
        if idx >= n:
            return False, ("candidate_index %d out of range: only %d "
                           "candidate(s) from the research step" % (idx, n))
        seen.setdefault(idx, set()).add(cfg["config"])
    missing = []
    for i in range(n):
        for c in configs:
            if c not in seen.get(i, set()):
                missing.append("candidate %d missing config %s" % (i, c))
    if missing:
        return False, ("incomplete calculator coverage: " +
                       "; ".join(missing) +
                       ". Configure every config for every candidate, or "
                       "mark it unavailable=true with unavailable_reason.")
    return True, ""


# --------------------------------------------------------------------------
# Deterministic HTML builders
# --------------------------------------------------------------------------
def _md_bold_to_html(text):
    """Escape HTML, then convert **bold** markers to <strong>."""
    esc = html.escape(text or "")
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc)


def _check_link(link):
    if not re.match(r"^https?://", link or ""):
        raise ValueError("refusing non-http(s) link: %r" % (link,))
    return html.escape(link, quote=True)


def build_portal_entry(job_config, entry_id, h2_title, verdict_line,
                       criteria_rows, deals):
    """Build one <article class="day"> portal entry, newest-first markup.

    Mirrors the existing entries in ev-deals/index.html exactly:
    header (h2 + verdict), Match Criteria <details>, one .deal block per
    deal with a per-option table, qualifying payments in <span class="qual">.
    All agent-supplied text is HTML-escaped; **bold** becomes <strong>.
    """
    crit = "\n".join(
        '      <tr><td class="k">%s</td><td>%s</td></tr>'
        % (html.escape(r["setting"]), html.escape(r["value"]))
        for r in criteria_rows)
    parts = []
    for deal in deals:
        rows = []
        for opt in deal["options"]:
            link = _check_link(opt["link"])
            label = html.escape(opt["label"])
            rate = _md_bold_to_html(opt["rate_text"])
            pay = html.escape(opt["payment_text"])
            if opt["qualifies"]:
                cell = '%s &rarr; <span class="qual">%s</span> - qualifies' \
                       % (rate, pay)
            else:
                cell = '%s &rarr; %s' % (rate, pay)
            rows.append(
                "      <tr>\n"
                '        <td><a href="%s">%s</a></td>\n'
                '        <td class="pay">%s</td>\n'
                "      </tr>" % (link, label, cell))
        notes = "\n".join(
            '    <p class="note">%s</p>' % _md_bold_to_html(n)
            for n in deal.get("notes", []))
        parts.append(
            '  <div class="deal">\n'
            '    <div class="deal-head"><strong>Deal:</strong> %s</div>\n'
            '    <table class="opts">\n'
            "      <tr><th>Option</th><th>Rate &rarr; bi-weekly payment</th></tr>\n"
            "%s\n"
            "    </table>\n"
            "%s\n"
            "  </div>" % (_md_bold_to_html(deal["header_text"]),
                          "\n".join(rows),
                          notes))
    return (
        '<article class="day" id="%s">\n'
        "  <header>\n"
        "    <h2>%s</h2>\n"
        '    <span class="verdict">%s</span>\n'
        "  </header>\n"
        "\n"
        '  <details class="static">\n'
        "    <summary>Match Criteria</summary>\n"
        "    <table>\n"
        "%s\n"
        "    </table>\n"
        "  </details>\n"
        "\n"
        "%s\n"
        "</article>"
        % (html.escape(entry_id), html.escape(h2_title),
           _md_bold_to_html(verdict_line), crit, "\n\n".join(parts)))


def build_widget_html(criteria_rows):
    """Build the Match Criteria chat widget HTML (theme-aware)."""
    cell_a = ("padding:4px 8px 4px 0;color:var(--hatch-widget-muted);"
              "white-space:nowrap;vertical-align:top;")
    cell_b = "padding:4px 0;vertical-align:top;"
    rows = "".join(
        '<tr><td style="%s">%s</td><td style="%s">%s</td></tr>'
        % (cell_a, html.escape(r["setting"]), cell_b,
           html.escape(r["value"]))
        for r in criteria_rows)
    return (
        '<div style="box-sizing:border-box;max-width:100%;'
        'color:var(--hatch-widget-text);font-size:13px;line-height:1.45;">'
        '<details style="border:1px solid var(--hatch-widget-border);'
        'border-radius:10px;background:var(--hatch-widget-surface);">'
        '<summary style="cursor:pointer;padding:10px 12px;font-weight:600;">'
        "Match Criteria</summary>"
        '<div style="padding:0 12px 12px;">'
        '<table style="width:100%;border-collapse:collapse;font-size:12px;">'
        "<tbody>" + rows + "</tbody></table></div></details></div>")


def check_report_hygiene(markdown):
    """Standing rule: the alert carries ONLY the deal report.

    Returns (ok, error_message)."""
    low = (markdown or "").lower()
    hits = [p for p in HYGIENE_DENYLIST if p in low]
    if hits:
        return False, (
            "delivery-hygiene violation: the report contains housekeeping "
            "language (%s). The alert carries ONLY the deal report - move "
            "housekeeping to the goal timeline, never into the message."
            % ", ".join(hits))
    return True, ""


# --------------------------------------------------------------------------
# GitHub API (contents API only - raw.githubusercontent.com is banned)
# --------------------------------------------------------------------------
def _auth_request(req):
    if add_surrogate_to_request is None:
        fail_loud("credential surrogate unavailable: cannot authenticate "
                  "to api.github.com")
    add_surrogate_to_request(req, "custom.github",
                             allowed_hosts=["api.github.com"])


def api_get(path):
    req = urllib.request.Request(
        API + path, method="GET",
        headers={"User-Agent": "muse-ev-deals",
                 "Accept": "application/vnd.github+json"})
    _auth_request(req)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        fail_loud("GitHub GET %s: HTTP %s %s"
                  % (path, e.code, e.read().decode()[:200]))


def api_put(path, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        API + path, data=data, method="PUT",
        headers={"User-Agent": "muse-ev-deals",
                 "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json"})
    _auth_request(req)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        fail_loud("GitHub PUT %s: HTTP %s %s"
                  % (path, e.code, e.read().decode()[:200]))


def wait_for_pages_build(commit_sha, timeout_s=180, interval_s=15):
    """Poll the Pages build until it reaches 'built' for our commit.

    An API 200 on the push is not a successful deploy - verify the build.
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        build = api_get("/repos/%s/pages/builds/latest" % PORTAL_REPO)
        if build.get("commit") == commit_sha:
            status = build.get("status")
            if status == "built":
                return "built"
            if status == "errored":
                fail_loud("Pages build errored for commit %s: %s"
                          % (commit_sha[:7], build.get("error", {}).get(
                              "message", "unknown")))
        time.sleep(interval_s)
    fail_loud("Pages build did not reach 'built' for commit %s within %ds"
              % (commit_sha[:7], timeout_s))


def push_portal_entry(job_config, entry_id, article_html, dry_run=False):
    """Prepend the new entry to ev-deals/index.html via the GitHub API.

    Read-modify-write: fetch the current page + blob sha, sanity-check the
    newest-entry marker, insert directly below it, PUT with the sha, then
    verify the Pages build. In dry-run mode nothing is pushed; the article
    is recorded under the state dir for tests.
    """
    cur = api_get("/repos/%s/contents/%s?ref=main" % (PORTAL_REPO,
                                                      PORTAL_PATH))
    content = base64.b64decode(cur["content"]).decode("utf-8")
    sha = cur["sha"]
    if PORTAL_MARKER not in content:
        fail_loud("portal page sanity check failed: newest-entry marker "
                  "missing; push aborted")
    new_content = content.replace(PORTAL_MARKER,
                                  PORTAL_MARKER + "\n\n" + article_html, 1)
    if dry_run:
        path = os.path.join(state_dir(),
                            "portal_dryrun_%s.html" % entry_id)
        with open(path, "w") as fh:
            fh.write(article_html)
        return {"dry_run": True, "sha": sha,
                "artifact": path, "pages_build": "skipped"}
    payload = {"message": "EV deals: %s entry %s"
                         % (job_config.JOB_ID, entry_id),
               "content": base64.b64encode(new_content.encode()).decode(),
               "sha": sha,
               "branch": "main"}
    resp = api_put("/repos/%s/contents/%s" % (PORTAL_REPO, PORTAL_PATH),
                   payload)
    commit_sha = resp["commit"]["sha"]
    build_status = wait_for_pages_build(commit_sha)
    return {"dry_run": False, "commit_sha": commit_sha,
            "pages_build": build_status}


# --------------------------------------------------------------------------
# Run state (survives across handshake re-invocations)
# --------------------------------------------------------------------------
def state_dir():
    d = os.environ.get("EVDEALS_STATE_DIR") or os.path.join(
        os.path.expanduser("~"), ".cron_runner", "job_state")
    os.makedirs(d, exist_ok=True)
    return d


def state_path(job_id, run_id):
    safe_job = re.sub(r"[^a-z0-9_-]", "_", job_id)
    safe_run = re.sub(r"[^a-z0-9_-]", "_", run_id)
    return os.path.join(state_dir(), "%s__%s.json" % (safe_job, safe_run))


def save_state(job_id, state):
    with open(state_path(job_id, state["run_id"]), "w") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)


def load_state(job_id, run_id):
    try:
        with open(state_path(job_id, run_id)) as fh:
            return json.load(fh)
    except (OSError, ValueError) as e:
        fail_loud("cannot load run state for run_id %r: %s. The handshake "
                  "state was lost; failing loudly instead of guessing."
                  % (run_id, e))


def new_run_id():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return "%s-%s" % (stamp, os.urandom(4).hex())


def cleanup_stale_state(max_age_days=7):
    """Best-effort removal of state files older than max_age_days."""
    try:
        root = state_dir()
    except OSError:
        return
    cutoff = time.time() - max_age_days * 86400
    try:
        for name in os.listdir(root):
            if "__" not in name or not name.endswith(".json"):
                continue
            path = os.path.join(root, name)
            try:
                if os.path.getmtime(path) < cutoff:
                    os.unlink(path)
            except OSError:
                pass
    except OSError:
        pass


def today_toronto():
    if ZoneInfo is not None:
        return datetime.now(ZoneInfo(TORONTO_TZ))
    return datetime.now(timezone.utc)  # pragma: no cover - fallback


def long_date(dt):
    return dt.strftime("%A, %B %d, %Y")
