"""Client for the unofficial expert.de API. Endpoints and behaviour: docs/expert-api.md."""

import gzip
import http.client
import json
import random
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

BASE_URL = "https://production.brntgs.expert.de"
ONLINE_SHOP = "e_2879130"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/159.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
    "Accept-Language": "de-DE,de;q=0.9",
    "Accept-Encoding": "gzip",
}
STORE_FINDER_BODY = {
    "lat": 0,
    "lng": 0,
    "maxResults": 500,
    "source": "HTML5",
    "withWebsite": True,
    "conditions": {"storeFinderResultFilter": "ALL"},
}

WORKERS = 8
TIMEOUT = 30
RETRIES = 3  # for 5xx, timeouts and connection errors
RETRY_DELAY = (1.0, 2.0)
RATE_LIMIT_WAITS = (2, 4, 8, 16, 32, 60)  # 429 backoff without Retry-After
RETRY_AFTER_MAX = 120
ABORT_MIN_CALLS = 20
ABORT_FAILED_SHARE = 0.20
SNIPPET_CHARS = 200


class ExpertApiError(Exception):
    """A call failed. `outcome` is the call-log outcome, `status` the last HTTP status.

    Also the base class of every error a step raises to say "this step failed, the run goes on" (run.py).
    """

    outcome = "http_error"

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class NetworkError(ExpertApiError):
    outcome = "network"


class ChallengeError(ExpertApiError):
    """Cloudflare challenge: `cf-mitigated`, non-JSON 2xx or non-JSON 403 (Forbidden)."""

    outcome = "challenge"


class RateLimitedError(ExpertApiError):
    """Still 429 (Too Many Requests) after all backoff waits."""

    outcome = "rate_limited"


class ScanAborted(Exception):
    """Too many calls of one `map` failed. `results` holds what the map had so far: results in item order,
    an exception for a failed item, `None` for one that had not finished."""

    def __init__(self, message, results=None):
        super().__init__(message)
        self.results = results


class Response:
    def __init__(self, status, headers, body):
        self.status = status
        self.headers = {k.lower(): v for k, v in headers.items()}
        self.body = body


def urllib_transport(method, url, headers, body, timeout):
    """Send one request. Returns a Response for every HTTP status; raises OSError on network errors."""
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return Response(resp.status, dict(resp.headers.items()), resp.read())
    except urllib.error.HTTPError as e:
        with e:
            return Response(e.code, dict(e.headers.items()), e.read())


