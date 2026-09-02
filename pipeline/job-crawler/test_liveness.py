#!/usr/bin/env python3
"""
Offline unit tests for liveness.py — NO network calls. Every input is a synthetic string fed
straight to the pure classifier / resolver / writer helpers. The network-touching layers
(check_ats, http_probe, _fetch_ats_ids) are intentionally NOT exercised here; they are verified
separately against the live boards.

Run:  python3 test_liveness.py           (or: python3 -m unittest test_liveness -v)
"""
import unittest
import liveness as L

# A realistic single-line tracker row (single-quotes only inside values, like the real file).
SAMPLE_ROW = (
    '  {co:"Northwind", role:"Staff Brand Designer", loc:"SF, CA, US", comp:"—", compK:null, '
    'status:"lead", fit:"watch", spon:"ask", posted:"2026-06-29", source:"crawl-jobs", '
    'jd:"https://job-boards.greenhouse.io/northwind/jobs/5995303004", '
    'apply:"https://job-boards.greenhouse.io/northwind/jobs/5995303004", folder:null, refs:0, '
    'everify:"unknown", next:"Read the full JD, tailor, apply.", '
    'link:"https://job-boards.greenhouse.io/northwind/jobs/5995303004", '
    'notes:"Found by the crawler. Fresh ATS pull."},')

LIVE_JD_BODY = (
    "<html><body><h1>Senior Product Designer</h1>"
    "<h2>About the role</h2><p>You will own end-to-end design for our core product surface, "
    "partnering closely with engineering and product to ship polished experiences.</p>"
    "<h2>Responsibilities</h2><ul><li>Lead design for major initiatives</li>"
    "<li>Build and maintain the design system</li></ul>"
    "<h2>Qualifications</h2><ul><li>5+ years of product design experience</li>"
    "<li>Strong portfolio of shipped work</li></ul>"
    "<h2>Benefits</h2><p>Health, dental, equity.</p>"
    "<a href='/apply'>Apply for this job</a></body></html>")

MINI_TRACKER = (
    "<script>\n"
    'const UPDATED = "2026-07-14";\n'
    "\n"
    "const APPLICATIONS = [\n"
    '  {co:"Alpha", role:"Designer", loc:"SF", status:"lead", jd:"https://jobs.ashbyhq.com/alpha/1", '
    'apply:"https://jobs.ashbyhq.com/alpha/1", link:"https://jobs.ashbyhq.com/alpha/1", notes:"x"},\n'
    '  {co:"Beta", role:"PD", loc:"NY", status:"applied", jd:null, apply:null, '
    'link:"https://x.com/b", notes:"y"},\n'
    '  {co:"Gamma", role:"Brand", loc:"—", status:"lead", jd:null, apply:null, notes:"z"}\n'
    "];\n"
    "\n"
    "const NETWORK = [\n"
    '  {name:"Zed", status:"lead", notes:"n"}\n'
    "];\n"
    "</script>\n")


