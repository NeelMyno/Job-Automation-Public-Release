#!/usr/bin/env python3
"""
One shared way for the crawler to read a URL: asks for gzip (smaller transfers, kinder to the
server) and retries a read that was cut off or timed out, which some networks and proxies do to
large responses. An HTTP error status (404, 429, 500...) is NOT retried here; it is raised as
urllib.error.HTTPError so each caller decides what it means.

If every try is cut off and `curl` is installed, the same GET is made once with curl. Some proxies
(common on work and school networks) truncate large responses to Python's built-in client while
curl reads them in full; without this, those boards would show up as errors on such a network.
Request headers go to curl on its standard input, never on its command line, so a key in a header
(USAJOBS sends one) is not visible to other programs in the process list.

A caller with a time budget passes `deadline` (a time.monotonic() value). Every try, every pause
and the curl retry then get at most the time left, and once it is spent the read stops with
OutOfTime instead of starting another try.

Stdlib only (curl is optional). Used by crawl.py, hn.py, sources.py and discover.py.
"""
import gzip, http.client, io, shutil, socket, subprocess, time, urllib.error, urllib.request
from email.message import Message

# The User-Agent every part of the crawler sends: says what it is and where it lives.
UA = "job-crawler/1.0 (open-source personal job search; polite, low volume)"

TRANSIENT = (http.client.IncompleteRead, http.client.RemoteDisconnected, ConnectionError,
             socket.timeout, TimeoutError)
MIN_TRY_SECONDS = 1.0  # a try with less time than this left is not started


class OutOfTime(TimeoutError):
    """The caller's time budget ran out before the read could finish."""


def _q(v):
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _curl_get(req, timeout):
    """GET `req` with curl. Returns the text, raises HTTPError on a 4xx/5xx, None if curl failed.
    The headers and URL are passed as a curl config on stdin (`-K -`), not as arguments."""
    curl = shutil.which("curl")
    if not curl or req.data is not None or timeout < MIN_TRY_SECONDS:
        return None
    cfg = [f"url = {_q(req.full_url)}"]
    for k, v in req.header_items():
        if k.lower() != "accept-encoding":
            cfg.append(f"header = {_q(f'{k}: {v}')}")
    cmd = [curl, "-sS", "-L", "--compressed", "--max-time", str(max(1, int(timeout))),
           "-w", "\n%{http_code}", "-K", "-"]
    try:
        out = subprocess.run(cmd, input=("\n".join(cfg) + "\n").encode("utf-8"), capture_output=True,
                             timeout=int(timeout) + 3)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    body, _, code = out.stdout.rpartition(b"\n")
    try:
        status = int(code)
    except ValueError:
        return None
    if status >= 400:
        raise urllib.error.HTTPError(req.full_url, status, "HTTP error (via curl)", Message(),
                                     io.BytesIO(body))
    return body.decode("utf-8", "replace")


def read_url(req, timeout=25, tries=3, pause=1.5, deadline=None, clock=time.monotonic,
             sleep=time.sleep, opener=None, curl=None):
    """Read `req` (a urllib.request.Request) and return the decoded text. With `deadline` (a
    clock() value), no try, pause or curl retry runs past it; OutOfTime is raised once it is spent.
    `opener`, `curl`, `clock` and `sleep` exist so the tests can run with no network."""
    opener = opener or urllib.request.urlopen
    curl = curl or _curl_get

    def left():
        return None if deadline is None else deadline - clock()

    def budget(t):
        lt = left()
        return t if lt is None else min(t, lt)

    if not req.has_header("Accept-encoding"):
        req.add_header("Accept-Encoding", "gzip")
    last = None
    for k in range(tries):
        t = budget(timeout)
        if t < MIN_TRY_SECONDS:
            raise OutOfTime(f"time budget spent before {req.full_url} could be read") from last
        try:
            with opener(req, timeout=t) as r:
                body = r.read()
                if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
                    body = gzip.decompress(body)
                return body.decode("utf-8", "replace")
        except urllib.error.HTTPError:
            raise
        except urllib.error.URLError as e:
            if not isinstance(e.reason, TRANSIENT):
                raise
            last = e
        except TRANSIENT as e:
            last = e
        if k < tries - 1:
            p = budget(pause * (k + 1))
            if p > 0:
                sleep(p)
    # No deadline: curl gets twice the timeout (it is the slow-proxy fallback). With one: the
    # same timeout, capped by the time left.
    t = timeout * 2 if deadline is None else budget(timeout)
    text = curl(req, t) if t >= MIN_TRY_SECONDS else None
    if text is not None:
        return text
    if deadline is not None and left() < MIN_TRY_SECONDS:
        raise OutOfTime(f"time budget spent before {req.full_url} could be read") from last
    raise last
