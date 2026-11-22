import argparse
import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scanner import probe
from scanner.expert_api import ExpertApi
from tests.test_expert_api import FakeClock, FakeTransport, html_response, json_response

T0 = datetime(2026, 11, 23, 10, 23, tzinfo=timezone.utc)


def call(outcome="ok", attempts=(200,), ms=200, dc="FRA", snippet=None, check="ok"):
    return {"name": "c", "endpoint": "/api/pricepds", "query": "", "attempts": list(attempts), "ms": ms,
            "bytes": 100, "dc": dc, "outcome": outcome, "snippet": snippet, "networkErrors": [], "check": check}


def sweep(**overrides):
    s = {"stores": 349, "calls": 349, "durationS": 35.0, "firstTry500": 10, "failedAfterRetries": 0,
         "rateLimited429": 0, "challenges": 0, "nonJson": 0, "withOffer": 190, "p50Ms": 200, "p95Ms": 800,
         "aborted": None}
    s.update(overrides)
    return s


def record(hours=0, runner="actions", calls=None, sweep=None, aborted=None, lag=0):
    return {"time": probe.iso(T0 + timedelta(hours=hours)), "runner": runner, "event": "schedule",
            "runId": "1", "scheduleLagMin": lag, "calls": calls if calls is not None else [call()] * 5,
            "sweep": sweep, "aborted": aborted}


def clean_runs(hours=72):
    return [record(h, sweep=sweep() if h % 6 == 0 else None) for h in range(hours + 1)]


class VerdictTest(unittest.TestCase):
    def test_pending_before_72_hours(self):
        s = probe.summarize(clean_runs(71), T0 + timedelta(hours=71))
        self.assertEqual(s["verdict"], "pending")
        self.assertFalse(s["done"])
        self.assertEqual(s["startedAt"], "2026-11-23T10:23:00Z")
        self.assertEqual(s["endsAt"], "2026-11-26T10:23:00Z")

    def test_go_after_72_hours(self):
        s = probe.summarize(clean_runs(72), T0 + timedelta(hours=72))
        self.assertEqual(s["verdict"], "go")
        self.assertTrue(s["done"])
        self.assertEqual(s["reasons"], [])
        self.assertEqual(s["runs"], 73)
        self.assertEqual(s["sweeps"], 13)
        self.assertEqual(s["calls"], 73 * 5 + 13 * 349)
        self.assertEqual(s["firstTry500"], 13 * 10)

    def test_challenge_is_no_go(self):
        runs = clean_runs()
        runs[5] = record(5, calls=[call(outcome="challenge", snippet="<html>", check=None)],
                         aborted="ChallengeError: x")
        s = probe.summarize(runs, T0 + timedelta(hours=72))
        self.assertEqual(s["verdict"], "no-go")
        self.assertEqual(s["challenges"], 1)
        self.assertEqual(s["nonJson"], 1)
        self.assertEqual(s["abortedRuns"], 1)
        self.assertEqual(len(s["reasons"]), 3)

    def test_non_json_body_alone_is_no_go(self):
        runs = clean_runs()
        runs[3] = record(3, sweep=sweep(nonJson=1))
        s = probe.summarize(runs, T0 + timedelta(hours=72))
        self.assertEqual(s["verdict"], "no-go")
        self.assertIn("non-JSON", s["reasons"][0])

    def test_aborted_sweep_is_no_go(self):
        runs = clean_runs()
        runs[6] = record(6, sweep=sweep(aborted="ScanAborted: 80 of 200 calls failed"), aborted="ScanAborted: x")
        self.assertEqual(probe.summarize(runs, T0 + timedelta(hours=72))["verdict"], "no-go")

    def test_ten_percent_first_try_500_is_no_go(self):
        runs = [record(h, calls=[call(attempts=(500, 200))] + [call()] * 9) for h in range(73)]
        s = probe.summarize(runs, T0 + timedelta(hours=72))
        self.assertEqual(s["firstTry500Share"], 0.1)
        self.assertEqual(s["verdict"], "no-go")

    def test_failures_after_retries_and_429_are_shown_not_judged(self):
        runs = clean_runs()
        runs[1] = record(1, calls=[call(outcome="http_error", attempts=(500, 500, 500, 500), check=None),
                                   call(attempts=(429, 200))])
        s = probe.summarize(runs, T0 + timedelta(hours=72))
        self.assertEqual(s["failedAfterRetries"], 1)
        self.assertEqual(s["rateLimited429"], 1)
        self.assertEqual(s["verdict"], "go")

    def test_local_runs_do_not_count(self):
        runs = [record(-5, runner="local", calls=[call(outcome="challenge", check=None)])] + clean_runs()
        s = probe.summarize(runs, T0 + timedelta(hours=72))
        self.assertEqual(s["startedAt"], "2026-11-23T10:23:00Z")
        self.assertEqual(s["verdict"], "go")

    def test_no_actions_run_yet(self):
        s = probe.summarize([record(runner="local")], T0)
        self.assertEqual((s["verdict"], s["runs"], s["startedAt"], s["done"]), ("pending", 0, None, False))

    def test_latency_lag_and_data_centres(self):
        runs = [record(0, calls=[call(ms=100, dc="FRA"), call(ms=300, dc="AMS")], lag=4),
                record(1, calls=[call(ms=200, dc="FRA")], lag=20, sweep=sweep(p95Ms=900))]
        s = probe.summarize(runs, T0 + timedelta(hours=1))
        self.assertEqual(s["latencyMs"], {"p50": 200, "p95": 300, "sweepP95Max": 900})
        self.assertEqual(s["scheduleLagMin"], {"median": 12, "max": 20})
        self.assertEqual(s["dataCentres"], {"FRA": 2, "AMS": 1})


