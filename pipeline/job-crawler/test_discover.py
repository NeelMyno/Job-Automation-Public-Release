#!/usr/bin/env python3
"""
Offline tests for discover.py: NO network. Runs discover.py's own selftest (URL parsing for all
six ATSes, the sweep, --urls, --company, --queries and the safe boards.yaml append, all against
synthetic fixtures and a fake HTTP layer), plus a few extra edge cases.

Run:  python3 test_discover.py
"""
import io, sys, unittest, urllib.request
from contextlib import redirect_stderr
from pathlib import Path
import tempfile

import discover as D


class NoNetwork(unittest.TestCase):
    def setUp(self):
        self._real = urllib.request.urlopen
        urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(AssertionError("network used"))

    def tearDown(self):
        urllib.request.urlopen = self._real


class TestDiscover(NoNetwork):
    def test_builtin_selftest(self):
        with redirect_stderr(io.StringIO()):
            self.assertEqual(D._selftest(), 0)

    def test_slug_is_url_safe(self):
        self.assertEqual(D.canon_slug("Anthos Capital"), "Anthos%20Capital")
        self.assertIsNone(D.canon_slug(""))
        self.assertIsNone(D.canon_slug("x" * 200))

    def test_user_rows_never_rewritten(self):
        p = Path(tempfile.mkdtemp()) / "boards.yaml"
        original = "# mine\nboards:\n  - {company: \"Initech\", ats: lever, slug: \"initech\", note: keep}\n"
        p.write_text(original)
        ok, _ = D.append_rows(p, [{"company": "Mirror", "ats": "ashby", "slug": "mirror",
                                   "source": "discover:urls", "added": "2099-01-01"}])
        self.assertTrue(ok)
        self.assertTrue(p.read_text().startswith(original))
        _, rows = D.read_boards(p)
        self.assertEqual(rows[0]["note"], "keep")
        self.assertEqual(rows[1]["source"], "discover:urls")

    def test_dedupe_is_case_insensitive(self):
        rows = [{"company": "A", "ats": "lever", "slug": "Northwind"}]
        self.assertIn(D.board_key("lever", "northwind"), D.existing_keys(rows))

    def test_probe_reports_dead_and_empty(self):
        http = D.FakeHttp({"api.lever.co/v0/postings/empty": [], "api.lever.co/v0/postings/gone": 404})
        self.assertEqual(D.probe("lever", "empty", http)["status"], "empty")
        self.assertEqual(D.probe("lever", "gone", http)["status"], "dead")
        self.assertEqual(D.probe("lever", "boom", D.FakeHttp({"api.lever.co": 500}), sleep=lambda s: None)["status"], "error")


if __name__ == "__main__":
    unittest.main(verbosity=2)
