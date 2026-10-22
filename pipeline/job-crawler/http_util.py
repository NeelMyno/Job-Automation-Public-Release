#!/usr/bin/env python3
"""
One shared way for the crawler to read a URL: asks for gzip (smaller transfers, kinder to the
server) and retries a read that was cut off or timed out, which some networks and proxies do to
large responses. An HTTP error status (404, 429, 500...) is NOT retried here; it is raised as
urllib.error.HTTPError so each caller decides what it means.

If every try is cut off and `curl` is installed, the same GET is made once with curl. Some proxies
(common on work and school networks) truncate large responses to Python's built-in client while
curl reads them in full; without this, those boards would show up as errors on such a network.

Stdlib only (curl is optional). Used by crawl.py, hn.py, sources.py and discover.py.
"""
import gzip, http.client, io, shutil, socket, subprocess, time, urllib.error, urllib.request
from email.message import Message

TRANSIENT = (http.client.IncompleteRead, http.client.RemoteDisconnected, ConnectionError,
             socket.timeout, TimeoutError)


def _curl_get(req, timeout):
    """GET `req` with curl. Returns the text, raises HTTPError on a 4xx/5xx, None if curl failed."""
    curl = shutil.which("curl")
    if not curl or req.data is not None:
        return None
    cmd = [curl, "-sS", "-L", "--compressed", "--max-time", str(int(timeout) * 2),
           "-w", "\n%{http_code}"]
    for k, v in req.header_items():
        if k.lower() != "accept-encoding":
            cmd += ["-H", f"{k}: {v}"]
    cmd.append(req.full_url)
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=int(timeout) * 2 + 5)
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


def read_url(req, timeout=25, tries=3, pause=1.5):
    """Read `req` (a urllib.request.Request) and return the decoded text."""
    if not req.has_header("Accept-encoding"):
        req.add_header("Accept-Encoding", "gzip")
    last = None
    for k in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
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
            time.sleep(pause * (k + 1))
    text = _curl_get(req, timeout)
    if text is not None:
        return text
    raise last
