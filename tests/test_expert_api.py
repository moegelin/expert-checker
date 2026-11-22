import gzip
import json
import threading
import unittest

from scanner import expert_api
from scanner.expert_api import (
    ChallengeError,
    ExpertApi,
    ExpertApiError,
    NetworkError,
    RateLimitedError,
    Response,
    ScanAborted,
)


def json_response(payload, status=200, headers=None):
    return Response(status, {"Content-Type": "application/json", "cf-ray": "abc123-FRA", **(headers or {})},
                    json.dumps(payload).encode())


def html_response(status=200, headers=None):
    return Response(status, {"Content-Type": "text/html", **(headers or {})},
                    b"<!DOCTYPE html><html><head><title>Just a moment...</title></head></html>")


SERVER_ERROR = {"error": True, "statusCode": 500, "statusMessage": "Server Error", "message": "Server Error"}


class FakeTransport:
    """Answers each URL from its own script; the last entry repeats. Exceptions in a script are raised."""

    def __init__(self, scripts=None, default=None):
        self.scripts = {k: list(v) for k, v in (scripts or {}).items()}
        self.default = default
        self.requests = []
        self.lock = threading.Lock()

    def __call__(self, method, url, headers, body, timeout):
        with self.lock:
            self.requests.append({"method": method, "url": url, "headers": headers, "body": body, "timeout": timeout})
            key = next((k for k in self.scripts if k in url), None)
            if key is None:
                answer = self.default(url) if callable(self.default) else self.default
            else:
                script = self.scripts[key]
                answer = script.pop(0) if len(script) > 1 else script[0]
        if isinstance(answer, BaseException):
            raise answer
        return answer


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []
        self.on_sleep = None

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        if self.on_sleep:
            hook, self.on_sleep = self.on_sleep, None
            hook()
        self.now += seconds


def make_api(transport):
    clock = FakeClock()
    api = ExpertApi(transport=transport, sleep=clock.sleep, clock=clock.clock)
    return api, clock


class RetryTest(unittest.TestCase):
    def test_500_is_retried_until_success(self):
        transport = FakeTransport({"pricepds": [json_response(SERVER_ERROR, 500)] * 2 + [json_response({"articleId": "e_1"})]})
        api, clock = make_api(transport)
        self.assertEqual(api.pricepds("111", "e_2"), {"articleId": "e_1"})
        self.assertEqual(api.calls[0]["attempts"], [500, 500, 200])
        self.assertEqual(api.calls[0]["outcome"], "ok")
        self.assertEqual(len(clock.sleeps), 2)
        self.assertTrue(all(1 <= s <= 2 for s in clock.sleeps))

    def test_500_gives_up_after_three_retries(self):
        api, clock = make_api(FakeTransport({"pricepds": [json_response(SERVER_ERROR, 500)]}))
        with self.assertRaises(ExpertApiError) as ctx:
            api.pricepds("111", "e_2")
        self.assertNotIsInstance(ctx.exception, ChallengeError)
        self.assertEqual(api.calls[0]["attempts"], [500, 500, 500, 500])
        self.assertEqual(api.calls[0]["outcome"], "http_error")

    def test_html_5xx_is_a_server_error_and_retried(self):
        api, _ = make_api(FakeTransport({"pricepds": [html_response(502), json_response({"articleId": "e_1"})]}))
        self.assertEqual(api.pricepds("111", "e_2"), {"articleId": "e_1"})
        self.assertEqual(api.calls[0]["attempts"], [502, 200])
        self.assertIn("Just a moment", api.calls[0]["snippet"])

    def test_timeout_is_retried(self):
        api, _ = make_api(FakeTransport({"pricepds": [TimeoutError("timed out"), json_response({"ok": 1})]}))
        self.assertEqual(api.pricepds("111", "e_2"), {"ok": 1})
        self.assertEqual(api.calls[0]["attempts"], ["timeout", 200])
        self.assertIn("TimeoutError('timed out')", api.calls[0]["networkErrors"][0])

    def test_connection_errors_raise_network_error(self):
        api, _ = make_api(FakeTransport({"pricepds": [ConnectionResetError("reset")]}))
        with self.assertRaises(NetworkError):
            api.pricepds("111", "e_2")
        self.assertEqual(api.calls[0]["attempts"], ["network"] * 4)
        self.assertEqual(api.calls[0]["outcome"], "network")

    def test_4xx_is_not_retried(self):
        api, clock = make_api(FakeTransport({"pricepds": [json_response({"error": True}, 404)]}))
        with self.assertRaises(ExpertApiError):
            api.pricepds("111", "e_2")
        self.assertEqual(api.calls[0]["attempts"], [404])
        self.assertEqual(clock.sleeps, [])