class SweepDueTest(unittest.TestCase):
    def test_auto(self):
        now = T0 + timedelta(hours=6)
        self.assertTrue(probe.sweep_due([], "actions", now, "auto"))
        self.assertTrue(probe.sweep_due([record(0, sweep=sweep())], "actions", now, "auto"))
        self.assertTrue(probe.sweep_due([record(0, sweep=sweep())], "actions", now - timedelta(minutes=20), "auto"))
        self.assertFalse(probe.sweep_due([record(0, sweep=sweep())], "actions", T0 + timedelta(hours=3), "auto"))
        self.assertTrue(probe.sweep_due([record(5, runner="local", sweep=sweep())], "actions", now, "auto"))
        self.assertTrue(probe.sweep_due([record(5, sweep={"skipped": "no store list", "aborted": None})],
                                        "actions", now, "auto"))

    def test_always_and_never(self):
        recent = [record(0, sweep=sweep())]
        self.assertTrue(probe.sweep_due(recent, "actions", T0, "always"))
        self.assertFalse(probe.sweep_due([], "actions", T0, "never"))


def store_finder_payload(count):
    return [{"store": {"id": f"e_{i}", "name": f"expert {i}"}} for i in range(count)]


def fake_expert(store_count=300, overrides=None):
    def answer(url):
        if "storeFinder" in url:
            return json_response(store_finder_payload(store_count))
        if "getIndex" in url:
            return json_response({"indexed": {}, "compactPromotionData": {}, "globalPromotions": {}})
        store = url.rsplit("storeId=", 1)[1]
        price = None if store.endswith("7") else 1999.0
        return json_response({"articleId": "e_1", "price": {"bruttoPrice": price}})
    return FakeTransport(overrides or {}, default=answer)


def fake_api(transport):
    clock = FakeClock()
    return ExpertApi(transport=transport, sleep=clock.sleep, clock=clock.clock)


