"""Unit tests: the manufacturer-preferred source rule for the rate scan.

Standing user rule (2026-10-02; refined same day): the rate-based scan
prefers manufacturer build-and-price configurators; dealership websites
are a fallback only within 50 km of L6Y 0Z4, Ontario.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import job_config as J


class SourceRulesTest(unittest.TestCase):
    def test_rule_text_prefers_manufacturer(self):
        text = J.source_rules().lower()
        self.assertIn("manufacturer", text)
        self.assertIn("dealer", text)
        self.assertIn("never", text)

    def test_rule_text_has_fallback_radius(self):
        text = J.source_rules()
        self.assertIn("50 km", text)
        self.assertIn("L6Y 0Z4", text)
        self.assertIn("dealer-sourced", text.lower())

    def test_research_prompt_carries_source_rule(self):
        prompt = J.research_task({"long_date": "Friday, October 2, 2026"})
        self.assertIn(J.source_rules(), prompt)

    def test_research_prompt_marks_missing_configurator_unverifiable(self):
        prompt = J.research_task({"long_date": "Friday, October 2, 2026"}).lower()
        self.assertIn("unverifiable", prompt)


if __name__ == "__main__":
    unittest.main()