class RateLimitTest(unittest.TestCase):
    def test_retry_after_is_honoured_and_capped(self):
        transport = FakeTransport({"pricepds": [
            json_response({}, 429, {"Retry-After": "5"}),
            json_response({}, 429, {"Retry-After": "900"}),
            json_response({"ok": 1}),
        ]})
        api, clock = make_api(transport)
        self.assertEqual(api.pricepds("111", "e_2"), {"ok": 1})
        self.assertEqual(clock.sleeps, [5, 120])
        self.assertEqual(api.calls[0]["attempts"], [429, 429, 200])

    def test_backoff_without_retry_after_then_give_up(self):
        api, clock = make_api(FakeTransport({"pricepds": [json_response({}, 429)]}))
        with self.assertRaises(RateLimitedError):
            api.pricepds("111", "e_2")
        self.assertEqual(clock.sleeps, [2, 4, 8, 16, 32, 60])
        self.assertEqual(api.calls[0]["outcome"], "rate_limited")
        self.assertEqual(len(api.calls[0]["attempts"]), 7)

    def test_success_resets_the_backoff(self):
        transport = FakeTransport({
            "storeId=a": [json_response({}, 429), json_response({"ok": "a"})],
            "storeId=b": [json_response({}, 429), json_response({"ok": "b"})],
        })
        api, clock = make_api(transport)
        api.pricepds("1", "a")
        api.pricepds("1", "b")
        self.assertEqual(clock.sleeps, [2, 2])

    def test_gate_pauses_other_workers(self):
        transport = FakeTransport({
            "storeId=a": [json_response({}, 429, {"Retry-After": "10"}), json_response({"ok": "a"})],
            "storeId=b": [json_response({"ok": "b"})],
        })
        api, clock = make_api(transport)
        other = []
        # While worker a waits on the gate, worker b starts a call: it must wait for the same gate.
        clock.on_sleep = lambda: other.append(api.pricepds("1", "b"))
        api.pricepds("1", "a")
        self.assertEqual(other, [{"ok": "b"}])
        self.assertEqual(clock.sleeps, [10, 10])
        urls = [r["url"] for r in transport.requests]
        self.assertEqual([u.rsplit("=", 1)[1] for u in urls], ["a", "b", "a"])


class ChallengeTest(unittest.TestCase):
    def test_cf_mitigated_header(self):
        api, clock = make_api(FakeTransport({"pricepds": [json_response({}, 200, {"cf-mitigated": "challenge"})]}))
        with self.assertRaises(ChallengeError):
            api.pricepds("111", "e_2")
        self.assertEqual(api.calls[0]["outcome"], "challenge")
        self.assertEqual(clock.sleeps, [])

    def test_cf_mitigated_on_5xx_is_not_retried(self):
        api, _ = make_api(FakeTransport({"pricepds": [html_response(503, {"cf-mitigated": "challenge"})]}))
        with self.assertRaises(ChallengeError):
            api.pricepds("111", "e_2")
        self.assertEqual(api.calls[0]["attempts"], [503])

    def test_non_json_2xx(self):
        api, _ = make_api(FakeTransport({"pricepds": [html_response(200)]}))
        with self.assertRaises(ChallengeError):
            api.pricepds("111", "e_2")
        self.assertTrue(api.calls[0]["snippet"].startswith("<!DOCTYPE html>"))
        self.assertLessEqual(len(api.calls[0]["snippet"]), 200)

    def test_non_json_403(self):
        api, _ = make_api(FakeTransport({"pricepds": [html_response(403)]}))
        with self.assertRaises(ChallengeError):
            api.pricepds("111", "e_2")

    def test_json_403_is_a_plain_error(self):
        api, _ = make_api(FakeTransport({"pricepds": [json_response({"error": True}, 403)]}))
        with self.assertRaises(ExpertApiError) as ctx:
            api.pricepds("111", "e_2")
        self.assertNotIsInstance(ctx.exception, ChallengeError)