ACTIONS_ENV = {"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "schedule", "GITHUB_RUN_ID": "42"}


class RunTest(unittest.TestCase):
    def test_clean_run_with_sweep(self):
        transport = fake_expert(overrides={"storeId=e_299": [json_response({}, 500), json_response({"price": {"bruttoPrice": 1.0}, "articleId": "e_1"})]})
        r = probe.run(fake_api(transport), [], "auto", ACTIONS_ENV, T0 + timedelta(minutes=9))
        self.assertEqual([c["name"].split()[0] for c in r["calls"]],
                         ["storeFinder", "pricepds", "pricepds", "pricepds", "getIndex"])
        self.assertTrue(all(c["check"] == "ok" for c in r["calls"]), r["calls"])
        self.assertEqual(r["scheduleLagMin"], 9)
        self.assertEqual(r["runner"], "actions")
        s = r["sweep"]
        self.assertEqual((s["stores"], s["calls"], s["firstTry500"], s["failedAfterRetries"]), (301, 301, 1, 0))
        self.assertEqual(s["withOffer"], 301 - 30)  # e_7, e_17, ..., e_297
        self.assertIsNone(r["aborted"])
        self.assertEqual(probe.exit_code(r), 0)
        self.assertNotIn("1999", json.dumps(r))  # no prices stored

    def test_too_few_stores_fails_the_check(self):
        r = probe.run(fake_api(fake_expert(store_count=12)), [], "never", ACTIONS_ENV, T0)
        self.assertEqual(r["calls"][0]["check"], "12 stores (< 300)")
        self.assertEqual(probe.exit_code(r), 1)

    def test_missing_price_fails_the_check(self):
        transport = fake_expert(overrides={"storeId=e_34627162": [json_response({"articleId": "e_1"})]})
        r = probe.run(fake_api(transport), [], "never", {}, T0)
        sony = next(c for c in r["calls"] if "Sony" in c["name"])
        self.assertEqual(sony["check"], "missing price")
        self.assertEqual(r["runner"], "local")
        self.assertEqual(probe.exit_code(r), 1)

    def test_challenge_stops_the_run(self):
        transport = fake_expert(overrides={"storeFinder": [html_response(200)]})
        r = probe.run(fake_api(transport), [], "always", ACTIONS_ENV, T0)
        self.assertEqual(len(r["calls"]), 1)
        self.assertEqual(r["calls"][0]["outcome"], "challenge")
        self.assertIn("ChallengeError", r["aborted"])
        self.assertIsNone(r["sweep"])
        self.assertEqual(probe.exit_code(r), 1)

    def test_challenge_in_price_calls_stops_the_run(self):
        transport = fake_expert(overrides={"storeId=e_32472581": [html_response(200)]})
        r = probe.run(fake_api(transport), [], "always", ACTIONS_ENV, T0)
        self.assertIn("ChallengeError", r["aborted"])
        self.assertFalse(any(c["name"].startswith("getIndex") for c in r["calls"]))
        lg = next(c for c in r["calls"] if "LG" in c["name"])
        self.assertEqual(lg["outcome"], "challenge")

    def test_store_finder_failure_skips_the_sweep(self):
        transport = fake_expert(overrides={"storeFinder": [json_response({}, 400)]})
        r = probe.run(fake_api(transport), [], "always", ACTIONS_ENV, T0)
        self.assertEqual(r["sweep"], {"skipped": "no store list", "aborted": None})
        self.assertEqual(len(r["calls"]), 5)
        self.assertEqual(probe.exit_code(r), 1)


class MainTest(unittest.TestCase):
    def test_writes_file_summary_and_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            out = tmp / "data" / "probe.json"
            out.parent.mkdir()
            out.write_text(json.dumps({"summary": {}, "records": [record(-72)]}))
            env = {**ACTIONS_ENV, "GITHUB_STEP_SUMMARY": str(tmp / "summary.md"), "GITHUB_OUTPUT": str(tmp / "out")}
            args = argparse.Namespace(out=str(out), sweep="never")
            with contextlib.redirect_stdout(io.StringIO()):
                code = probe.main(args, env=env, now=T0, api=fake_api(fake_expert()))
            self.assertEqual(code, 0)
            data = json.loads(out.read_text())
            self.assertEqual(len(data["records"]), 2)
            self.assertEqual(data["summary"]["verdict"], "go")
            self.assertEqual((tmp / "out").read_text(), "stamp=2026-11-23 10:23 UTC\ndone=true\n")
            markdown = (tmp / "summary.md").read_text()
            self.assertIn("### Verdict: go", markdown)
            self.assertIn("| storeFinder | 200 |", markdown)


if __name__ == "__main__":
    unittest.main()
