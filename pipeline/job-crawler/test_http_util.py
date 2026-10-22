#!/usr/bin/env python3
"""
Offline tests for http_util.py: NO network. A fake clock, a fake opener and a fake curl stand in
for the real ones, so the time budget and the curl fallback can be checked exactly.

Run:  python3 test_http_util.py
"""
import socket, subprocess, unittest, urllib.request
from unittest import mock

import http_util as H


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def slow_opener(clock, timeouts):
    """Every call 'waits' its full timeout, then times out."""
    def opener(req, timeout):
        timeouts.append(timeout)
        clock.t += timeout
        raise socket.timeout("timed out")
    return opener


def req():
    return urllib.request.Request("https://example.test/jobs", headers={"User-Agent": H.UA})


class TestDeadline(unittest.TestCase):
    def test_no_deadline_keeps_old_behaviour(self):
        clock, timeouts, curl_t = FakeClock(), [], []
        with self.assertRaises(socket.timeout):
            H.read_url(req(), timeout=25, clock=clock, sleep=clock.sleep,
                       opener=slow_opener(clock, timeouts), curl=lambda r, t: curl_t.append(t))
        self.assertEqual(timeouts, [25, 25, 25])
        self.assertEqual(curl_t, [50])

    def test_every_try_and_curl_capped_by_time_left(self):
        clock, timeouts, curl_t = FakeClock(), [], []
        with self.assertRaises(H.OutOfTime):
            H.read_url(req(), timeout=25, deadline=40, clock=clock, sleep=clock.sleep,
                       opener=slow_opener(clock, timeouts), curl=lambda r, t: curl_t.append(t))
        self.assertLessEqual(clock.t, 40)
        self.assertEqual(timeouts[0], 25)
        self.assertTrue(all(t <= 40 for t in timeouts))
        self.assertFalse(curl_t, "no time left, so curl must not start")

    def test_curl_gets_only_the_time_left(self):
        clock, curl_t = FakeClock(), []
        H.read_url(req(), timeout=25, tries=1, deadline=30, clock=clock, sleep=clock.sleep,
                   opener=slow_opener(clock, []), curl=lambda r, t: curl_t.append(t) or "ok")
        self.assertEqual(curl_t, [5])

    def test_spent_deadline_starts_nothing(self):
        clock, timeouts = FakeClock(), []
        clock.t = 100
        with self.assertRaises(H.OutOfTime):
            H.read_url(req(), deadline=99, clock=clock, opener=slow_opener(clock, timeouts))
        self.assertEqual(timeouts, [])


class TestCurlHeaders(unittest.TestCase):
    def test_headers_go_on_stdin_not_argv(self):
        r = urllib.request.Request("https://data.usajobs.gov/api/Search?Keyword=nurse",
                                   headers={"Authorization-Key": "secret-key-123", "User-Agent": "x@y.z"})
        seen = {}

        def fake_run(cmd, input=None, capture_output=None, timeout=None):
            seen["cmd"], seen["input"] = cmd, input
            return subprocess.CompletedProcess(cmd, 0, stdout=b'{"ok": 1}\n200', stderr=b"")
        with mock.patch.object(H.shutil, "which", return_value="/usr/bin/curl"), \
                mock.patch.object(H.subprocess, "run", fake_run):
            self.assertEqual(H._curl_get(r, 20), '{"ok": 1}')
        self.assertFalse([a for a in seen["cmd"] if "secret-key-123" in a or "usajobs" in a])
        self.assertIn(b'header = "Authorization-key: secret-key-123"', seen["input"])
        self.assertIn("-K", seen["cmd"])


class TestUserAgent(unittest.TestCase):
    def test_honest_identifying_agent(self):
        self.assertTrue(H.UA.startswith("job-crawler/"))
        self.assertNotIn("Mozilla", H.UA)


if __name__ == "__main__":
    unittest.main(verbosity=2)
