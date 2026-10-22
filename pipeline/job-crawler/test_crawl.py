#!/usr/bin/env python3
"""
Offline tests for crawl.py's ranking, its tracker rows, the shared location rule (locations.py),
HN title parsing, the short-title rule (titles.py), the drop counts, and discover.py's
time-budget help: NO network. Every input is synthetic.

Run:  python3 test_crawl.py
"""
import io, json, re, sys, tempfile, unittest, urllib.request
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest import mock

import crawl as C
import discover as D
import hn
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


BASE = {"lookback_hours": 72, "include_titles": ["security engineer"], "require_us": True,
        "us_markers": ["united states", ", co", ", ca"], "location_block": ["ireland", "dublin"]}


class TestLocations(NoNetwork):
    def test_selftest(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(L._selftest(), 0)

    def test_crawl_applies_home_metro_rule(self):
        F = dict(BASE, remote_ok=True, onsite_ok="home_metros", home_metros=["denver"])
        api = [job("Security Engineer", "San Francisco, CA", company="Acme"),
               job("Security Engineer", "Denver, CO", company="Globex"),
               job("Security Engineer", "Remote (United States)", company="Initech"),
               job("Security Engineer", "Dublin, Ireland", company="Northwind")]
        code, out, _ = run_crawl([], F, {"boards": []}, api=api)
        self.assertEqual(code, 0)
        d = json.loads(out)
        self.assertEqual(sorted(m["location"] for m in d["matches"]), ["Denver, CO", "Remote (United States)"])
        self.assertIn("onsite or hybrid in denver", d["location_rule"])

    def test_default_keeps_onsite_anywhere(self):
        code, out, _ = run_crawl([], dict(BASE), {"boards": []}, api=[job("Security Engineer", "San Francisco, CA")])
        self.assertEqual(json.loads(out)["count"], 1)

    def test_bad_setting_is_one_clear_sentence(self):
        code, out, err = run_crawl([], dict(BASE, onsite_ok="home_metros"), {"boards": []})
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("home_metros", err)


class TestRanking(NoNetwork):
    def test_title_fit_levels(self):
        F = {"include_titles": ["security engineer"]}
        fit = lambda t: C.title_fit({"title": t}, F)
        self.assertEqual(fit("Security Engineer"), 3)
        self.assertEqual(fit("Senior Security Engineer, Cloud"), 2)
        self.assertEqual(fit("Application-Security Engineering Lead"), 1)

    def test_rank_without_keywords_uses_fit_then_freshness(self):
        api = [job("Senior Security Engineer II", hours_ago=1), job("Security Engineer", hours_ago=40),
               job("Staff Security Engineer", hours_ago=5)]
        code, out, _ = run_crawl([], dict(BASE), {"boards": []}, api=api)
        d = json.loads(out)
        self.assertEqual([m["title"] for m in d["matches"]],
                         ["Security Engineer", "Senior Security Engineer II", "Staff Security Engineer"])
        self.assertTrue(all(m["score"] == 0 for m in d["matches"]))
        self.assertIn("include_keywords is empty", d["ranking"])

    def test_keywords_rank_first_when_set(self):
        a = job("Senior Security Engineer", hours_ago=1)
        a["description"] = "cloud and kubernetes"
        api = [job("Security Engineer", hours_ago=2), a]
        code, out, _ = run_crawl([], dict(BASE, include_keywords=["kubernetes"]), {"boards": []}, api=api)
        d = json.loads(out)
        self.assertEqual(d["matches"][0]["title"], "Senior Security Engineer")
        self.assertNotIn("include_keywords is empty", d["ranking"])


# The APPLICATIONS row shape (records-format section 1, as the full release's records_check.py
# enforces it): required keys present, posted YYYY-MM-DD or unknown, folder a string ("" or
# applications/<slug>), lowercase keys, `notes` never `note`, no `applied` on a lead row.
REQUIRED = ("co", "role", "status", "posted", "source", "jd", "apply", "folder", "refs", "everify", "next")
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
        m = dict(company="Globex", title="Security Engineer", location="Denver, CO",
                 url="https://example.test/1", posted_at="2099-01-05T00:00:00+00:00", remote=None,
                 score=0, title_fit=3, matched="security engineer", source="ats", no_sponsor_flag=False)
        m.update(kw)
        return parse_row(C._js_row(m))

    def assert_shape(self, r):
        for k in REQUIRED:
            self.assertIn(k, r)
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
        m = dict(company="Globex", title="Security Engineer", location="", url="https://example.test/2",
                 posted_at=None, remote=None, score=0, title_fit=3, matched="x", source="ats",
                 no_sponsor_flag=False)
        with mock.patch.object(C, "TRACKER", tmp):
            self.assertEqual(C.patch_tracker([m])["added"], 1)
            self.assertEqual(C.patch_tracker([m])["added"], 0)  # deduped on the URL
        rows = re.findall(r"\{co:.*?\},", tmp.read_text(), re.S)
        self.assertEqual(len(rows), 1)
        self.assert_shape(parse_row(rows[0]))


class TestHnTitles(NoNetwork):
    F = {"include_titles": ["security engineer", "engineer"], "us_markers": [], "location_block": []}

    def comment(self, header):
        return {"id": 7, "text": header + "<p>Body text.", "created_at": "2099-01-01T00:00:00Z"}

    def test_sentence_is_not_a_title(self):
        garbage = ("Northwind | we are looking for candidates that are excited about privacy and want "
                   "to grow as a security engineer...")
        self.assertIsNone(hn.parse_comment(self.comment(garbage), self.F))
        self.assertTrue(hn.sentence_like("we are looking for candidates that are excited..."))

    def test_real_role_still_parses(self):
        j = hn.parse_comment(self.comment("Northwind | Senior Security Engineer | Remote (US) | Full-time"), self.F)
        self.assertEqual(j["title"], "Senior Security Engineer")
        self.assertEqual(j["company"], "Northwind")

    def test_role_token_beside_a_sentence(self):
        j = hn.parse_comment(self.comment(
            "Northwind | Security Engineer | we are looking for people who want to build"), self.F)
        self.assertEqual(j["title"], "Security Engineer")


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
        walled = job("Security Engineer", "Remote (United States)", company="Initech")
        walled["description"] = "Active clearance required."
        api = [job("Office Manager", company="Acme"),                                   # title
               walled,                                                                  # wall
               job("Security Engineer", "San Francisco, CA", company="Northwind"),      # location
               job("Security Engineer", "Denver, CO", company="Globex", hours_ago=500), # age
               job("Security Engineer", "Denver, CO", company="Hooli")]                 # kept
        code, out, _ = run_crawl([], F, {"boards": []}, api=api)
        d = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(d["count"], 1)
        self.assertEqual({k: d["dropped"][k] for k in ("title", "wall", "location", "age")},
                         {"title": 1, "wall": 1, "location": 1, "age": 1})
        self.assertEqual(set(d["dropped"]), set(d["dropped_reasons"]))

    def test_remote_only_hint_when_remote_not_ok(self):
        F = dict(BASE, remote_ok=False, onsite_ok="home_metros", home_metros=["denver"])
        api = [job("Security Engineer", "Remote (United States)", company="Acme")]
        code, out, err = run_crawl([], F, {"boards": []}, api=api)
        d = json.loads(out)
        hint = [h for h in d["hints"] if "remote_ok is false" in h]
        self.assertEqual(len(hint), 1, d["hints"])
        self.assertIn("Remotive", hint[0])
        self.assertIn("dropped 1 postings", hint[0])
        self.assertEqual(d["dropped"]["location"], 1)
        # a thin HN thread beside a bulk of remote-only jobs still gets the hint
        api3 = [job("Security Engineer", "Remote (United States)", company=c) for c in ("Acme", "Globex", "Initech")]
        hn_jobs = [job("Security Engineer", "Denver, CO", company="Hooli", source="hn")]
        d = json.loads(run_crawl([], F, {"boards": []}, api=api3, hn_jobs=hn_jobs)[1])
        self.assertTrue([h for h in d["hints"] if "3 of the 4 jobs" in h], d["hints"])

    def test_no_remote_only_hint_when_remote_ok_or_onsite_source_ran(self):
        api = [job("Security Engineer", "Remote (United States)", company="Acme")]
        F = dict(BASE, remote_ok=True, onsite_ok="home_metros", home_metros=["denver"])
        d = json.loads(run_crawl([], F, {"boards": []}, api=api)[1])
        self.assertFalse([h for h in d["hints"] if "remote_ok is false" in h])
        F = dict(BASE, remote_ok=False, onsite_ok="home_metros", home_metros=["denver"])
        hn_jobs = [job("Security Engineer", "Denver, CO", company="Globex", source="hn")]
        d = json.loads(run_crawl([], F, {"boards": []}, api=api, hn_jobs=hn_jobs)[1])
        self.assertFalse([h for h in d["hints"] if "remote_ok is false" in h])
        self.assertEqual(d["count"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
