#!/usr/bin/env python3
"""
Offline tests for crawl.py's ranking, its tracker rows, the shared location rule (locations.py),
HN title parsing, the short-title rule (titles.py), the drop counts, and discover.py's
time-budget help: NO network. Every input is synthetic.

Run:  python3 test_crawl.py
"""
import io, json, re, sys, tempfile, unittest, urllib.error, urllib.request
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest import mock

try:
    import yaml  # noqa: F401
except ImportError:
    sys.exit("These tests need the PyYAML package, which is missing. Install it with: python3 -m pip install PyYAML")

import crawl as C
import discover as D
import hn
import liveness as LV
import locations as L
import titles as T
from test_sources import run_crawl


class NoNetwork(unittest.TestCase):
    def setUp(self):
        self._real = urllib.request.urlopen
        urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(AssertionError("network used"))

    def tearDown(self):
        urllib.request.urlopen = self._real


def job(title, location="Remote", company="Globex", hours_ago=2, url=None, source="remotive", remote=None):
    return dict(company=company, title=title, location=location, remote=remote,
                url=url or f"https://example.test/{abs(hash((title, location, hours_ago)))}",
                posted_at=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
                description="", source=source)


BASE = {"lookback_hours": 72, "include_titles": ["registered nurse", "staff accountant", "electrician",
        "warehouse associate", "middle school teacher", "retail store manager", "dispatcher"], "require_us": True,
        "us_markers": ["united states", ", co", ", ca"], "location_block": ["ireland", "dublin"]}


class TestLocations(NoNetwork):
    def test_selftest(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(L._selftest(), 0)

    def test_crawl_applies_home_metro_rule(self):
        F = dict(BASE, remote_ok=True, onsite_ok="home_metros", home_metros=["denver"])
        api = [job("Registered Nurse", "San Francisco, CA", company="Acme"),
               job("Registered Nurse", "Denver, CO", company="Globex"),
               job("Registered Nurse", "Remote (United States)", company="Initech"),
               job("Registered Nurse", "Dublin, Ireland", company="Northwind")]
        code, out, _ = run_crawl([], F, {"boards": []}, api=api)
        self.assertEqual(code, 0)
        d = json.loads(out)
        self.assertEqual(sorted(m["location"] for m in d["matches"]), ["Denver, CO", "Remote (United States)"])
        self.assertIn("onsite or hybrid in denver", d["location_rule"])

    def test_default_keeps_onsite_anywhere(self):
        code, out, _ = run_crawl([], dict(BASE), {"boards": []}, api=[job("Electrician", "San Francisco, CA")])
        self.assertEqual(json.loads(out)["count"], 1)

    def test_bad_setting_is_one_clear_sentence(self):
        code, out, err = run_crawl([], dict(BASE, onsite_ok="home_metros"), {"boards": []})
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("home_metros", err)


class TestRegionLists(NoNetwork):
    """The region gate with filled-in lists: whole words, every state, US wins. The lists are written
    here because filters.yaml is yours to trim."""
    F = {"require_us": True, "us_markers": ["united states", "usa", "us", "u.s."],
         "location_block": ["canada", "toronto", "manila", "philippines", "nigeria", "lagos", "europe",
                            "emea", "united kingdom", "london", "mexico", "mexico city", "dublin",
                            "berlin", "lisbon", "paris", "india"]}

    def ok(self, where):
        return L.region_ok({"location": where}, self.F)

    def test_foreign_places_dropped(self):
        for where in ("Toronto, Canada", "Makati, Manila, Philippines", "Lagos, Nigeria",
                      "Remote (Europe)", "Remote - EMEA", "London, United Kingdom", "Mexico City, Mexico"):
            self.assertFalse(self.ok(where), where)

    def test_us_towns_with_foreign_names_kept(self):
        for where in ("Dublin, OH", "London, OH", "Berlin, NH", "Lisbon, OH", "Toronto, OH",
                      "Columbus, OH", "Paris, TX", "Albuquerque, New Mexico", "Indianapolis, IN",
                      "Remote (United States)", "Remote, US"):
            self.assertTrue(self.ok(where), where)


class TestBadFilterValues(NoNetwork):
    """A value in filters.yaml that can't be used stops the run with one plain sentence naming the
    file and the setting, never a Python error."""
    def assert_refused(self, key, value):
        code, out, err = run_crawl([], dict(BASE, **{key: value}), {"boards": []})
        self.assertEqual(code, 2, (key, value))
        self.assertEqual(out, "", (key, value))
        self.assertEqual(len(err.strip().splitlines()), 1, (key, value))
        self.assertIn("filters.yaml", err, (key, value))
        self.assertIn(key, err, (key, value))
        self.assertNotRegex(err, r"[A-Z][a-z]+Error|Traceback", (key, value))

    def test_lookback_hours_must_be_a_positive_number(self):
        for bad in (None, "soon", "72", -5, 0, True, [72], ["soon"], {"a": 1}, float("inf"), float("nan"), 1e300):
            self.assert_refused("lookback_hours", bad)

    def test_good_lookback_hours_still_run(self):
        for good in (72, 1.5):
            code, out, _ = run_crawl([], dict(BASE, lookback_hours=good), {"boards": []}, api=[])
            self.assertEqual((code, json.loads(out)["lookback_hours"]), (0, good))
        no_key = {k: v for k, v in BASE.items() if k != "lookback_hours"}
        self.assertEqual(json.loads(run_crawl([], no_key, {"boards": []}, api=[])[1])["lookback_hours"], 72)

    def test_hours_flag_replaces_a_bad_value_and_is_checked_too(self):
        code, out, _ = run_crawl(["--hours", "24"], dict(BASE, lookback_hours="soon"), {"boards": []}, api=[])
        self.assertEqual((code, json.loads(out)["lookback_hours"]), (0, 24))
        for bad in ("0", "-5", "99999999999999"):
            code, out, err = run_crawl(["--hours", bad], dict(BASE), {"boards": []}, api=[])
            self.assertEqual((code, out), (2, ""), bad)
            self.assertIn("--hours must be", err, bad)

    def test_onsite_ok_must_be_one_choice(self):
        for bad in (["denver"], [], {"a": 1}):
            self.assert_refused("onsite_ok", bad)

    def test_list_entries_must_be_plain_text(self):
        for key in ("include_titles", "us_markers", "location_block", "home_metros", "exclude_patterns"):
            for bad in ([["a"]], [{"a": 1}]):
                self.assert_refused(key, bad)

    def test_discover_gets_the_same_plain_refusal(self):
        p = Path(tempfile.mkdtemp()) / "filters.yaml"
        p.write_text("include_titles: [welder]\nlocation_block: [[dublin]]\n")
        with self.assertRaises(C.config_files.ConfigError) as caught:
            D.load_filters(p)
        self.assertIn("location_block", str(caught.exception))


class TestFilterLists(NoNetwork):
    """exclude_patterns, flag_patterns and exclude_companies match whatever case you typed, and a
    null list is read as empty instead of crashing."""
    def test_mixed_case_entries_match(self):
        walled = job("Warehouse Associate", "Remote (United States)", company="Initech")
        walled["description"] = "Must be a US Citizen."
        flagged = job("Warehouse Associate", "Remote (United States)", company="Hooli")
        flagged["description"] = "We are Unable To Sponsor visas."
        api = [walled, flagged, job("Warehouse Associate", "Remote (United States)", company="Acme Corp"),
               job("Warehouse Associate", "Remote (United States)", company="Globex")]
        F = dict(BASE, exclude_patterns=["US Citizen"], flag_patterns=["Unable to Sponsor"],
                 exclude_companies=["ACME"])
        code, out, _ = run_crawl([], F, {"boards": []}, api=api)
        d = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(sorted(m["company"] for m in d["matches"]), ["Globex", "Hooli"])
        self.assertEqual(d["dropped"]["wall"], 2)
        self.assertEqual([m["company"] for m in d["matches"] if m["no_sponsor_flag"]], ["Hooli"])

    def test_null_lists_do_not_crash(self):
        F = dict(BASE, exclude_patterns=None, flag_patterns=None, exclude_companies=None,
                 include_keywords=None)
        code, out, _ = run_crawl([], F, {"boards": []},
                                 api=[job("Dispatcher", "Remote (United States)")])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["count"], 1)

    def test_blank_entry_is_dropped(self):
        self.assertEqual(C.normalize_filters({"exclude_patterns": ["", "  ", "X"]})["exclude_patterns"], ["x"])


