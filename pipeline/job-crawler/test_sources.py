#!/usr/bin/env python3
"""
Offline tests for the free job APIs (sources.py) and how crawl.py uses them: NO network. Covers
sources.py's own selftest (every default source normalized from synthetic fixtures, the minimum
interval cache, the USAJOBS key gate), plus crawl.py's fresh-clone behaviour: no titles -> one
clear sentence and exit 2; an empty boards.yaml -> the APIs and HN still run and the JSON report
says what ran, what it returned, and what was skipped and why.

Run:  python3 test_sources.py
"""
import io, json, sys, tempfile, unittest, urllib.request
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest import mock

import sources as S
import crawl as C


class NoNetwork(unittest.TestCase):
    def setUp(self):
        self._real = urllib.request.urlopen
        urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(AssertionError("network used"))

    def tearDown(self):
        urllib.request.urlopen = self._real


def by_name(report):
    return {r["name"]: r for r in report}


def run_crawl(argv, filters, boards, api=None, hn_jobs=None):
    """Run crawl.main() with the config files and every network source mocked."""
    def fake_yaml(name):
        return {"filters.yaml": filters, "boards.yaml": boards}[name]
    now = datetime.now(timezone.utc)
    api_jobs = api if api is not None else [
        dict(company="Globex", title="Data Analyst", location="Remote (United States)",
             url="https://remotive.com/remote-jobs/data/1", posted_at=now - timedelta(hours=2),
             remote=True, description="", source="remotive")]
    api_report = [{"name": "remotive", "label": "Remotive", "status": "ran", "jobs": len(api_jobs)},
                  {"name": "themuse", "label": "The Muse", "status": "skipped", "jobs": 0,
                   "reason": "disabled in sources.yaml"}]
    out, err = io.StringIO(), io.StringIO()
    code = 0
    with mock.patch.object(C, "load_yaml", fake_yaml), \
            mock.patch.object(C.api_sources, "collect", return_value=(api_jobs, api_report)), \
            mock.patch.object(C.hn, "collect", return_value=(hn_jobs or [], {"thread": None})), \
            mock.patch.object(sys, "argv", ["crawl.py"] + argv), \
            redirect_stdout(out), redirect_stderr(err):
        try:
            C.main()
        except SystemExit as e:
            code = e.code
    return code, out.getvalue(), err.getvalue()


class TestSources(NoNetwork):
    def test_builtin_selftest(self):
        with redirect_stdout(io.StringIO()):
            S._selftest()

    def test_remoteok_skips_legal_notice(self):
        jobs = S.fetch_remoteok({}, ["x"], lambda u, **k: [{"legal": "terms"}, {"position": "Welder",
                                "company": "Initech", "url": "https://remoteok.com/remote-jobs/1"}], None)
        self.assertEqual([j["title"] for j in jobs], ["Welder"])

    def test_floor_cannot_be_lowered(self):
        tmp = Path(tempfile.mkdtemp())
        cfg = {"remoteok": {"enabled": True, "min_interval_minutes": 1}}
        calls = []
        get = lambda u, **k: calls.append(u) or [{"position": "Welder", "company": "A", "url": "https://remoteok.com/1"}]
        t0 = datetime(2099, 1, 1, tzinfo=timezone.utc)
        S.collect(["welder"], cfg, tmp, t0, get, lambda s: None)
        _, rep = S.collect(["welder"], cfg, tmp, t0 + timedelta(minutes=5), get, lambda s: None)
        self.assertEqual(len(calls), 1)
        self.assertEqual(by_name(rep)["remoteok"]["status"], "cached")

    def test_rate_limit_counts_as_attempt(self):
        import urllib.error
        tmp = Path(tempfile.mkdtemp())
        cfg = {"remoteok": {"enabled": True}}
        def get(u, **k):
            raise urllib.error.HTTPError(u, 429, "slow down", {}, None)
        t0 = datetime(2099, 1, 1, tzinfo=timezone.utc)
        _, rep = S.collect([], cfg, tmp, t0, get, lambda s: None)
        self.assertEqual(by_name(rep)["remoteok"]["status"], "error")
        self.assertIn("429", by_name(rep)["remoteok"]["reason"])
        _, rep2 = S.collect([], cfg, tmp, t0 + timedelta(minutes=10), get, lambda s: None)
        self.assertEqual(by_name(rep2)["remoteok"]["status"], "cached")

    def test_shipped_sources_yaml_matches_defaults(self):
        cfg = S.load_config(Path(S.__file__).with_name("sources.yaml"))
        on = sorted(k for k, v in cfg.items() if v.get("enabled"))
        self.assertEqual(on, ["himalayas", "jobicy", "remoteok", "remotive", "usajobs"])
        self.assertFalse(cfg["themuse"]["enabled"])
        self.assertFalse(cfg["weworkremotely"]["enabled"])


class TestCrawlFreshClone(NoNetwork):
    base_filters = {"lookback_hours": 72, "include_titles": [], "require_us": True,
                    "us_markers": ["united states"], "location_block": ["london"]}

    def test_no_titles_exits_with_one_sentence(self):
        code, out, err = run_crawl([], dict(self.base_filters), {"boards": None})
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertEqual(err.strip(), C.NO_TITLES)
        self.assertEqual(err.strip().count(". "), 0)  # one sentence

    def test_empty_boards_still_runs_apis_and_hn(self):
        F = dict(self.base_filters, include_titles=["Data Analyst"])
        code, out, err = run_crawl([], F, {"boards": None})
        self.assertEqual(code, 0)
        d = json.loads(out)
        names = {r["name"]: r for r in d["sources"]}
        self.assertEqual(names["ats-boards"]["status"], "skipped")
        self.assertIn("discover.py --sweep", names["ats-boards"]["reason"])
        self.assertEqual(names["remotive"]["matches"], 1)
        self.assertEqual(names["themuse"]["reason"], "disabled in sources.yaml")
        self.assertEqual(names["hn"]["status"], "ran")
        self.assertEqual(d["count_by_source"], {"remotive": 1})
        self.assertIn("discover.py --sweep", err)
        self.assertIn("not a fixed set", d["sources_note"])

    def test_api_job_obeys_filters(self):
        now = datetime.now(timezone.utc)
        api = [dict(company="Initech", title="Data Analyst", location="London", url="https://x/1",
                    posted_at=now, remote=False, description="", source="jobicy"),
               dict(company="Northwind", title="Data Analyst", location="Remote", url="https://x/2",
                    posted_at=now - timedelta(days=30), remote=True, description="", source="jobicy")]
        F = dict(self.base_filters, include_titles=["data analyst"])
        _, out, _ = run_crawl([], F, {"boards": []}, api=api)
        self.assertEqual(json.loads(out)["count"], 0)  # one outside the US, one too old

    def test_feed_names_the_source_and_credits_it(self):
        m = dict(company="Globex", title="Data Analyst", location="Remote", url="https://remotive.com/x",
                 posted_at="2099-01-01T00:00:00+00:00", remote=True, score=0, matched="data analyst",
                 source="remotive", no_sponsor_flag=False)
        tmp = Path(tempfile.mkdtemp()) / "job-feed.md"
        with mock.patch.object(C, "FEED", tmp):
            C.write_feed([m], 72)
        text = tmp.read_text()
        self.assertIn("| Remotive |", text)
        self.assertIn("[Remotive](https://remotive.com)", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
