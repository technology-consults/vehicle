"""Unit tests: deterministic portal-entry and widget HTML builders."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ev_common as C
import job_config as J


CRIT = [{"setting": "Offer period", "value": "10/01/2026 - 10/31/2026"},
        {"setting": "Rate gate", "value": "below 3% APR"}]
DEALS = [{"header_text": "**2026 Kia Niro EV** - Wind+ trim",
          "options": [
              {"label": "Lease 48 mo / 20k km/yr",
               "link": "https://www.kia.ca/en/offers/niro-ev?x=1",
               "rate_text": "**2.49%** (3.49% - 1pt loyalty)",
               "payment_text": "$189.49 bi-weekly", "qualifies": True},
              {"label": "Finance 72 mo",
               "link": "https://www.kia.ca/en/offers/niro-ev?x=2",
               "rate_text": "1.49%", "payment_text": "$231.96 bi-weekly",
               "qualifies": False},
          ],
          "notes": ["Above-base trim; MSRP $48,595 - $4,000 rebate."]}]

EXPECTED_PORTAL = """<article class="day" id="d2026-09-30">
  <header>
    <h2>Wednesday, September 30, 2026</h2>
    <span class="verdict"><strong>1 deal</strong> met all four criteria</span>
  </header>

  <details class="static">
    <summary>Match Criteria</summary>
    <table>
      <tr><td class="k">Offer period</td><td>10/01/2026 - 10/31/2026</td></tr>
      <tr><td class="k">Rate gate</td><td>below 3% APR</td></tr>
    </table>
  </details>

  <div class="deal">
    <div class="deal-head"><strong>Deal:</strong> <strong>2026 Kia Niro EV</strong> - Wind+ trim</div>
    <table class="opts">
      <tr><th>Option</th><th>Rate &rarr; bi-weekly payment</th></tr>
      <tr>
        <td><a href="https://www.kia.ca/en/offers/niro-ev?x=1">Lease 48 mo / 20k km/yr</a></td>
        <td class="pay"><strong>2.49%</strong> (3.49% - 1pt loyalty) &rarr; <span class="qual">$189.49 bi-weekly</span> - qualifies</td>
      </tr>
      <tr>
        <td><a href="https://www.kia.ca/en/offers/niro-ev?x=2">Finance 72 mo</a></td>
        <td class="pay">1.49% &rarr; $231.96 bi-weekly</td>
      </tr>
    </table>
    <p class="note">Above-base trim; MSRP $48,595 - $4,000 rebate.</p>
  </div>
</article>"""


class PortalEntryTest(unittest.TestCase):
    def test_matches_existing_page_markup(self):
        got = C.build_portal_entry(J, "d2026-09-30",
                                   "Wednesday, September 30, 2026",
                                   "**1 deal** met all four criteria",
                                   CRIT, DEALS)
        self.assertEqual(got, EXPECTED_PORTAL)

    def test_agent_text_is_escaped(self):
        evil = [{"header_text": "<script>alert(1)</script>",
                 "options": [{"label": "<b>l</b>",
                              "link": "https://example.com/",
                              "rate_text": "**x**", "payment_text": "<p>",
                              "qualifies": False}],
                 "notes": []}]
        got = C.build_portal_entry(J, "d2026-09-30", "t", "v", CRIT, evil)
        self.assertNotIn("<script>", got)
        self.assertIn("&lt;script&gt;", got)
        self.assertIn("<strong>x</strong>", got)  # bold still works

    def test_non_http_link_rejected(self):
        bad = [{"header_text": "h",
                "options": [{"label": "l", "link": "javascript:alert(1)",
                             "rate_text": "r", "payment_text": "p",
                             "qualifies": False}],
                "notes": []}]
        with self.assertRaises(ValueError):
            C.build_portal_entry(J, "d2026-09-30", "t", "v", CRIT, bad)


class WidgetTest(unittest.TestCase):
    def test_contains_criteria_and_theme_vars(self):
        got = C.build_widget_html(CRIT)
        self.assertIn("Match Criteria", got)
        self.assertIn("10/01/2026 - 10/31/2026", got)
        self.assertIn("var(--hatch-widget-text)", got)
        self.assertIn("var(--hatch-widget-muted)", got)
        self.assertIn("var(--hatch-widget-border)", got)
        self.assertIn("var(--hatch-widget-surface)", got)
        self.assertIn("<details", got)

    def test_escapes_agent_text(self):
        got = C.build_widget_html([{"setting": "<b>S</b>", "value": "<i>V</i>"}])
        self.assertNotIn("<b>", got)
        self.assertNotIn("<i>", got)


class HygieneTest(unittest.TestCase):
    def test_clean_report_passes(self):
        ok, _ = C.check_report_hygiene("**1 deal** met all four criteria\n\n")
        self.assertTrue(ok)

    def test_footers_flagged(self):
        for phrase in ("Task: cron fix 12", "cron pin", "approval request",
                       "for review", "versioned-cron"):
            ok, msg = C.check_report_hygiene("report text\n" + phrase)
            self.assertFalse(ok, phrase)
            self.assertIn("hygiene", msg)

    def test_case_insensitive(self):
        ok, _ = C.check_report_hygiene("Please see the For Review thread.")
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