class ResponseTest(unittest.TestCase):
    def test_empty_2xx_body_is_none(self):
        api, _ = make_api(FakeTransport({"bundles": [Response(200, {}, b"")]}))
        self.assertIsNone(api.get_json("/api/search/bundlesForArticle", articleId="e_1", storeId="e_2"))
        self.assertEqual(api.calls[0]["outcome"], "ok")

    def test_gzip_body_and_call_log(self):
        body = gzip.compress(json.dumps({"articleId": "e_1"}).encode())
        api, _ = make_api(FakeTransport({"pricepds": [Response(200, {"Content-Encoding": "gzip", "CF-RAY": "a5e8-TXL"}, body)]}))
        self.assertEqual(api.pricepds("111", "e_2"), {"articleId": "e_1"})
        entry = api.calls[0]
        self.assertEqual(entry["endpoint"], "/api/pricepds")
        self.assertEqual(entry["query"], "webcode=111&storeId=e_2")
        self.assertEqual(entry["dc"], "TXL")
        self.assertEqual(entry["bytes"], len(b'{"articleId": "e_1"}'))
        self.assertIsNone(entry["snippet"])

    def test_request_headers(self):
        transport = FakeTransport(default=json_response([]))
        api, _ = make_api(transport)
        api.pricepds("111", "e_2")
        api.store_finder()
        get, post = transport.requests
        self.assertEqual(get["method"], "GET")
        self.assertEqual(get["url"], "https://production.brntgs.expert.de/api/pricepds?webcode=111&storeId=e_2")
        self.assertIn("Chrome/159.0.0.0", get["headers"]["User-Agent"])
        self.assertEqual(get["headers"]["Accept"], "application/json")
        self.assertEqual(get["headers"]["Accept-Encoding"], "gzip")
        self.assertEqual(get["timeout"], 30)
        self.assertNotIn("Cookie", get["headers"])
        self.assertEqual(post["method"], "POST")
        self.assertEqual(post["url"], "https://production.brntgs.expert.de/_api/storeFinder/searchStoresByGeoLocation")
        self.assertEqual(post["headers"]["Cookie"], "fmarktcookie=e_2879130")
        self.assertEqual(post["headers"]["Content-Type"], "application/json")
        self.assertEqual(json.loads(post["body"])["maxResults"], 500)


class MapTest(unittest.TestCase):
    def test_results_in_order_with_failures_in_place(self):
        transport = FakeTransport({"storeId=s3": [json_response({}, 404)]},
                                  default=lambda url: json_response({"store": url.rsplit("=", 1)[1]}))
        api, _ = make_api(transport)
        results = api.map(lambda s: api.pricepds("1", s), [f"s{i}" for i in range(10)])
        self.assertEqual(results[0], {"store": "s0"})
        self.assertIsInstance(results[3], ExpertApiError)
        self.assertEqual(results[9], {"store": "s9"})

    def test_challenge_stops_the_map(self):
        challenged = threading.Event()
        sent = []

        def transport(method, url, headers, body, timeout):
            sent.append(url)
            if url.endswith("storeId=s0"):
                challenged.set()
                return html_response(200)
            return json_response({"ok": 1})

        api, _ = make_api(transport)

        def fn(store):
            if store != "s0":
                challenged.wait(5)  # the other workers start only after s0 was challenged
            return api.pricepds("1", store)

        with self.assertRaises(ChallengeError):
            api.map(fn, [f"s{i}" for i in range(200)])
        self.assertLess(len(sent), 100)

    def test_abort_when_more_than_20_percent_fail(self):
        transport = FakeTransport(default=lambda url: json_response({}, 404) if int(url.rsplit("s", 1)[1]) % 4 == 0
                                  else json_response({"ok": 1}))
        api, _ = make_api(transport)
        with self.assertRaises(ScanAborted):
            api.map(lambda s: api.pricepds("1", s), [f"s{i}" for i in range(200)])

    def test_20_percent_failures_do_not_abort(self):
        transport = FakeTransport(default=lambda url: json_response({}, 404) if int(url.rsplit("s", 1)[1]) % 5 == 0
                                  else json_response({"ok": 1}))
        api, _ = make_api(transport)
        results = api.map(lambda s: api.pricepds("1", s), [f"s{i}" for i in range(20)])
        self.assertEqual(sum(isinstance(r, ExpertApiError) for r in results), 4)

    def test_at_most_8_requests_in_flight(self):
        lock, state = threading.Lock(), {"now": 0, "max": 0}
        release = threading.Event()

        def transport(method, url, headers, body, timeout):
            with lock:
                state["now"] += 1
                state["max"] = max(state["max"], state["now"])
                if state["now"] == expert_api.WORKERS:
                    release.set()
            release.wait(5)
            with lock:
                state["now"] -= 1
            return json_response({"ok": 1})

        api, _ = make_api(transport)
        api.map(lambda s: api.pricepds("1", s), range(40))
        self.assertEqual(state["max"], expert_api.WORKERS)


if __name__ == "__main__":
    unittest.main()
