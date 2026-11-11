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
from contextlib import nullcontext, redirect_stdout, redirect_stderr
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest import mock

try:
    import yaml  # noqa: F401
except ImportError:
    sys.exit("These tests need the PyYAML package, which is missing. Install it with: python3 -m pip install PyYAML")

import sources as S
import crawl as C


class NoNetwork(unittest.TestCase):
    def setUp(self):
        self._real = urllib.request.urlopen
        urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(AssertionError("network used"))

    def tearDown(self):
        urllib.request.urlopen = self._real


SHIPPED_HERE = C.HERE


def by_name(report):
    return {r["name"]: r for r in report}


def run_crawl(argv, filters, boards, api=None, hn_jobs=None, report=None, hn_error=None):
    """Run crawl.main() with the config files and every network source mocked. It never looks at the
    user's own boards.yaml or sources.yaml; a test that patches C.HERE itself keeps its folder."""
    def fake_yaml(name):
        return {"filters.yaml": filters, "boards.yaml": boards}[name]
    now = datetime.now(timezone.utc)
    api_jobs = api if api is not None else [
        dict(company="Globex", title="Data Analyst", location="Remote (United States)",
             url="https://remotive.com/remote-jobs/data/1", posted_at=now - timedelta(hours=2),
             remote=True, description="", source="remotive")]
    api_report = report if report is not None else [
        {"name": "remotive", "label": "Remotive", "status": "ran", "jobs": len(api_jobs)},
        {"name": "themuse", "label": "The Muse", "status": "skipped", "jobs": 0,
         "reason": "disabled in sources.yaml"}]
    hn_mock = {"side_effect": hn_error} if hn_error else {"return_value": (hn_jobs or [], {"thread": None})}
    out, err = io.StringIO(), io.StringIO()
    code = 0
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "boards.yaml").write_text("boards: []\n")
        here = mock.patch.object(C, "HERE", Path(tmp)) if C.HERE == SHIPPED_HERE else nullcontext()
        with here, mock.patch.object(C, "load_yaml", fake_yaml), \
                mock.patch.object(C, "read_sources", return_value=({}, [])), \
                mock.patch.object(C.api_sources, "collect", return_value=(api_jobs, api_report)), \
                mock.patch.object(C.hn, "collect", **hn_mock), \
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

    def test_a_wrong_enabled_value_falls_back_and_names_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sources.yaml"
            path.write_text('sources:\n  remotive:\n    enabled: "no"\n  themuse:\n    enabled: "false"\n  jobicy:\n    enabled:\n')
            cfg, problems = S.read_config(path)
            clean, bad = S.config_files.clean_source_settings(cfg, S.DEFAULTS)
        self.assertIs(clean["remotive"]["enabled"], S.DEFAULTS["remotive"]["enabled"])
        self.assertIs(clean["themuse"]["enabled"], S.DEFAULTS["themuse"]["enabled"])
        self.assertIs(clean["jobicy"]["enabled"], S.DEFAULTS["jobicy"]["enabled"])
        self.assertEqual(len(bad), 3)
        self.assertTrue(all(b.startswith("sources.yaml: enabled under") for b in bad), bad)

    def test_collect_reading_the_file_itself_cleans_it_too(self):
        off = {k: {"enabled": False} for k in S.DEFAULTS}
        off["remotive"] = {"enabled": "false"}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(S, "read_config", return_value=(off, [])):
            jobs, report = S.collect(["welder"], cache_dir=Path(tmp), get=lambda *a, **k: [], sleep=lambda s: None)
        self.assertTrue(any(r["name"] == S.CONFIG_ENTRY and "enabled under remotive" in r["reason"] for r in report))

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

    def test_a_title_change_inside_the_interval_is_said_not_hidden(self):
        tmp = Path(tempfile.mkdtemp())
        cfg = {"remoteok": {"enabled": True}}
        get = lambda u, **k: [{"position": "Paralegal", "company": "A", "url": "https://remoteok.com/1"}]
        t0 = datetime(2099, 1, 1, tzinfo=timezone.utc)
        S.collect(["paralegal"], cfg, tmp, t0, get, lambda s: None)
        _, same = S.collect(["Paralegal"], cfg, tmp, t0 + timedelta(minutes=5), get, lambda s: None)
        _, rep = S.collect(["welder"], cfg, tmp, t0 + timedelta(minutes=5), get, lambda s: None)
        self.assertNotIn("stale_titles", by_name(same)["remoteok"])
        entry = by_name(rep)["remoteok"]
        self.assertEqual((entry["status"], entry["stale_titles"]), ("cached", True))
        self.assertIn("earlier titles", entry["reason"])
        self.assertGreater(entry["retry_in"], 0)

    def test_feed_entities_are_decoded_once(self):
        j = S._job("remoteok", "Aisles &amp; Abroad", "Client Support &amp; Travel", "Austin, TX &amp; Remote",
                   "https://remoteok.com/1", None, True, "")
        self.assertEqual((j["company"], j["title"], j["location"]),
                         ("Aisles & Abroad", "Client Support & Travel", "Austin, TX & Remote"))

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

    def test_built_in_defaults_turn_on_the_free_sources(self):
        on = sorted(k for k, v in S.DEFAULTS.items() if v.get("enabled"))
        self.assertEqual(on, ["himalayas", "jobicy", "remoteok", "remotive", "usajobs"])
        self.assertFalse(S.DEFAULTS["themuse"]["enabled"])
        self.assertFalse(S.DEFAULTS["weworkremotely"]["enabled"])

    def test_switching_a_source_off_keeps_the_rest(self):
        p = Path(tempfile.mkdtemp()) / "sources.yaml"
        p.write_text("sources:\n  remoteok: {enabled: false}\n")
        cfg = S.load_config(p)
        self.assertFalse(cfg["remoteok"]["enabled"])
        self.assertEqual(cfg["jobicy"], S.DEFAULTS["jobicy"])


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


