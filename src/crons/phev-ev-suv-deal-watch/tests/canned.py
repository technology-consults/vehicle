"""Canned agent results: full successful run + two regression cases.

REGRESSION 1: a rate that was advertised in the US only must be rejected as
unverified (verification_rules: market scope - a Canadian rate is required;
market_confirmed=false marks it unconfirmed).
REGRESSION 2: a calculator figure that disagrees with the deterministic math
by more than $3 must be treated as unverified (payment_match=false).
"""
RESEARCH = {
    "run_id": "__RUN_ID__",
    "offer_period": "10/01/2026 - 10/31/2026",
    "candidates": [
        {
            "make": "Kia", "model": "Niro EV", "trim": "Wind+",
            "above_base": True, "msrp": 48595.0, "mfr_rebate": 4000.0,
            "advertised": [
                {"kind": "lease", "rate_apr": 3.49, "term_hint": "48 mo",
                 "source_url": "https://www.kia.ca/en/offers/niro-ev"},
                {"kind": "finance", "rate_apr": 1.49,
                 "term_hint": "72 mo",
                 "source_url": "https://www.kia.ca/en/offers/niro-ev"},
            ],
            "source_url": "https://www.kia.ca/en/offers/niro-ev",
            "market_confirmed": True,
            "evap_eligible": True, "evap_path": "explicit-subtract",
            "notes": "1pt loyalty reduction available on lease (3.49% -> 2.49%)",
        },
        {
            "make": "Volkswagen", "model": "ID.4", "trim": "Pro RWD",
            "above_base": True, "msrp": 50499.0, "mfr_rebate": 5000.0,
            "advertised": [
                {"kind": "finance", "rate_apr": 0.99,
                 "term_hint": "72 mo",
                 "source_url": "https://www.vw.ca/en/offers/id4"},
            ],
            "source_url": "https://www.vw.ca/en/offers/id4",
            "market_confirmed": False,  # REGRESSION 1: market unconfirmed
            "evap_eligible": True, "evap_path": "explicit-subtract",
            "notes": "0.99% seen on US site; Canadian program unconfirmed",
        },
    ],
}

CALCULATORS = {
    "run_id": "__RUN_ID__",
    "configs": [
        {"candidate_index": 0, "config": "lease-48",
         "rate_apr": 2.49, "biweekly_payment": 189.49,
         "deep_link": "https://www.kia.ca/en/offers/niro-ev?lease=48",
         "url_notes": "province and trim in URL; term in page state",
         "calculator_applied_evap": False, "verified_live": True},
        {"candidate_index": 0, "config": "finance-72",
         "rate_apr": 1.49, "biweekly_payment": 232.5,
         "deep_link": "https://www.kia.ca/en/offers/niro-ev?finance=72",
         "url_notes": "", "calculator_applied_evap": False,
         "verified_live": True},
        {"candidate_index": 0, "config": "finance-84",
         "rate_apr": 1.99, "biweekly_payment": 999.0,  # REGRESSION 2: bogus
         "deep_link": "https://www.kia.ca/en/offers/niro-ev?finance=84",
         "url_notes": "", "calculator_applied_evap": False,
         "verified_live": True},
        {"candidate_index": 1, "config": "lease-48",
         "rate_apr": 0.0, "biweekly_payment": 0.0,
         "deep_link": "https://www.vw.ca/en/offers/id4",
         "url_notes": "", "calculator_applied_evap": False,
         "verified_live": False, "unavailable": True,
         "unavailable_reason": "no lease program published in Canada"},
        {"candidate_index": 1, "config": "finance-72",
         "rate_apr": 0.99, "biweekly_payment": 195.0,
         "deep_link": "https://www.vw.ca/en/offers/id4",
         "url_notes": "", "calculator_applied_evap": False,
         "verified_live": False},  # REGRESSION 1: not verified live
        {"candidate_index": 1, "config": "finance-84",
         "rate_apr": 0.0, "biweekly_payment": 0.0,
         "deep_link": "https://www.vw.ca/en/offers/id4",
         "url_notes": "", "calculator_applied_evap": False,
         "verified_live": False, "unavailable": True,
         "unavailable_reason": "no 84-mo program published"},
    ],
}

VERDICT = {
    "run_id": "__RUN_ID__",
    "verdict_line": "**1 deal** met all four criteria",
    "criteria_rows": [
        {"setting": "Offer period", "value": "10/01/2026 - 10/31/2026"},
        {"setting": "Scope", "value": "BEV SUV, Ontario"},
        {"setting": "Rate gate", "value": "below 3% APR"},
    ],
    "report_markdown": "**1 deal** met all four criteria\n",
    "deals": [{
        "header_text": "**2026 Kia Niro EV** - Wind+ trim",
        "options": [{
            "label": "Lease 48 mo / 20k km/yr",
            "link": "https://www.kia.ca/en/offers/niro-ev?lease=48",
            "rate_text": "**2.49%** (3.49% - 1pt loyalty)",
            "payment_text": "$189.49 bi-weekly",
            "qualifies": True,
        }],
        "notes": ["VW ID.4 0.99% was seen on the US site only - not "
                  "counted until a Canadian program is confirmed."],
    }],
}

DELIVER = {
    "run_id": "__RUN_ID__",
    "widget_token": "widget:mock-token-123",
    "timeline_logged": True,
}
