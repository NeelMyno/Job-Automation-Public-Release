#!/usr/bin/env python3
"""
Offline tests for discover.py: NO network. Runs discover.py's own selftest (URL parsing for all
six ATSes, the sweep, --urls, --company, --queries and the safe boards.yaml append, all against
synthetic fixtures and a fake HTTP layer), plus a few extra edge cases.

Run:  python3 test_discover.py
"""
import io, sys, unittest, urllib.request
from unittest import mock
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


class TestTimeBudget(NoNetwork):
    def test_deadline_reaches_every_http_read(self):
        clock = D.FakeClock()
        ctx = D.Ctx(cache=Path(tempfile.mkdtemp()), clock=clock, F={"include_titles": ["x"]})
        seen = []

        def fake_read(req, timeout, **kw):
            seen.append(kw)
            return "{}"
        ctx.deadline = 120.0
        with mock.patch.object(D, "read_url", fake_read):
            ctx.http.get_json("https://api.lever.co/v0/postings/acme?mode=json")
        self.assertEqual(seen[0]["deadline"], 120.0)
        self.assertIs(seen[0]["clock"], clock)

    def test_probe_stops_retrying_when_time_is_short(self):
        waits = []
        r = D.probe("lever", "boom", D.FakeHttp({"api.lever.co": 500}), sleep=waits.append, left=lambda: 1.0)
        self.assertEqual(r["status"], "error")
        self.assertEqual(waits, [])

    def test_unchecked_board_is_skipped_not_failed_after_deadline(self):
        clock = D.FakeClock()
        ctx = D.Ctx(cache=Path(tempfile.mkdtemp()), http=D.FakeHttp({"api.lever.co": 500}, clock, 50.0),
                    sleep=lambda s: None, clock=clock, F={"include_titles": ["x"]})
        ctx.deadline = 40.0
        with redirect_stderr(io.StringIO()):
            got = list(D.run_pool(ctx, [("lever", "a"), ("lever", "b")], 1, "t"))
        self.assertEqual({g["status"] for g in got}, {"skipped"})

    def test_index_503_backs_off_at_least_30_seconds(self):
        waits = []
        ctx = D.Ctx(cache=Path(tempfile.mkdtemp()), http=D.FakeHttp({"collinfo": 503}), sleep=waits.append,
                    F={"include_titles": ["x"]})
        with self.assertRaises(D.HttpStatus):
            D._retry(ctx, lambda: ctx.http.get_json(D.COLLINFO), tries=2, waits=(3,))
        self.assertEqual(waits, [30])

    def test_503_wait_never_runs_past_the_budget(self):
        clock, waits = D.FakeClock(), []
        ctx = D.Ctx(cache=Path(tempfile.mkdtemp()), http=D.FakeHttp({"collinfo": 503}), sleep=waits.append,
                    clock=clock, F={"include_titles": ["x"]})
        ctx.deadline = 10.0
        with self.assertRaises(D.OutOfTime):
            D._retry(ctx, lambda: ctx.http.get_json(D.COLLINFO), tries=2, waits=(3,))
        self.assertEqual(waits, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
