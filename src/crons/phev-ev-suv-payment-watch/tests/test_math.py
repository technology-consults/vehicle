"""Unit tests: payment math, EVAP exactly-once rule, qualification flags."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ev_common as C
import job_config as J


class FinanceMathTest(unittest.TestCase):
    # Expected values computed independently with Decimal (28-digit
    # precision) from the closed-form amortization formula; they pin the
    # float implementation against regression.
    def test_finance_72(self):
        self.assertAlmostEqual(C.finance_biweekly(34595, 1.49, 72),
                               231.96085730221338, places=6)

    def test_finance_84(self):
        self.assertAlmostEqual(C.finance_biweekly(34595, 1.99, 84),
                               203.78624178277877, places=6)

    def test_zero_apr(self):
        self.assertAlmostEqual(C.finance_biweekly(26000, 0, 72),
                               26000 / 72 * 12 / 26, places=9)

    def test_biweekly_conversion(self):
        # bi-weekly = monthly * 12 / 26, not monthly / 2
        m = C.finance_monthly(34595, 1.49, 72)
        self.assertAlmostEqual(C.finance_biweekly(34595, 1.49, 72),
                               m * 12 / 26, places=9)

    def test_negative_principal_clamped(self):
        self.assertEqual(C.finance_biweekly(-100, 5.0, 72), 0.0)


class EvapTest(unittest.TestCase):
    def _cand(self, eligible=True, path="explicit-subtract"):
        return {"evap_eligible": eligible, "evap_path": path}

    def test_explicit_subtract(self):
        amt, how = C.evap_for_candidate(self._cand(), False)
        self.assertEqual((amt, how), (5000.0, "explicitly-subtracted"))

    def test_site_applied(self):
        amt, how = C.evap_for_candidate(self._cand(path="site-applied"), True)
        self.assertEqual((amt, how), (5000.0, "site-applied"))

    def test_ineligible(self):
        amt, how = C.evap_for_candidate(self._cand(eligible=False), False)
        self.assertEqual((amt, how), (0.0, "ineligible"))
        amt, how = C.evap_for_candidate(self._cand(path="ineligible"), True)
        self.assertEqual((amt, how), (0.0, "ineligible"))


class QualifyTest(unittest.TestCase):
    def test_no_rate_requirement(self):
        # rate_ok is always True on the payment-only scan
        self.assertTrue(J.qualify("lease-48", 9.99, 200.0)["rate_ok"])
        self.assertTrue(J.qualify("finance-72", 0.0, 300.0)["rate_ok"])

    def test_lease_cap_inclusive(self):
        self.assertTrue(J.qualify("lease-48", 2.0, 265.0)["payment_ok"])
        self.assertFalse(J.qualify("lease-48", 2.0, 265.01)["payment_ok"])

    def test_finance_cap_inclusive(self):
        self.assertTrue(J.qualify("finance-72", 2.0, 365.0)["payment_ok"])
        self.assertFalse(J.qualify("finance-72", 2.0, 365.01)["payment_ok"])

    def test_mechanical_qualifies_is_payment_only(self):
        self.assertTrue(
            J.qualify("finance-72", 9.99, 300.0)["mechanical_qualifies"])
        self.assertFalse(
            J.qualify("finance-72", 0.99, 366.0)["mechanical_qualifies"])


class ComputeTableTest(unittest.TestCase):
    def _research(self):
        return {"run_id": "r", "offer_period": "x", "candidates": [
            {"make": "Kia", "model": "Niro EV", "trim": "Wind+",
             "above_base": True, "msrp": 48595.0, "mfr_rebate": 4000.0,
             "advertised": [], "source_url": "https://www.kia.ca/",
             "market_confirmed": True, "evap_eligible": True,
             "evap_path": "explicit-subtract", "notes": ""},
        ]}

    def _calc(self, biweekly, applied_evap=False, rate=1.49):
        return {"run_id": "r", "configs": [
            {"candidate_index": 0, "config": "finance-72",
             "rate_apr": rate, "biweekly_payment": biweekly,
             "deep_link": "https://www.kia.ca/x", "url_notes": "",
             "calculator_applied_evap": applied_evap, "verified_live": True},
        ]}

    def test_finance_cross_check_match(self):
        # principal = 48595-4000-5000(evap)-5000(down) = 34595
        table = C.compute_table(J, self._research(),
                                self._calc(231.96, rate=1.49))
        row = table[0]
        self.assertEqual(row["net_pre_evap"], 44595.0)
        self.assertEqual(row["evap_applied"], 5000.0)
        self.assertEqual(row["evap_how"], "explicitly-subtracted")
        self.assertEqual(row["principal"], 34595.0)
        self.assertAlmostEqual(row["script_biweekly"],
                               round(231.96085730221338, 2), places=2)
        self.assertTrue(row["payment_match"])
        self.assertTrue(row["flags"]["mechanical_qualifies"])
        # 231.96 is within the $365 finance cap -> payment_ok True
        self.assertTrue(row["flags"]["payment_ok"])
        self.assertTrue(row["flags"]["rate_ok"])

    def test_finance_cross_check_mismatch_flagged(self):
        table = C.compute_table(J, self._research(),
                                self._calc(999.0, rate=1.49))
        self.assertFalse(table[0]["payment_match"])

    def test_evap_never_double_counted(self):
        # site-applied AND explicit path claimed -> still exactly 5000 once
        research = self._research()
        research["candidates"][0]["evap_path"] = "explicit-subtract"
        table = C.compute_table(
            J, research, self._calc(231.96, applied_evap=True, rate=1.49))
        row = table[0]
        self.assertEqual(row["evap_applied"], 5000.0)
        self.assertEqual(row["evap_how"], "site-applied")
        self.assertEqual(row["principal"], 34595.0)

    def test_lease_not_recomputed(self):
        calc = {"run_id": "r", "configs": [
            {"candidate_index": 0, "config": "lease-48",
             "rate_apr": 2.49, "biweekly_payment": 189.49,
             "deep_link": "https://www.kia.ca/y", "url_notes": "",
             "calculator_applied_evap": True, "verified_live": True},
        ]}
        table = C.compute_table(J, self._research(), calc)
        row = table[0]
        self.assertIsNone(row["script_biweekly"])
        self.assertIsNone(row["payment_match"])
        self.assertTrue(row["flags"]["mechanical_qualifies"])

    def test_unavailable_config(self):
        calc = {"run_id": "r", "configs": [
            {"candidate_index": 0, "config": "finance-72",
             "rate_apr": 0.0, "biweekly_payment": 0.0,
             "deep_link": "https://www.kia.ca/z", "url_notes": "",
             "calculator_applied_evap": False, "verified_live": False,
             "unavailable": True,
             "unavailable_reason": "no finance program published"},
        ]}
        table = C.compute_table(J, self._research(), calc)
        self.assertTrue(table[0]["unavailable"])

    def test_candidate_index_out_of_range(self):
        calc = {"run_id": "r", "configs": [
            {"candidate_index": 7, "config": "lease-48",
             "rate_apr": 2.0, "biweekly_payment": 180.0,
             "deep_link": "https://x", "url_notes": "",
             "calculator_applied_evap": False, "verified_live": True},
        ]}
        with self.assertRaises(IndexError):
            C.compute_table(J, self._research(), calc)


if __name__ == "__main__":
    unittest.main()