class ExpertApi:
    def __init__(self, transport=urllib_transport, sleep=time.sleep, clock=time.monotonic, rng=random.uniform):
        self._transport = transport
        self._sleep = sleep
        self._clock = clock
        self._rng = rng
        self._in_flight = threading.BoundedSemaphore(WORKERS)
        self._gate = threading.Lock()
        self._resume_at = 0.0
        self._rate_waits = 0  # 429 waits since the last successful response
        self._log_lock = threading.Lock()
        self.calls = []

    # Endpoints

    def store_finder(self):
        return self.post_json(
            "/_api/storeFinder/searchStoresByGeoLocation",
            STORE_FINDER_BODY,
            headers={"Cookie": f"fmarktcookie={ONLINE_SHOP}"},
        )

    def pricepds(self, webcode, store_id, retries=RETRIES):
        """`retries` < RETRIES for a store that answered `500` last time too: a store that does not list the
        article answers `500` for good (TCL 65C89L, 2026-11-27), four attempts each would be wasted."""
        return self.get_json("/api/pricepds", retries=retries, webcode=webcode, storeId=store_id)

    def promotion_index(self, store_id):
        return self.get_json("/api/promotions/getIndex", storeId=store_id)

    def bundles_for_article(self, article_id, store_id):
        return self.get_json("/api/search/bundlesForArticle", articleId=article_id, storeId=store_id)

    def search_article(self, webcode):
        return self.get_json("/api/search/article", webcode=webcode)

    def medium(self, medium_id):
        return self.get_json(f"/api/medium/{medium_id}")

    # Requests

    def get_json(self, path, retries=RETRIES, **params):
        query = urllib.parse.urlencode(params)
        return self._call("GET", path, query, None, {}, retries)

    def post_json(self, path, body, headers=None):
        data = json.dumps(body).encode()
        return self._call("POST", path, "", data, {"Content-Type": "application/json", **(headers or {})})

    def _call(self, method, path, query, data, extra_headers, retries=RETRIES):
        url = BASE_URL + path + (f"?{query}" if query else "")
        headers = {**HEADERS, **extra_headers}
        entry = {"endpoint": path, "query": query, "attempts": [], "ms": None, "bytes": None,
                 "dc": None, "outcome": None, "snippet": None, "networkErrors": []}
        retried = 0
        try:
            while True:
                self._wait_for_gate()
                start = self._clock()
                try:
                    with self._in_flight:
                        resp = self._transport(method, url, headers, data, TIMEOUT)
                except (OSError, http.client.HTTPException) as e:
                    entry["ms"] = round((self._clock() - start) * 1000)
                    entry["attempts"].append("timeout" if _is_timeout(e) else "network")
                    entry["networkErrors"].append(f"{entry['ms']} ms: {e!r}"[:SNIPPET_CHARS])
                    if retried < retries:
                        retried += 1
                        self._sleep(self._rng(*RETRY_DELAY))
                        continue
                    raise NetworkError(f"{method} {path}: {e!r}") from e
                entry["ms"] = round((self._clock() - start) * 1000)
                entry["attempts"].append(resp.status)
                body = _decode(resp)
                entry["bytes"] = len(body)
                entry["dc"] = _data_centre(resp.headers.get("cf-ray"))
                payload, is_json = _parse(body)
                if not is_json:
                    entry["snippet"] = body[:SNIPPET_CHARS].decode("utf-8", "replace")

                if "cf-mitigated" in resp.headers:
                    raise ChallengeError(f"{method} {path}: cf-mitigated={resp.headers['cf-mitigated']}", resp.status)
                if resp.status == 429:
                    self._rate_limited(resp.headers.get("retry-after"), path)
                    continue
                if resp.status >= 500:
                    if retried < retries:
                        retried += 1
                        self._sleep(self._rng(*RETRY_DELAY))
                        continue
                    raise ExpertApiError(f"{method} {path}: HTTP {resp.status} after {retried} retries", resp.status)
                if resp.status == 403 and not is_json:
                    raise ChallengeError(f"{method} {path}: non-JSON 403", resp.status)
                if not 200 <= resp.status < 300:
                    raise ExpertApiError(f"{method} {path}: HTTP {resp.status}", resp.status)
                if not is_json:
                    raise ChallengeError(f"{method} {path}: non-JSON body with HTTP {resp.status}", resp.status)
                with self._gate:
                    self._rate_waits = 0
                entry["outcome"] = "ok"
                return payload
        except ExpertApiError as e:
            entry["outcome"] = e.outcome
            raise
        finally:
            with self._log_lock:
                self.calls.append(entry)

    def _wait_for_gate(self):
        while True:
            with self._gate:
                pause = self._resume_at - self._clock()
            if pause <= 0:
                return
            self._sleep(pause)

    def _rate_limited(self, retry_after, path):
        """Close the shared gate for all workers, or give up after the last wait."""
        with self._gate:
            if self._rate_waits >= len(RATE_LIMIT_WAITS):
                raise RateLimitedError(f"{path}: still 429 after {self._rate_waits} waits", 429)
            pause = _retry_after(retry_after)
            if pause is None:
                pause = RATE_LIMIT_WAITS[self._rate_waits]
            self._rate_waits += 1
            self._resume_at = max(self._resume_at, self._clock() + pause)

    # Parallel calls

    def map(self, fn, items, ignore=(), abort=True):
        """Run fn over items on WORKERS threads. Returns results in order; failed items hold their exception.

        Raises ChallengeError and RateLimitedError at once, and ScanAborted (with the results so far) when
        more than 20 % of at least 20 finished calls failed. Items that have not started yet are skipped in
        both cases. Items in `ignore` are expected to fail (stores that answered `500` last time too) and
        count neither as finished nor as failed; `abort=False` turns the 20 % rule off, the challenge and
        rate-limit stops stay.
        """
        items = list(items)
        results = [None] * len(items)
        stop = threading.Event()
        ignore = set(ignore)

        def run(item):
            if stop.is_set():
                raise _Skipped()
            try:
                return fn(item)
            except (ChallengeError, RateLimitedError):
                stop.set()  # stop the other workers at once, before the main thread sees it
                raise

        finished = failed = 0
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = {pool.submit(run, item): i for i, item in enumerate(items)}
            pending = set(futures)
            try:
                while pending:
                    done, pending = wait(pending, return_when=FIRST_COMPLETED)
                    for future in done:
                        error = future.exception()
                        if isinstance(error, _Skipped):
                            continue
                        if isinstance(error, (ChallengeError, RateLimitedError)):
                            raise error
                        index = futures[future]
                        counted = items[index] not in ignore
                        finished += counted
                        if error is not None:
                            failed += counted
                            results[index] = error
                        else:
                            results[index] = future.result()
                    if abort and finished >= ABORT_MIN_CALLS and failed > ABORT_FAILED_SHARE * finished:
                        raise ScanAborted(f"{failed} of {finished} calls failed", results)
            except BaseException:
                stop.set()
                pool.shutdown(wait=True, cancel_futures=True)
                raise
        return results


class _Skipped(Exception):
    pass


def _decode(resp):
    body = resp.body or b""
    if body and resp.headers.get("content-encoding", "").lower() == "gzip":
        try:
            body = gzip.decompress(body)
        except (OSError, EOFError):
            pass  # not gzip after all; _parse reports it as a non-JSON body
    return body


def _parse(body):
    """Returns (payload, is_json). An empty body is JSON `None` (bundlesForArticle for unsold articles)."""
    if not body.strip():
        return None, True
    try:
        return json.loads(body), True
    except ValueError:
        return None, False


def _data_centre(cf_ray):
    if not cf_ray or "-" not in cf_ray:
        return None
    return cf_ray.rsplit("-", 1)[1]


def _retry_after(value):
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    return min(max(seconds, 0), RETRY_AFTER_MAX)


def _is_timeout(error):
    if isinstance(error, TimeoutError):
        return True
    return isinstance(error, urllib.error.URLError) and isinstance(error.reason, TimeoutError)