class TestClassify(unittest.TestCase):
    def c(self, status, body, *, final=None, original="https://acme.com/jobs/12345"):
        return L.classify(status, final or original, body, original_url=original)

    def test_404_is_dead(self):
        v, r = self.c(404, "<h1>Not Found</h1>")
        self.assertEqual(v, "dead")
        self.assertIn("404", r)

    def test_410_is_dead(self):
        v, _ = self.c(410, "gone")
        self.assertEqual(v, "dead")

    def test_strong_signal_is_dead(self):
        v, r = self.c(200, "<p>This role has been filled. We are no longer accepting applications.</p>")
        self.assertEqual(v, "dead")
        self.assertIn("closed-signal", r)

    def test_position_filled_is_dead(self):
        v, _ = self.c(200, "<div>This position has been filled — thank you for your interest.</div>")
        self.assertEqual(v, "dead")

    def test_live_jd_is_live(self):
        v, _ = self.c(200, LIVE_JD_BODY)
        self.assertEqual(v, "live")

    def test_live_jd_with_none_status_is_live(self):
        # status unknown (e.g. only a body captured) still resolves off positive JD evidence
        v, _ = self.c(None, LIVE_JD_BODY)
        self.assertEqual(v, "live")

    def test_redirect_to_careers_index_is_dead(self):
        v, r = L.classify(200, "https://acme.com/careers",
                          "<html><body>Explore roles at Acme</body></html>",
                          original_url="https://acme.com/careers/senior-designer-req")
        self.assertEqual(v, "dead")
        self.assertIn("careers index", r)

    def test_redirect_to_site_root_is_dead(self):
        v, _ = L.classify(200, "https://acme.com/", "<html><body>Welcome</body></html>",
                          original_url="https://acme.com/jobs/98765")
        self.assertEqual(v, "dead")

    def test_ambiguous_thin_page_is_uncertain(self):
        v, _ = self.c(200, "<html><body>Loading...</body></html>")
        self.assertEqual(v, "uncertain")

    def test_ambiguous_long_page_no_apply_is_uncertain(self):
        body = "<p>" + ("some company marketing copy about our mission. " * 30) + "</p>"
        v, _ = self.c(200, body)
        self.assertEqual(v, "uncertain")

    def test_single_weak_signal_is_uncertain(self):
        # one generic word alone must NOT be enough to call a lead dead (conservative)
        v, r = self.c(200, "<p>That feature is no longer available in this region.</p>")
        self.assertEqual(v, "uncertain")
        self.assertIn("weak signal", r)

    def test_two_weak_signals_are_dead(self):
        v, r = self.c(200, "<p>This opening is no longer available; the listing has been closed.</p>")
        self.assertEqual(v, "dead")
        self.assertIn("closed-signals", r)

    def test_403_is_uncertain_not_dead(self):
        v, r = self.c(403, "")
        self.assertEqual(v, "uncertain")
        self.assertIn("403", r)

    def test_500_is_uncertain_not_dead(self):
        v, _ = self.c(503, "<h1>Service Unavailable</h1>")
        self.assertEqual(v, "uncertain")

    def test_a_live_jd_that_also_redirected_elsewhere_still_dead(self):
        # a real redirect to an index beats body content (posting was pulled)
        v, _ = L.classify(200, "https://acme.com/jobs", LIVE_JD_BODY,
                          original_url="https://acme.com/jobs/55555")
        self.assertEqual(v, "dead")


class TestResolution(unittest.TestCase):
    def test_detect_ats(self):
        self.assertEqual(L.detect_ats("https://boards.greenhouse.io/figma/jobs/1"), "greenhouse")
        self.assertEqual(L.detect_ats("https://jobs.ashbyhq.com/ramp/uuid"), "ashby")
        self.assertEqual(L.detect_ats("https://jobs.lever.co/foo/uuid"), "lever")
        self.assertEqual(L.detect_ats("https://stripe.com/jobs/search?gh_jid=7144975"), "greenhouse")
        self.assertIsNone(L.detect_ats("https://careers.example.com/founding-engineer"))

    def test_job_id_from_url(self):
        self.assertEqual(
            L.job_id_from_url("https://job-boards.greenhouse.io/northwind/jobs/5986638004", "greenhouse"),
            "5986638004")
        self.assertEqual(
            L.job_id_from_url("https://stripe.com/jobs/search?gh_jid=7144975", "greenhouse"), "7144975")
        self.assertEqual(
            L.job_id_from_url("https://jobs.ashbyhq.com/supabase/4A85C92B-1D0D-43EE-8DBC-0E45A58BE208",
                              "ashby"),
            "4a85c92b-1d0d-43ee-8dbc-0e45a58be208")

    def test_slug_from_url(self):
        self.assertEqual(
            L.slug_from_url("https://job-boards.greenhouse.io/northwind/jobs/1", "greenhouse"), "northwind")
        self.assertEqual(
            L.slug_from_url("https://jobs.ashbyhq.com/supabase/uuid", "ashby"), "supabase")
        self.assertEqual(L.slug_from_url("https://jobs.lever.co/foo/uuid", "lever"), "foo")
        self.assertIsNone(L.slug_from_url("https://stripe.com/jobs/search?gh_jid=7144975", "greenhouse"))

    def test_resolve_target_slug_in_path(self):
        self.assertEqual(
            L.resolve_target("https://job-boards.greenhouse.io/northwind/jobs/5986638004"),
            ("greenhouse", "northwind", "5986638004"))

    def test_resolve_target_company_hosted_needs_boards_map(self):
        url = "https://stripe.com/jobs/search?gh_jid=7144975"
        # without a boards map, the slug is unknowable -> None -> HTTP fallback
        self.assertIsNone(L.resolve_target(url))
        # with the company + boards map, it resolves to the stripe board
        bmap = {"stripe": ("greenhouse", "stripe")}
        self.assertEqual(L.resolve_target(url, company="Stripe", boards_map=bmap),
                         ("greenhouse", "stripe", "7144975"))

    def test_board_lookup_ignores_noise_company(self):
        bmap = {"stripe": ("greenhouse", "stripe"), "ramp": ("ashby", "ramp")}
        self.assertEqual(L._board_lookup("Stripe", bmap), ("greenhouse", "stripe"))
        self.assertIsNone(L._board_lookup("Physical-AGI (via Impax)", bmap))

    def test_has_job_id_and_index(self):
        self.assertTrue(L._has_job_id("https://x.com/jobs/12345"))
        self.assertTrue(L._has_job_id("https://jobs.ashbyhq.com/a/4a85c92b-1d0d-43ee-8dbc-0e45a58be208"))
        self.assertFalse(L._has_job_id("https://x.com/careers"))
        self.assertTrue(L._looks_like_index("https://x.com/careers"))
        self.assertTrue(L._looks_like_index("https://x.com/"))
        self.assertFalse(L._looks_like_index("https://x.com/careers/senior-designer-req"))

    def test_check_url_linkedin_is_uncertain_no_network(self):
        v, r = L.check_url("https://www.linkedin.com/jobs/view/4426522138/")
        self.assertEqual(v, "uncertain")
        self.assertIn("auth-walled", r)

    def test_check_url_empty_is_uncertain(self):
        v, _ = L.check_url(None)
        self.assertEqual(v, "uncertain")