class TestFewMatchesHint(NoNetwork):
    def test_zero_matches_points_beyond_the_feeds(self):
        F = dict(BASE, include_titles=["registered nurse"], remote_ok=False, onsite_ok="home_metros",
                 home_metros=["columbus"])
        code, out, _ = run_crawl([], F, {"boards": []}, api=[job("Data Analyst")])
        d = json.loads(out)
        self.assertEqual(d["count"], 0)
        hint = [h for h in d["hints"] if "can't read" in h]
        self.assertEqual(len(hint), 1, d["hints"])
        self.assertIn('"registered nurse jobs columbus"', hint[0])
        self.assertIn("hospitals", hint[0])
        self.assertIn("discover.py --queries", hint[0])

    def test_no_hint_when_plenty(self):
        api = [job("Staff Accountant", "Remote (United States)", company=c)
               for c in ("Acme", "Globex", "Initech", "Hooli", "Umbrella")]
        d = json.loads(run_crawl([], dict(BASE), {"boards": []}, api=api)[1])
        self.assertFalse([h for h in d["hints"] if "can't read" in h])


class TestRanking(NoNetwork):
    def test_title_fit_levels(self):
        F = {"include_titles": ["dispatcher"]}
        fit = lambda t: C.title_fit({"title": t}, F)
        self.assertEqual(fit("Dispatcher"), 3)
        self.assertEqual(fit("Senior Dispatcher, Night Shift"), 2)
        self.assertEqual(fit("Dispatchers-Desk Lead"), 1)

    def test_rank_without_keywords_uses_fit_then_freshness(self):
        api = [job("Senior Registered Nurse II", hours_ago=1), job("Registered Nurse", hours_ago=40),
               job("Staff Registered Nurse", hours_ago=5)]
        code, out, _ = run_crawl([], dict(BASE), {"boards": []}, api=api)
        d = json.loads(out)
        self.assertEqual([m["title"] for m in d["matches"]],
                         ["Registered Nurse", "Senior Registered Nurse II", "Staff Registered Nurse"])
        self.assertTrue(all(m["score"] == 0 for m in d["matches"]))
        self.assertIn("include_keywords is empty", d["ranking"])

    def test_keywords_rank_first_when_set(self):
        a = job("Senior Electrician", hours_ago=1)
        a["description"] = "commercial wiring and conduit bending"
        api = [job("Electrician", hours_ago=2), a]
        code, out, _ = run_crawl([], dict(BASE, include_keywords=["conduit"]), {"boards": []}, api=api)
        d = json.loads(out)
        self.assertEqual(d["matches"][0]["title"], "Senior Electrician")
        self.assertNotIn("include_keywords is empty", d["ranking"])


# The APPLICATIONS row shape (records-format section 1, as the full release's records_check.py
# enforces it): required keys present, posted YYYY-MM-DD or unknown, folder a string ("" or
# applications/<slug>), lowercase keys, `notes` never `note`, no `applied` on a lead row.
REQUIRED = ("co", "role", "status", "posted", "source", "jd", "apply", "folder", "refs", "next")
OPTIONAL = {"loc", "comp", "compK", "fit", "spon", "notes", "link"}
VAL = r'("(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?|null|true|false)'


def parse_row(text):
    body = text.strip().rstrip(",").strip()
    assert body.startswith("{") and body.endswith("}"), text
    pairs = re.findall(r"(\w+):" + VAL, body)
    out = {}
    for k, v in pairs:
        out[k] = None if v == "null" else json.loads(v) if v.startswith('"') else v
    return out


