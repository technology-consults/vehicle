"""Unit tests: the manufacturer-only source rule for the payment scan.

Standing user rule (2026-10-02): the payment-only scan uses manufacturer
build-and-price configurators exclusively - dealership websites and dealer
mirrors are never opened, cited, or linked.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import job_config as J


class SourceRulesTest(unittest.TestCase):
    def test_rule_text_bans_dealer_sites(self):
        text = J.source_rules().lower()
        self.assertIn("manufacturer", text)
        self.assertIn("dealer", text)
        self.assertIn("never", text)

    def test_research_prompt_carries_source_rule(self):
        prompt = J.research_task({"long_date": "Friday, October 2, 2026"})
        self.assertIn(J.source_rules(), prompt)

    def test_research_prompt_marks_missing_configurator_unverifiable(self):
        prompt = J.research_task({"long_date": "Friday, October 2, 2026"}).lower()
        self.assertIn("unverifiable", prompt)


if __name__ == "__main__":
    unittest.main()