class TestTrackerWriter(unittest.TestCase):
    def test_set_liveness_basic_and_idempotent(self):
        out = L.set_liveness_on_line(SAMPLE_ROW, "dead", "2026-07-14")
        self.assertIsNotNone(out)
        self.assertEqual(out.count('liveness:"'), 1)
        self.assertEqual(out.count('checked:"'), 1)
        self.assertIn('liveness:"dead"', out)
        self.assertIn('checked:"2026-07-14"', out)
        self.assertTrue(out.rstrip().endswith("},"))
        self.assertEqual(L._field(out, "co"), "Northwind")           # untouched
        self.assertEqual(L._field(out, "status"), "lead")          # untouched
        # re-stamp: still exactly one field each, value updated (no duplication)
        again = L.set_liveness_on_line(out, "live", "2026-07-15")
        self.assertEqual(again.count('liveness:"'), 1)
        self.assertIn('liveness:"live"', again)
        self.assertIn('checked:"2026-07-15"', again)
        # same inputs -> identical output (true idempotency)
        self.assertEqual(L.set_liveness_on_line(out, "dead", "2026-07-14"), out)

    def test_set_liveness_rejects_non_row(self):
        self.assertIsNone(L.set_liveness_on_line("not a row object", "dead", "2026-07-14"))

    def test_parse_applications(self):
        rows = L.parse_applications(MINI_TRACKER)
        self.assertEqual(len(rows), 3)
        self.assertEqual([r["co"] for r in rows], ["Alpha", "Beta", "Gamma"])
        self.assertEqual(rows[0]["url"], "https://jobs.ashbyhq.com/alpha/1")
        self.assertEqual(rows[1]["url"], "https://x.com/b")          # apply/jd null -> link
        self.assertIsNone(rows[2]["url"])                            # no apply/jd/link at all

    def test_rewrite_tracker_is_safe_and_validated(self):
        rows = L.parse_applications(MINI_TRACKER)
        updates = {r["idx"]: v for r, v in zip(rows, ["dead", "uncertain", "live"])}
        new_text, note = L.rewrite_tracker(MINI_TRACKER, updates, "2026-07-14")
        self.assertTrue(note.startswith("ok"), note)
        # structure preserved
        self.assertEqual(new_text.count('co:"'), MINI_TRACKER.count('co:"'))
        self.assertEqual(new_text.count("const NETWORK = ["), 1)
        self.assertEqual(len(new_text.split("\n")), len(MINI_TRACKER.split("\n")))
        # every checked row now annotated exactly once
        self.assertEqual(new_text.count('liveness:"'), 3)
        self.assertEqual(new_text.count('checked:"2026-07-14"'), 3)
        # and it still parses back to the same rows
        self.assertEqual(len(L.parse_applications(new_text)), 3)
        # the network row (NETWORK array) was NOT annotated
        self.assertNotIn('name:"Zed", status:"lead", notes:"n", liveness', new_text)

    def test_rewrite_tracker_idempotent(self):
        rows = L.parse_applications(MINI_TRACKER)
        updates = {r["idx"]: "dead" for r in rows}
        once, _ = L.rewrite_tracker(MINI_TRACKER, updates, "2026-07-14")
        rows2 = L.parse_applications(once)
        updates2 = {r["idx"]: "dead" for r in rows2}
        twice, note = L.rewrite_tracker(once, updates2, "2026-07-14")
        self.assertEqual(once, twice)                               # no drift on re-run
        self.assertTrue(note.startswith("already current"), note)


if __name__ == "__main__":
    unittest.main(verbosity=2)