class TestJobicyTagLength(NoNetwork):
    def tags(self, titles):
        urls = []
        got = S.fetch_jobicy({}, titles, lambda u, **k: urls.append(u) or {"jobs": []}, lambda s: None)
        self.assertFalse(getattr(got, "errors", []))
        return [S.urllib.parse.parse_qs(S.urllib.parse.urlparse(u).query)["tag"][0] for u in urls]

    def test_long_titles_fit_the_limit(self):
        self.assertEqual(self.tags(["journeyman electrician"]), ["electrician"])
        self.assertEqual(self.tags(["electrical technician"]), ["technician"])
        self.assertEqual(self.tags(["certified nursing assistant"]), ["nursing assistant"])

    def test_exactly_twenty_characters_is_sent_whole(self):
        self.assertEqual(self.tags(["warehouse supervisor"]), ["warehouse supervisor"])

    def test_shortened_duplicates_are_sent_once(self):
        self.assertEqual(self.tags(["journeyman electrician", "electrician"]), ["electrician"])

    def test_other_sources_keep_the_whole_title(self):
        urls = []
        S.fetch_himalayas({}, ["journeyman electrician"], lambda u, **k: urls.append(u) or {"jobs": []}, lambda s: None)
        self.assertIn("journeyman+electrician", urls[0])