class TestTrackerRow(NoNetwork):
    def _row(self, **kw):
        m = dict(company="Globex", title="Middle School Teacher", location="Denver, CO",
                 url="https://example.test/1", posted_at="2099-01-05T00:00:00+00:00", remote=None,
                 score=0, title_fit=3, matched="middle school teacher", source="ats", no_sponsor_flag=False)
        m.update(kw)
        return parse_row(C._js_row(m))

    def assert_shape(self, r):
        for k in REQUIRED:
            self.assertIn(k, r)
        self.assertLessEqual(set(r), set(REQUIRED) | OPTIONAL)
        self.assertRegex(r["posted"], r"^(?:\d{4}-\d{2}-\d{2}|unknown)$")
        self.assertIsInstance(r["folder"], str)
        self.assertTrue(r["folder"] == "" or r["folder"].startswith("applications/"))
        self.assertEqual(r["status"], "lead")
        self.assertNotIn("note", r)
        self.assertNotIn("applied", r)
        self.assertFalse([k for k in r if k[:1].isupper()])

    def test_dated_row(self):
        r = self._row()
        self.assert_shape(r)
        self.assertEqual(r["posted"], "2099-01-05")

    def test_undated_row_says_unknown(self):
        r = self._row(posted_at=None, source="hn")
        self.assert_shape(r)
        self.assertEqual(r["posted"], "unknown")

    def test_approximate_date_goes_to_notes(self):
        r = self._row(posted_approx=True)
        self.assert_shape(r)
        self.assertEqual(r["posted"], "unknown")
        self.assertIn("posted (as recorded): about 2099-01-05", r["notes"])

    def test_quotes_never_break_the_row(self):
        r = self._row(company='Acme "Labs"', title="Engineer\nII", url='https://example.test/a"b')
        self.assert_shape(r)
        self.assertEqual(r["jd"], "https://example.test/a%22b")

    def test_patch_tracker_writes_valid_rows(self):
        tmp = Path(tempfile.mkdtemp()) / "tracker.html"
        tmp.write_text('<script>\nconst UPDATED = "2099-01-01";\nconst APPLICATIONS = [\n];\n</script>\n')
        m = dict(company="Globex", title="Retail Store Manager", location="", url="https://example.test/2",
                 posted_at=None, remote=None, score=0, title_fit=3, matched="x", source="ats",
                 no_sponsor_flag=False)
        with mock.patch.object(C, "TRACKER", tmp):
            self.assertEqual(C.patch_tracker([m])["added"], 1)
            self.assertEqual(C.patch_tracker([m])["added"], 0)  # deduped on the URL
        rows = re.findall(r"\{co:.*?\},", tmp.read_text(), re.S)
        self.assertEqual(len(rows), 1)
        self.assert_shape(parse_row(rows[0]))


class TestHnTitles(NoNetwork):
    F = {"include_titles": ["warehouse associate", "associate"], "us_markers": [], "location_block": []}

    def comment(self, header):
        return {"id": 7, "text": header + "<p>Body text.", "created_at": "2099-01-01T00:00:00Z"}

    def test_sentence_is_not_a_title(self):
        garbage = ("Northwind | we are looking for candidates that are excited about privacy and want "
                   "to grow as a warehouse associate...")
        self.assertIsNone(hn.parse_comment(self.comment(garbage), self.F))
        self.assertTrue(hn.sentence_like("we are looking for candidates that are excited..."))

    def test_real_role_still_parses(self):
        j = hn.parse_comment(self.comment("Northwind | Senior Warehouse Associate | Remote (US) | Full-time"), self.F)
        self.assertEqual(j["title"], "Senior Warehouse Associate")
        self.assertEqual(j["company"], "Northwind")

    def test_role_token_beside_a_sentence(self):
        j = hn.parse_comment(self.comment(
            "Northwind | Warehouse Associate | we are looking for people who want to build"), self.F)
        self.assertEqual(j["title"], "Warehouse Associate")


class TestWording(NoNetwork):
    def test_empty_boards_hint(self):
        self.assertIn("has no company boards yet", C.NO_BOARDS_HINT)
        self.assertIn("discover.py --sweep", C.NO_BOARDS_HINT)

    def test_discover_help_documents_budget_and_limit(self):
        out = io.StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit):
            D.main(["--help"])
        text = " ".join(out.getvalue().split())
        self.assertIn("--max-minutes", text)
        self.assertIn("does not bound the index harvest", text)
        self.assertIn("first run is the slowest", text)


