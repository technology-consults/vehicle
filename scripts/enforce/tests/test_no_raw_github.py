"""Tests for scripts/enforce/no_raw_github.py.

The banned host is spelled out only via concatenation in this file, so the
check under test never flags its own test suite.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import no_raw_github as NRG

BANNED = "raw." + "githubusercontent.com"


class ApiEquivalentTest(unittest.TestCase):
    def test_conversion(self):
        url = ("https://%s/technology-consults/vehicle/main/"
               "ev-deals/index.html" % BANNED)
        m = NRG.RAW_RE.search(url)
        self.assertIsNotNone(m)
        self.assertEqual(
            NRG.api_equivalent(m),
            "https://api.github.com/repos/technology-consults/vehicle/"
            "contents/ev-deals/index.html?ref=main")

    def test_nested_path(self):
        url = ("https://%s/o/r/v1.0/a/b/c.txt" % BANNED)
        m = NRG.RAW_RE.search(url)
        self.assertEqual(
            NRG.api_equivalent(m),
            "https://api.github.com/repos/o/r/contents/a/b/c.txt?ref=v1.0")

    def test_no_match_on_api_url(self):
        self.assertIsNone(NRG.RAW_RE.search(
            "https://api.github.com/repos/o/r/contents/x?ref=main"))


class CheckTest(unittest.TestCase):
    def _tmp(self, content):
        fh = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False)
        fh.write(content)
        fh.close()
        self.addCleanup(os.unlink, fh.name)
        return fh.name

    def test_clean_file_passes(self):
        path = self._tmp("import json\n# api.github.com only\n")
        self.assertEqual(NRG.check([path]), [])

    def test_violation_reported(self):
        path = self._tmp("URL = \"https://%s/o/r/main/f.py\"\n" % BANNED)
        viols = NRG.check([path])
        self.assertEqual(len(viols), 1)
        self.assertEqual(viols[0]["line"], 1)
        self.assertIn(BANNED, viols[0]["raw_url"])
        self.assertEqual(
            viols[0]["api_url"],
            "https://api.github.com/repos/o/r/contents/f.py?ref=main")

    def test_multiple_lines(self):
        path = self._tmp(
            "a = \"https://%s/o/r/main/1.py\"\n"
            "b = \"https://%s/o/r/main/2.py\"\n" % (BANNED, BANNED))
        self.assertEqual(len(NRG.check([path])), 2)

    def test_missing_file_ignored(self):
        self.assertEqual(NRG.check(["/nonexistent/x.py"]), [])


class MainTest(unittest.TestCase):
    def test_main_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            clean = os.path.join(d, "clean.py")
            dirty = os.path.join(d, "dirty.py")
            with open(clean, "w") as fh:
                fh.write("x = 1\n")
            with open(dirty, "w") as fh:
                fh.write("u = \"https://%s/o/r/main/f\"\n" % BANNED)
            self.assertEqual(NRG.main(["no_raw_github.py", clean]), 0)
            self.assertEqual(NRG.main(["no_raw_github.py", dirty]), 1)


if __name__ == "__main__":
    unittest.main()