class TestBrokenSourcesFile(NoNetwork):
    def cfg(self, text):
        p = Path(tempfile.mkdtemp()) / "sources.yaml"
        p.write_text(text)
        return S.read_config(p)

    def test_invalid_yaml_says_so_and_uses_defaults(self):
        cfg, problems = self.cfg("sources:\n  himalayas: {enabled: true\n")
        self.assertEqual(cfg["jobicy"], S.DEFAULTS["jobicy"])
        self.assertEqual(len(problems), 1)
        self.assertIn("built-in source settings", problems[0])
        self.assertIn("not valid YAML", problems[0])

    def test_no_sources_block_says_so(self):
        for text in ("- just\n- a list\n", "sources: nope\n", ""):
            cfg, problems = self.cfg(text)
            self.assertEqual(cfg["remotive"], S.DEFAULTS["remotive"], text)
            self.assertEqual(len(problems), 1, text)

    def test_one_bad_block_keeps_the_good_ones(self):
        cfg, problems = self.cfg("sources:\n  jobicy: {enabled: false}\n  remotive: yes\n")
        self.assertFalse(cfg["jobicy"]["enabled"])
        self.assertTrue(cfg["remotive"]["enabled"])
        self.assertEqual(len(problems), 1)
        self.assertIn("`remotive`", problems[0])

    def test_good_or_absent_file_reports_nothing(self):
        self.assertEqual(self.cfg("sources:\n  jobicy: {enabled: false}\n")[1], [])
        self.assertEqual(S.read_config(Path(tempfile.mkdtemp()) / "none.yaml")[1], [])

    def test_collect_reports_the_problem_and_carries_on(self):
        p = Path(tempfile.mkdtemp()) / "sources.yaml"
        p.write_text("sources: [broken\n")
        off = {k: dict(v, enabled=False) for k, v in S.DEFAULTS.items()}
        with mock.patch.object(S, "read_config", return_value=(off, ["sources.yaml is broken"])):
            _, report = S.collect(["welder"], cache_dir=Path(tempfile.mkdtemp()))
        self.assertEqual(report[-1]["name"], S.CONFIG_ENTRY)
        self.assertEqual(report[-1]["reason"], "sources.yaml is broken")

    def test_crawl_hints_carry_the_problem(self):
        report = [{"name": S.CONFIG_ENTRY, "label": "sources.yaml", "status": "error", "jobs": 0,
                   "reason": "Using the built-in source settings for this run."},
                  {"name": "remotive", "label": "Remotive", "status": "ran", "jobs": 0}]
        d = json.loads(run_crawl([], {"include_titles": ["welder"]}, {"boards": []}, api=[], report=report)[1])
        self.assertIn("Using the built-in source settings for this run.", d["hints"])
        self.assertNotIn(C.ALL_FAILED_HINT, d["hints"])

    def test_unreadable_interval_keeps_the_floor(self):
        self.assertEqual(S._interval_minutes("jobicy", {"min_interval_minutes": "soon"}), 60)

    def crawl_with(self, sources_text, here, runs=1):
        """crawl.main() with a real sources.yaml read from `here`; only the HTTP reads are faked."""
        (here / "sources.yaml").write_text(sources_text)
        (here / "boards.yaml").write_text("boards: []\n")
        F = {"lookback_hours": 72, "include_titles": ["welder"], "require_us": False}
        body = json.dumps({"jobs": [{"companyName": "Acme", "title": "Welder", "pubDate": 4102444800,
                                     "applicationLink": "https://himalayas.app/1"}]}).encode()
        out = io.StringIO()
        with mock.patch.object(S, "HERE", here), mock.patch.object(C, "HERE", here), \
                mock.patch.object(C, "CACHE_DIR", here / "cache"), \
                mock.patch.object(S, "read_url", lambda *a, **k: body), \
                mock.patch.object(C, "load_yaml", lambda name: {"filters.yaml": F, "boards.yaml": {}}[name]), \
                mock.patch.object(sys, "argv", ["crawl.py", "--no-hn"]), \
                redirect_stdout(out), redirect_stderr(io.StringIO()):
            for _ in range(runs):
                out.seek(0)
                out.truncate()
                C.main()
        return json.loads(out.getvalue())

    def test_bad_values_are_named_and_the_source_still_runs(self):
        off = "".join(f"  {n}: {{enabled: false}}\n" for n in S.DEFAULTS if n != "himalayas")
        for bad in ("soon", "[1, 2]", "{a: 1}", "-5", ".inf", ".nan", "true"):
            d = self.crawl_with(f"sources:\n  himalayas: {{enabled: true, max_queries: {bad}}}\n{off}",
                                Path(tempfile.mkdtemp()))
            self.assertEqual(by_name(d["sources"])["himalayas"]["status"], "ran", bad)
            self.assertEqual(d["count"], 1, bad)
            note = [h for h in d["hints"] if "max_queries" in h]
            self.assertEqual(len(note), 1, bad)
            self.assertIn("sources.yaml", note[0])
            self.assertNotRegex(json.dumps(d["sources"]), r"[A-Z][a-z]+Error", bad)

    def test_an_endless_interval_does_not_lose_every_api_on_the_next_run(self):
        off = "".join(f"  {n}: {{enabled: false}}\n" for n in S.DEFAULTS if n != "himalayas")
        for bad in (".inf", ".nan", "1e300"):
            d = self.crawl_with(f"sources:\n  himalayas: {{enabled: true, min_interval_minutes: {bad}}}\n{off}",
                                Path(tempfile.mkdtemp()), runs=2)
            self.assertEqual(by_name(d["sources"])["himalayas"]["status"], "cached", bad)
            self.assertNotIn("job-apis", by_name(d["sources"]), bad)

    def test_a_country_of_the_wrong_kind_goes_back_to_the_built_in_one(self):
        p = Path(tempfile.mkdtemp())
        (p / "sources.yaml").write_text("sources:\n  himalayas: {enabled: true, country: [US, CA]}\n")
        with mock.patch.object(S, "HERE", p):
            cfg, problems = C.read_sources()
        self.assertEqual(cfg["himalayas"]["country"], S.DEFAULTS["himalayas"]["country"])
        self.assertEqual(len(problems), 1)
        self.assertIn("country under himalayas", problems[0])

    def test_a_cached_failure_is_marked(self):
        def down(u, **k):
            raise urllib.error.HTTPError(u, 503, "x", {}, None)
        tmp, t0 = Path(tempfile.mkdtemp()), datetime(2099, 1, 1, tzinfo=timezone.utc)
        cfg = {"remoteok": {"enabled": True}}
        S.collect(["welder"], cfg, tmp, t0, down, lambda s: None)
        entry = {r["name"]: r for r in S.collect(["welder"], cfg, tmp, t0 + timedelta(minutes=5), down, lambda s: None)[1]}["remoteok"]
        self.assertEqual((entry["status"], entry["last_attempt_failed"]), ("cached", True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