class TestShortTitles(NoNetwork):
    """A title term of 3 characters or fewer matches only as a whole word (titles.py)."""
    def test_titles_selftest(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(T._selftest(), 0)

    def test_short_term_not_inside_a_word(self):
        F = {"include_titles": ["rn"]}
        self.assertIsNone(C.title_match({"title": "International Account Manager"}, F))
        self.assertIsNone(C.title_match({"title": "Internal Communications Lead"}, F))
        self.assertEqual(C.title_match({"title": "ICU RN - Nights"}, F), "rn")
        self.assertEqual(C.title_fit({"title": "International Account Manager"}, F), 0)
        self.assertEqual(C.title_fit({"title": "RN"}, F), 3)

    def test_long_term_still_substring(self):
        F = {"include_titles": ["engineer"]}
        self.assertEqual(C.title_match({"title": "Engineering Manager"}, F), "engineer")

    def test_crawl_drops_short_term_inside_word(self):
        F = dict(BASE, include_titles=["rn"])
        api = [job("International Account Manager", "Remote (United States)", company="Acme"),
               job("Registered Nurse (RN)", "Remote (United States)", company="Globex")]
        code, out, _ = run_crawl([], F, {"boards": []}, api=api)
        d = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual([m["company"] for m in d["matches"]], ["Globex"])
        self.assertEqual(d["dropped"]["title"], 1)

    def test_discover_uses_same_rule(self):
        F = {"include_titles": ["rn"]}
        self.assertEqual(D.matching_titles(["International Marketing", "Travel RN"], F), ["Travel RN"])


class TestDropCounts(NoNetwork):
    def test_each_reason_counted(self):
        F = dict(BASE, exclude_patterns=["clearance required"], remote_ok=True,
                 onsite_ok="home_metros", home_metros=["denver"])
        walled = job("Electrician", "Remote (United States)", company="Initech")
        walled["description"] = "Active clearance required."
        api = [job("Office Manager", company="Acme"),                                   # title
               walled,                                                                  # wall
               job("Retail Store Manager", "San Francisco, CA", company="Northwind"),   # location
               job("Dispatcher", "Denver, CO", company="Globex", hours_ago=500),        # age
               job("Middle School Teacher", "Denver, CO", company="Hooli")]             # kept
        code, out, _ = run_crawl([], F, {"boards": []}, api=api)
        d = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(d["count"], 1)
        self.assertEqual({k: d["dropped"][k] for k in ("title", "wall", "location", "age")},
                         {"title": 1, "wall": 1, "location": 1, "age": 1})
        self.assertEqual(set(d["dropped"]), set(d["dropped_reasons"]))

    def test_remote_only_hint_when_remote_not_ok(self):
        F = dict(BASE, remote_ok=False, onsite_ok="home_metros", home_metros=["denver"])
        api = [job("Staff Accountant", "Remote (United States)", company="Acme")]
        code, out, err = run_crawl([], F, {"boards": []}, api=api)
        d = json.loads(out)
        hint = [h for h in d["hints"] if "remote_ok is false" in h]
        self.assertEqual(len(hint), 1, d["hints"])
        self.assertIn("Remotive", hint[0])
        self.assertIn("dropped 1 postings", hint[0])
        self.assertEqual(d["dropped"]["location"], 1)
        # a thin HN thread beside a bulk of remote-only jobs still gets the hint
        api3 = [job("Staff Accountant", "Remote (United States)", company=c) for c in ("Acme", "Globex", "Initech")]
        hn_jobs = [job("Staff Accountant", "Denver, CO", company="Hooli", source="hn")]
        d = json.loads(run_crawl([], F, {"boards": []}, api=api3, hn_jobs=hn_jobs)[1])
        self.assertTrue([h for h in d["hints"] if "3 of the 4 jobs" in h], d["hints"])

    def test_no_remote_only_hint_when_remote_ok_or_onsite_source_ran(self):
        api = [job("Dispatcher", "Remote (United States)", company="Acme")]
        F = dict(BASE, remote_ok=True, onsite_ok="home_metros", home_metros=["denver"])
        d = json.loads(run_crawl([], F, {"boards": []}, api=api)[1])
        self.assertFalse([h for h in d["hints"] if "remote_ok is false" in h])
        F = dict(BASE, remote_ok=False, onsite_ok="home_metros", home_metros=["denver"])
        hn_jobs = [job("Dispatcher", "Denver, CO", company="Globex", source="hn")]
        d = json.loads(run_crawl([], F, {"boards": []}, api=api, hn_jobs=hn_jobs)[1])
        self.assertFalse([h for h in d["hints"] if "remote_ok is false" in h])
        self.assertEqual(d["count"], 1)


class TestConfigProblems(NoNetwork):
    """A missing or broken settings file, or a bad row, ends in a plain message, never a traceback."""
    def run_main(self, here, argv=()):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(C, "HERE", here), mock.patch.object(sys, "argv", ["crawl.py", *argv]), \
                redirect_stdout(out), redirect_stderr(err), self.assertRaises(SystemExit) as stop:
            C.main()
        return stop.exception.code, err.getvalue()

    def test_missing_filters_is_a_plain_exit_2(self):
        code, err = self.run_main(Path(tempfile.mkdtemp()))
        self.assertEqual(code, 2)
        self.assertIn("filters.yaml is missing", err)
        self.assertIn("git checkout -- pipeline/job-crawler/filters.yaml", err)

    def test_invalid_filters_is_a_plain_exit_2(self):
        here = Path(tempfile.mkdtemp())
        (here / "filters.yaml").write_text("include_titles: [nurse\nlookback_hours: 72\n")
        code, err = self.run_main(here)
        self.assertEqual(code, 2)
        self.assertRegex(err, r"filters\.yaml is not valid YAML near line \d+")

    def test_invalid_boards_is_a_plain_exit_2(self):
        here = Path(tempfile.mkdtemp())
        (here / "filters.yaml").write_text("include_titles: [nurse]\n")
        (here / "boards.yaml").write_text("boards:\n  - {company: Acme\n")
        code, err = self.run_main(here)
        self.assertEqual(code, 2)
        self.assertIn("boards.yaml is not valid YAML", err)

    def test_board_row_without_ats_is_skipped_and_reported(self):
        good = job("Registered Nurse", "Remote", company="Umbrella")
        rows = {"boards": [{"company": "Acme", "slug": "acme"}, "not a row",
                           {"company": "Umbrella", "ats": "lever", "slug": "umbrella"}]}
        with mock.patch.dict(C.FETCHERS, {"lever": lambda co, slug: [good]}):
            code, out, _ = run_crawl(["--no-hn"], dict(BASE, include_titles=["registered nurse"]), rows, api=[])
        d = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual([m["company"] for m in d["matches"]], ["Umbrella"])
        self.assertTrue([e for e in d["errors"] if "row 1 (Acme): no ats" in e], d["errors"])
        self.assertTrue([e for e in d["errors"] if "row 2" in e], d["errors"])

    def test_boards_not_a_list_is_reported(self):
        d = json.loads(run_crawl(["--no-hn"], BASE, {"boards": "acme"}, api=[])[1])
        self.assertTrue([e for e in d["errors"] if "is not a list" in e], d["errors"])

    def test_text_where_a_list_belongs_is_one_item(self):
        F = C.normalize_filters({"include_titles": "Paralegal", "exclude_patterns": "CPA required",
                                 "flag_patterns": "No Sponsorship", "exclude_companies": "Hooli",
                                 "include_keywords": "Litigation", "home_metros": "tulsa",
                                 "us_markers": "guam", "location_block": "dublin"})
        self.assertEqual(F["include_titles"], ["paralegal"])
        self.assertEqual(F["exclude_patterns"], ["cpa required"])
        for k in ("flag_patterns", "exclude_companies", "include_keywords"):
            self.assertEqual(len(F[k]), 1, k)
        self.assertEqual((F["home_metros"], F["us_markers"], F["location_block"]), (["tulsa"], ["guam"], ["dublin"]))
        self.assertEqual(T.first_match(F["include_titles"], "Lead Paralegal"), "paralegal")
        self.assertIsNone(T.first_match(F["include_titles"], "Line Cook"))  # not read letter by letter


class TestSourceFailures(NoNetwork):
    F = dict(BASE, include_titles=["registered nurse"])
    DOWN = [{"name": "remotive", "label": "Remotive", "status": "error", "jobs": 0, "reason": "HTTP 429 (rate limited)"},
            {"name": "themuse", "label": "The Muse", "status": "skipped", "jobs": 0, "reason": "disabled"}]

    def test_a_failed_hn_fetch_is_not_called_a_board(self):
        code, out, err = run_crawl([], self.F, {"boards": []}, api=[], hn_error=OSError("no route"),
                                   report=[{"name": "remotive", "label": "Remotive", "status": "ran", "jobs": 0}])
        d = json.loads(out)
        self.assertFalse([h for h in d["hints"] if "company board(s) could not be read" in h], d["hints"])
        self.assertTrue([h for h in d["hints"] if h.startswith("Hacker News could not be read")], d["hints"])

    def test_a_held_feed_is_named_with_its_retry_time(self):
        held = [{"name": "remotive", "label": "Remotive", "status": "cached", "jobs": 0, "last_attempt_failed": True,
                 "retry_in": 300, "reason": "cached"}]
        code, out, err = run_crawl([], self.F, {"boards": []}, api=[], report=held, hn_jobs=[])
        d = json.loads(out)
        self.assertEqual(code, 0)
        named = [h for h in d["hints"] if h.startswith("Not searched this run: Remotive")]
        self.assertEqual(len(named), 1)
        self.assertIn("about 300 min", named[0])
        self.assertFalse([h for h in d["hints"] if "a small count does not mean" in h])

    def test_only_dead_boards_say_the_rows_are_wrong(self):
        rows = {"boards": [{"company": "Acme", "ats": "greenhouse", "slug": "nope"}]}
        import urllib.error
        def dead(company, slug):
            raise urllib.error.HTTPError("u", 404, "not found", {}, None)
        with mock.patch.dict(C.FETCHERS, {"greenhouse": dead}):
            code, out, err = run_crawl(["--no-api", "--no-hn"], self.F, rows, api=[])
        d = json.loads(out)
        self.assertEqual(code, 3)
        self.assertTrue([h for h in d["hints"] if h.startswith("Every company board in boards.yaml answered 404")], d["hints"])

    def test_nothing_searched_with_bad_rows_names_the_rows(self):
        code, out, err = run_crawl(["--no-api", "--no-hn"], self.F, {"boards": [{"company": "Acme"}]}, api=[])
        d = json.loads(out)
        self.assertEqual(code, 3)
        self.assertTrue(d["hints"] and d["hints"][0].startswith(C.BAD_BOARDS_HINT), d["hints"])

    def test_nothing_searched_says_so_and_exits_3(self):
        code, out, err = run_crawl(["--no-api", "--no-hn"], self.F, {"boards": []}, api=[])
        d = json.loads(out)
        self.assertEqual(code, 3)
        self.assertEqual(d["hints"], [C.NOTHING_SEARCHED])

    def test_every_source_failed_says_so_and_does_not_blame_titles(self):
        code, out, err = run_crawl([], self.F, {"boards": []}, api=[], report=self.DOWN, hn_error=OSError("no route"))
        d = json.loads(out)
        self.assertEqual(code, 3)  # nothing could be fetched: never exit 0
        self.assertEqual([h for h in d["hints"] if h == C.ALL_FAILED_HINT], [C.ALL_FAILED_HINT])
        self.assertFalse([h for h in d["hints"] if "\"registered nurse jobs" in h or "a small count" in h])
        self.assertIn("Every source failed", err)

    def test_one_source_answering_is_not_every_source_failing(self):
        d = json.loads(run_crawl([], self.F, {"boards": []}, api=[])[1])
        self.assertNotIn(C.ALL_FAILED_HINT, d["hints"])
        self.assertTrue([h for h in d["hints"] if "a small count" in h])

    def test_all_failed_rules(self):
        err = {"name": "a", "status": "error", "jobs": 0}
        self.assertTrue(C.all_sources_failed([err, {"name": "b", "status": "skipped", "jobs": 0}]))
        self.assertFalse(C.all_sources_failed([{"name": "b", "status": "skipped", "jobs": 0}]))
        self.assertFalse(C.all_sources_failed([err, {"name": "b", "status": "ran", "jobs": 0}]))
        self.assertFalse(C.all_sources_failed([err, {"name": "b", "status": "cached", "jobs": 0}]))
        self.assertFalse(C.all_sources_failed([err, {"name": "b", "status": "cached", "jobs": 3, "last_attempt_failed": True}]))
        self.assertTrue(C.all_sources_failed([err, {"name": "b", "status": "cached", "jobs": 0, "last_attempt_failed": True}]))
        self.assertTrue(C.all_sources_failed([err, {"name": "sources-config", "status": "error", "jobs": 0}]))

    def test_every_board_failing_counts_as_failed(self):
        def down(co, slug):
            raise urllib.error.URLError("no route")
        rows = {"boards": [{"company": "Acme", "ats": "lever", "slug": "acme"}]}
        with mock.patch.dict(C.FETCHERS, {"lever": down}):
            d = json.loads(run_crawl(["--no-hn", "--no-api"], self.F, rows)[1])
        self.assertEqual(d["sources"][0]["status"], "error")
        self.assertIn(C.ALL_FAILED_HINT, d["hints"])

    def test_feed_does_not_blame_filters_when_everything_failed(self):
        tmp = Path(tempfile.mkdtemp()) / "job-feed.md"
        with mock.patch.object(C, "FEED", tmp):
            C.write_feed([], 72, all_failed=True)
        self.assertIn("Every source failed", tmp.read_text())
        self.assertNotIn("Widen with", tmp.read_text())

    def http_error_note(self, code):
        def boom(co, slug):
            raise urllib.error.HTTPError("https://example.test", code, "x", {}, None)
        rows = {"boards": [{"company": "Acme", "ats": "lever", "slug": "acme"}]}
        with mock.patch.dict(C.FETCHERS, {"lever": boom}):
            return json.loads(run_crawl(["--no-hn"], self.F, rows, api=[])[1])["errors"][0]

    def test_rate_limit_is_not_called_a_bad_slug(self):
        note = self.http_error_note(429)
        self.assertIn("rate limited", note)
        self.assertNotIn("bad slug", note)

    def test_server_error_is_not_called_a_bad_slug(self):
        self.assertNotIn("bad slug", self.http_error_note(503))

    def test_404_still_points_at_the_slug(self):
        self.assertIn("bad slug", self.http_error_note(404))


class TestRunReport(NoNetwork):
    """What a run says about itself in its JSON and hints."""
    F = {"lookback_hours": 72, "include_titles": ["welder"], "require_us": False}

    def api_job(self):
        return dict(company="Globex", title="Welder", location="Remote", url="https://remotive.com/1",
                    posted_at=datetime.now(timezone.utc) - timedelta(hours=2), remote=True,
                    description="", source="remotive")

    def test_older_matches_are_pointed_to(self):
        old = dict(self.api_job(), posted_at=datetime.now(timezone.utc) - timedelta(days=20))
        code, out, err = run_crawl([], self.F, {"boards": []}, api=[old], hn_jobs=[])
        d = json.loads(out)
        self.assertEqual(d["dropped"]["age"], 1)
        self.assertTrue([h for h in d["hints"] if "--hours 720" in h], d["hints"])

    def test_deleted_boards_file_says_missing_and_how_to_restore(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(C, "HERE", Path(tmp)):
            code, out, err = run_crawl([], self.F, {"boards": []})
        self.assertEqual(code, 0)
        self.assertIn("boards.yaml is missing", err)
        self.assertIn(C.RESTORE_BOARDS, err)
        self.assertNotIn("ships empty", err)
        boards = next(s for s in json.loads(out)["sources"] if s["name"] == "ats-boards")
        self.assertEqual(boards["status"], "skipped")
        self.assertIn("is missing", boards["reason"])

    def test_empty_boards_file_keeps_the_empty_message(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(C, "HERE", Path(tmp)):
            (Path(tmp) / "boards.yaml").write_text("boards:\n")
            code, _, err = run_crawl([], self.F, {"boards": []})
        self.assertEqual(code, 0)
        self.assertIn("has no company boards yet", err)
        self.assertNotIn("is missing", err)

    def test_invalid_boards_file_still_stops_the_run(self):
        def broken(name):
            raise C.config_files.ConfigError("boards.yaml is not valid YAML near line 2")
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(C, "HERE", Path(tmp)), \
                mock.patch.object(C, "load_yaml", broken), redirect_stdout(io.StringIO()), \
                redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stop:
            (Path(tmp) / "boards.yaml").write_text("boards: [\n")
            (Path(tmp) / "filters.yaml").write_text("include_titles: [welder]\n")
            with mock.patch.object(sys, "argv", ["crawl.py"]):
                C.main()
        self.assertEqual(stop.exception.code, 2)

    BROKEN_ROWS = {"boards": [{"company": "Acme"}, {"ats": "lever"}, "not a row"]}

    def test_all_rows_malformed_gets_a_boards_hint(self):
        code, out, err = run_crawl([], self.F, self.BROKEN_ROWS)
        self.assertEqual(code, 0)
        d = json.loads(out)
        self.assertIn(C.BAD_BOARDS_HINT, d["hints"])
        self.assertNotIn(C.NO_BOARDS_HINT, d["hints"])
        self.assertEqual(len(d["errors"]), 3)

    def test_all_rows_malformed_and_sources_down_never_blames_the_connection_alone(self):
        down = [{"name": "remotive", "label": "Remotive", "status": "error", "jobs": 0, "reason": "HTTP 503"}]
        code, out, err = run_crawl([], self.F, self.BROKEN_ROWS, api=[], report=down, hn_error=RuntimeError("down"))
        self.assertEqual(code, 3)
        d = json.loads(out)
        self.assertIn(C.BAD_BOARDS_HINT, d["hints"])
        self.assertIn(C.BAD_BOARDS_REST_FAILED, d["hints"])
        self.assertNotIn(C.ALL_FAILED_HINT, d["hints"])
        self.assertNotIn("Check your connection", " ".join(d["hints"]))

    def test_one_good_row_gets_no_boards_hint(self):
        rows = {"boards": [{"company": "Acme"}, {"company": "Globex", "ats": "lever", "slug": "globex"}]}
        with mock.patch.dict(C.FETCHERS, {"lever": lambda co, slug: []}):
            d = json.loads(run_crawl([], self.F, rows)[1])
        self.assertNotIn(C.BAD_BOARDS_HINT, d["hints"])

    def test_feed_names_the_boards_when_they_were_the_problem(self):
        tmp = Path(tempfile.mkdtemp()) / "job-feed.md"
        with mock.patch.object(C, "FEED", tmp):
            C.write_feed([], 72, all_failed=True, bad_boards=True)
        self.assertIn("boards.yaml", tmp.read_text())

    def test_wrong_true_false_setting_stops_the_run_plainly(self):
        for bad in ("maybe", None, "false", 1):
            code, out, err = run_crawl([], dict(self.F, require_us=bad), {"boards": []})
            self.assertEqual(code, 2, bad)
            self.assertIn("filters.yaml: require_us must be true or false", err)
            self.assertNotIn("Traceback", err)
            self.assertEqual(out, "")

    def test_no_pyyaml_prints_the_install_line(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(C, "HERE", Path(tmp)), \
                mock.patch.dict(sys.modules, {"yaml": None}), mock.patch.object(sys, "argv", ["crawl.py"]), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as err, \
                self.assertRaises(SystemExit) as stop:
            (Path(tmp) / "filters.yaml").write_text("include_titles: [welder]\n")
            C.main()
        self.assertEqual(stop.exception.code, 2)
        self.assertIn("python3 -m pip install -r pipeline/job-crawler/requirements.txt", err.getvalue())

    def test_raw_jobs_counts_every_source(self):
        rows = {"boards": [{"company": "Acme", "ats": "greenhouse", "slug": "acme"}]}
        board_job = dict(self.api_job(), company="Acme", title="Cashier", url="https://acme.example/1",
                         source="ats")
        hn_job = dict(self.api_job(), company="Initech", title="Baker", url="https://initech.example/1",
                      source="hn")
        api = [self.api_job(), dict(self.api_job(), title="Nurse", url="https://remotive.com/2")]
        with mock.patch.dict(C.FETCHERS, {"greenhouse": lambda company, slug: [board_job]}):
            d = json.loads(run_crawl([], self.F, rows, api=api, hn_jobs=[hn_job])[1])
        self.assertEqual(d["raw_jobs"], 4)
        self.assertEqual(d["boards"], 1)
        self.assertEqual(next(s for s in d["sources"] if s["name"] == "ats-boards")["jobs"], 1)

    def test_an_upper_case_ats_name_is_read(self):
        rows = {"boards": [{"company": "Acme", "ats": "Greenhouse", "slug": "acme"}]}
        board_job = dict(self.api_job(), company="Acme", title="Cashier", url="https://acme.example/1", source="ats")
        with mock.patch.dict(C.FETCHERS, {"greenhouse": lambda company, slug: [board_job]}):
            d = json.loads(run_crawl([], self.F, rows, api=[])[1])
        self.assertEqual((d["boards"], [e for e in d["errors"] if "unknown ats" in e]), (1, []))

    def test_raw_jobs_is_not_zero_with_api_jobs_and_no_boards(self):
        d = json.loads(run_crawl([], self.F, {"boards": []}, api=[self.api_job()])[1])
        self.assertEqual((d["boards"], d["raw_jobs"]), (0, 1))

    def html_failure(self):
        try:
            json.loads("<!doctype html><html></html>")
        except json.JSONDecodeError as e:
            return e

    def test_source_returning_html_reads_plainly(self):
        e = self.html_failure()
        report = [{"name": "remotive", "label": "Remotive", "status": "error", "jobs": 0,
                   "reason": f"{type(e).__name__} {str(e)[:80]}"}]
        d = json.loads(run_crawl([], self.F, {"boards": []}, api=[], report=report)[1])
        got = next(s for s in d["sources"] if s["name"] == "remotive")
        self.assertEqual(got["status"], "error")
        self.assertEqual(got["reason"], C.NOT_DATA)

    def test_one_failed_search_among_several_reads_plainly(self):
        e = self.html_failure()
        got = C.plain_failure(f"2 queries failed and the rest were kept: 'cook': {type(e).__name__} {e}; "
                              f"'baker': HTTP 500")
        self.assertEqual(got, f"2 queries failed and the rest were kept: 'cook': {C.NOT_DATA}; 'baker': HTTP 500")

    def test_other_failures_are_left_alone(self):
        self.assertEqual(C.plain_failure("HTTP 503"), "HTTP 503")

    def test_board_and_hn_returning_html_read_plainly(self):
        e = self.html_failure()
        rows = {"boards": [{"company": "Acme", "ats": "greenhouse", "slug": "acme"}]}

        def board(company, slug):
            raise e
        with mock.patch.dict(C.FETCHERS, {"greenhouse": board}):
            d = json.loads(run_crawl([], self.F, rows, api=[], hn_error=e)[1])
        self.assertTrue(any(C.NOT_DATA in x for x in d["errors"] if x.startswith("Acme")), d["errors"])
        self.assertEqual(next(s for s in d["sources"] if s["name"] == "hn")["reason"], C.NOT_DATA)
        self.assertNotIn("JSONDecodeError", json.dumps(d))


class TestOneClock(NoNetwork):
    """Every date the crawler writes comes from config_files.local_now()."""
    FIXED = datetime(2031, 3, 4, 5, 6, tzinfo=timezone(timedelta(hours=14)))

    def test_json_generated_time(self):
        with mock.patch.object(C.config_files, "local_now", return_value=self.FIXED):
            d = json.loads(run_crawl([], {"include_titles": ["welder"]}, {"boards": []}, api=[])[1])
        self.assertEqual(d["generated"], self.FIXED.isoformat())

    def test_feed_time(self):
        with tempfile.NamedTemporaryFile(suffix=".md") as f, mock.patch.object(C, "FEED", Path(f.name)), \
                mock.patch.object(C.config_files, "local_now", return_value=self.FIXED):
            C.write_feed([], 72)
            self.assertIn("2031-03-04 05:06", Path(f.name).read_text())

    def test_discover_today(self):
        with mock.patch.object(C.config_files, "local_now", return_value=self.FIXED):
            ctx = D.Ctx(cache=Path(tempfile.mkdtemp()), http=D.FakeHttp({}), F={"include_titles": ["x"]})
        self.assertEqual(ctx.today, "2031-03-04")

    def test_clock_selftest(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(C.config_files._selftest(), 0)


class TestEmptyFeed(NoNetwork):
    """An empty feed says what the run's hint says: boards are one source, so search the web too."""
    F = {"include_titles": ["dental hygienist"], "remote_ok": False, "onsite_ok": "home_metros",
         "home_metros": ["tulsa"]}

    def feed(self, F):
        with tempfile.NamedTemporaryFile(suffix=".md") as f, mock.patch.object(C, "FEED", Path(f.name)):
            C.write_feed([], 72, F=F)
            return Path(f.name).read_text()

    def test_points_at_a_web_search(self):
        text = self.feed(self.F)
        self.assertIn("one source, not the only one", text)
        self.assertIn('"dental hygienist jobs tulsa"', text)
        self.assertIn("discover.py --queries", text)
        self.assertNotIn("Widen with", text)

    def test_same_words_as_the_hint(self):
        hint = C.few_matches_hint(0, C.normalize_filters(dict(self.F)))
        tail = hint[hint.index("Search the web"):]
        self.assertIn(tail.replace("|", "\\|"), self.feed(self.F))

    def test_no_filters_still_reads(self):
        self.assertIn('"your job title jobs"', self.feed(None))


class TestOnePostingOneRow(NoNetwork):
    """A posting already in the tracker (from a web search: `jd`/`apply`, no `link`) is not added
    again, however its URL is dressed (tracking keys, a trailing slash, a fragment, http)."""
    X = "https://careers.globex.example/jobs/4411-warehouse-lead"

    def tracker(self):
        tmp = Path(tempfile.mkdtemp()) / "tracker.html"
        tmp.write_text('<script>\nconst UPDATED = "2099-01-01";\nconst APPLICATIONS = [\n'
                       '  {co:"Globex", role:"Warehouse Lead", status:"lead", posted:"unknown", source:"web search", '
                       f'jd:"{self.X}", apply:"{self.X}", folder:"", refs:0, next:"x"}},\n];\n</script>\n')
        return tmp

    def m(self, url):
        return dict(company="Globex", title="Warehouse Lead", location="Reno, NV", url=url, posted_at=None,
                    remote=None, score=0, title_fit=3, matched="warehouse lead", source="ats", no_sponsor_flag=False)

    def test_web_search_row_blocks_the_crawler_row(self):
        tmp = self.tracker()
        with mock.patch.object(C, "TRACKER", tmp):
            got = C.patch_tracker([self.m(self.X), self.m(self.X + "/?utm_source=board&utm_medium=feed"),
                                   self.m("http://www." + self.X[8:] + "#apply"),
                                   self.m(self.X + "?gh_src=abc")])
        self.assertEqual(got["added"], 0)
        self.assertEqual(tmp.read_text().count('co:"'), 1)

    def test_a_different_posting_is_added_once(self):
        tmp = self.tracker()
        other = "https://careers.globex.example/jobs/5520-dispatcher"
        with mock.patch.object(C, "TRACKER", tmp):
            got = C.patch_tracker([self.m(other), self.m(other + "?utm_campaign=x")])
        self.assertEqual(got["added"], 1)

    def test_real_query_keys_still_tell_postings_apart(self):
        a = C.same_posting_key("https://acme.example/job?id=1&utm_source=x")
        self.assertEqual(a, C.same_posting_key("acme.example/job/?id=1"))
        self.assertNotEqual(a, C.same_posting_key("https://acme.example/job?id=2"))

    def test_empty_feed_routes_to_a_lead_row(self):
        with mock.patch.object(C, "TRACKER", self.tracker()):
            text = TestEmptyFeed.feed(self, TestEmptyFeed.F)
        self.assertIn("as a lead row in pipeline/tracker.html", text)


class TestNoRuleLines(unittest.TestCase):
    """No crawler file writes or prints a decorative rule line. Markdown table separators are needed
    syntax and stay. Only code and the README are read, so a user's own YAML comments never fail this."""
    RUN = re.compile(r"([-=_~*#])\1{2,}")
    MULTIPLIED = re.compile(r"""['"][-=_~*#]+['"]\s*\*\s*\w|\w\s*\*\s*['"][-=_~*#]+['"]""")
    PADDED = re.compile(r"""\.(ljust|rjust|center)\([^)]*['"][-=_~*#]['"]|:[-=_~*#][<>^]\d""")
    BOX = re.compile("[\u2500-\u257f]")

    def test_none(self):
        here = Path(C.__file__).resolve().parent
        bad = []
        for path in sorted(here.glob("*.py")) + [here / "README.md"]:
            for n, line in enumerate(path.read_text().splitlines(), 1):
                if "|---" in line or "|:-" in line:
                    continue
                if self.RUN.search(line) or self.MULTIPLIED.search(line) or self.PADDED.search(line) \
                        or self.BOX.search(line):
                    bad.append(f"{path.name}:{n}")
        self.assertEqual(bad, [])


class TestOneClockTracker(NoNetwork):
    """The tracker's dates come from the same clock."""
    FIXED = datetime(2031, 3, 4, 5, 6, tzinfo=timezone(timedelta(hours=14)))

    def match(self):
        return dict(company="Acme", title="Welder", location="Remote", url="https://acme.example/1",
                    posted_at="", source="ats")

    def test_row_found_date(self):
        with mock.patch.object(C.config_files, "local_now", return_value=self.FIXED):
            self.assertIn("on 2031-03-04", C._js_row(self.match()))

    def test_tracker_updated_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            tracker = Path(tmp) / "tracker.html"
            tracker.write_text('const UPDATED = "2000-01-01";\nconst APPLICATIONS = [\n];\n')
            with mock.patch.object(C, "TRACKER", tracker), \
                    mock.patch.object(C.config_files, "local_now", return_value=self.FIXED):
                self.assertEqual(C.patch_tracker([self.match()])["added"], 1)
            self.assertIn('const UPDATED = "2031-03-04";', tracker.read_text())


class TestLivenessUrlWithoutScheme(unittest.TestCase):
    """A URL pasted without https:// is checked, never a ValueError."""
    def test_scheme_is_added_before_fetching(self):
        with mock.patch.object(LV, "http_probe", return_value=(200, "https://careers.acme.example/jobs/1", "", None)) as probe, \
                mock.patch.object(LV, "classify", return_value=("live", "ok")):
            self.assertEqual(LV.check_url("careers.acme.example/jobs/1"), ("live", "ok"))
        self.assertEqual(probe.call_args[0][0], "https://careers.acme.example/jobs/1")

    def test_ats_url_without_scheme_still_resolves(self):
        with mock.patch.object(LV, "check_ats", return_value=("live", "ok")) as ats:
            LV.check_url("boards.greenhouse.io/acme/jobs/1234567")
        self.assertEqual(ats.call_args[0][:2], ("greenhouse", "acme"))

    def test_scheme_is_added_when_a_url_sits_in_the_query(self):
        with mock.patch.object(LV, "http_probe", return_value=(200, "x", "", None)) as probe, \
                mock.patch.object(LV, "classify", return_value=("live", "ok")):
            LV.check_url("acme.example/go?next=https://globex.example/")
        self.assertEqual(probe.call_args[0][0], "https://acme.example/go?next=https://globex.example/")

    def test_url_with_scheme_is_unchanged(self):
        with mock.patch.object(LV, "http_probe", return_value=(200, "http://acme.example/1", "", None)) as probe, \
                mock.patch.object(LV, "classify", return_value=("live", "ok")):
            LV.check_url("http://acme.example/1")
        self.assertEqual(probe.call_args[0][0], "http://acme.example/1")

    def test_empty_boards_file_is_not_a_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "boards.yaml").write_text("boards:\n")
            with mock.patch.object(LV, "HERE", Path(tmp)):
                self.assertEqual(LV.load_boards_map(), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
