import argparse
import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scanner import run
from scanner.expert_api import ChallengeError, ExpertApiError, ScanAborted
from tests.test_repo import FakeGit

T0 = datetime(2026, 11, 23, 13, 40, tzinfo=timezone.utc)


class FakeApi:
    def __init__(self):
        self.calls = []


class FakeNtfy:
    def __init__(self):
        self.sent = []

    def send(self, title, message, **kw):
        self.sent.append((title, message, kw))
        return True


def step(calls=0, result=None, error=None, log=None, name=None):
    def fn(ctx):
        if log is not None:
            log.append(name)
        ctx.api.calls.extend([{}] * calls)
        if error:
            raise error
        return result
    return fn


def status_with(now, **ages):
    """A previous status whose steps ran `ages` hours ago."""
    return {"steps": {name: {"lastRun": run.iso(now - timedelta(hours=h)), "ok": True} for name, h in ages.items()}}


class DueTest(unittest.TestCase):
    def test_first_run_does_everything(self):
        self.assertEqual(run.due_steps({}, T0, "wifi"), {"stores", "prices", "sets", "cashback"})

    def test_prices_always(self):
        s = status_with(T0, stores=1, prices=1, sets=1, cashback=1)
        self.assertEqual(run.due_steps(s, T0, "mobile"), {"prices"})

    def test_sets_on_wifi_every_run_on_mobile_daily(self):
        s = status_with(T0, stores=1, prices=1, sets=2, cashback=1)
        self.assertIn("sets", run.due_steps(s, T0, "wifi"))
        self.assertNotIn("sets", run.due_steps(s, T0, "mobile"))
        self.assertNotIn("sets", run.due_steps(s, T0, "unknown"))
        s = status_with(T0, stores=1, prices=1, sets=23.6, cashback=1)
        self.assertIn("sets", run.due_steps(s, T0, "mobile"))  # 24 h minus 30 min slack

    def test_cashback_every_six_hours_with_slack(self):
        self.assertNotIn("cashback", run.due_steps(status_with(T0, cashback=5.4), T0, "wifi"))
        self.assertIn("cashback", run.due_steps(status_with(T0, cashback=5.6), T0, "wifi"))

    def test_stores_weekly(self):
        self.assertNotIn("stores", run.due_steps(status_with(T0, stores=24 * 6), T0, "wifi"))
        self.assertIn("stores", run.due_steps(status_with(T0, stores=24 * 7 - 0.5), T0, "wifi"))

    def test_failed_step_is_due_again(self):
        s = {"steps": {"cashback": {"lastAttempt": run.iso(T0 - timedelta(hours=1)), "ok": False}}}
        self.assertIn("cashback", run.due_steps(s, T0, "wifi"))


class LockTest(unittest.TestCase):
    def test_second_lock_fails_until_released(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / ".lock"
            first = run.acquire_lock(path)
            self.assertIsNotNone(first)
            self.assertIsNone(run.acquire_lock(path))
            run.release_lock(first)
            second = run.acquire_lock(path)
            self.assertIsNotNone(second)
            run.release_lock(second)

    def test_main_exits_3_when_locked(self):
        with tempfile.TemporaryDirectory() as d:
            held = run.acquire_lock(Path(d) / ".lock")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = run.main(argparse.Namespace(data=d, event="schedule", network="wifi", push=False),
                                env={}, now=T0, steps={}, api=FakeApi())
            run.release_lock(held)
            self.assertEqual(code, run.EXIT_LOCKED)
            self.assertIn("another run is active", out.getvalue())
            self.assertFalse((Path(d) / "status.json").exists())


class RunTest(unittest.TestCase):
    def go(self, steps, push=False, git=None, network="wifi", event="schedule", previous=None, push_state=None,
           ntfy=None, env=None):
        self.dir = tempfile.TemporaryDirectory()
        data = Path(self.dir.name) / "data"
        data.mkdir()
        if previous is not None:
            run.write_json(data / "status.json", previous)
        if push_state is not None:
            run.write_json(data / ".push.json", push_state)
        self.api, self.ntfy, self.git = FakeApi(), ntfy or FakeNtfy(), git or FakeGit()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = run.main(argparse.Namespace(data=str(data), event=event, network=network, push=push),
                            env=env or {"TERMUX_VERSION": "0.118"}, now=T0, steps=steps, api=self.api,
                            git=self.git, ntfy=self.ntfy, clock=lambda: 0.0)
        self.line = out.getvalue().strip().splitlines()[-1]
        self.status = run.read_json(data / "status.json")
        self.push_state = run.read_json(data / ".push.json")
        self.data = data
        return code

    def tearDown(self):
        self.dir.cleanup()

    def test_clean_run_records_steps_and_skips_the_rest(self):
        log = []
        steps = {"prices": step(calls=349, result={"products": 1}, log=log, name="prices"),
                 "cashback": step(calls=1, log=log, name="cashback")}
        previous = status_with(T0, stores=24, sets=1, cashback=1)
        code = self.go(steps, previous=previous)
        self.assertEqual(code, run.EXIT_OK)
        self.assertEqual(log, ["prices"])
        s = self.status
        self.assertEqual(s["runner"], "termux")
        self.assertEqual(s["event"], "schedule")
        self.assertEqual(s["network"], "wifi")
        self.assertEqual(s["lastRun"], "2026-11-23T13:40:00Z")
        self.assertEqual(s["berlinTime"], "2026-11-23 14:40")
        self.assertEqual(s["calls"], 349)
        self.assertEqual(s["skipped"], ["stores", "cashback"])
        p = s["steps"]["prices"]
        self.assertTrue(p["ok"])
        self.assertEqual((p["lastRun"], p["lastAttempt"], p["calls"], p["products"]),
                         ("2026-11-23T13:40:00Z", "2026-11-23T13:40:00Z", 349, 1))
        self.assertEqual(s["steps"]["cashback"]["lastRun"], previous["steps"]["cashback"]["lastRun"])
        self.assertEqual(self.line, "ok · 2026-11-23 14:40 · wifi · stores not due · prices ok (349 calls) · "
                                    "sets – · cashback not due · no push")

    def test_not_implemented_steps_are_left_alone(self):
        code = self.go({"prices": step(calls=5)})
        self.assertEqual(code, run.EXIT_OK)
        self.assertNotIn("stores", self.status["steps"])
        self.assertEqual(self.status["skipped"], [])

    def test_failed_step_is_degraded_and_keeps_old_last_run(self):
        previous = status_with(T0, cashback=7)
        steps = {"prices": step(calls=5), "cashback": step(calls=1, error=ExpertApiError("HTTP 500 after 3 retries"))}
        code = self.go(steps, previous=previous)
        self.assertEqual(code, run.EXIT_DEGRADED)
        c = self.status["steps"]["cashback"]
        self.assertFalse(c["ok"])
        self.assertEqual(c["error"], "HTTP 500 after 3 retries")
        self.assertEqual(c["lastRun"], previous["steps"]["cashback"]["lastRun"])
        self.assertEqual(c["lastAttempt"], "2026-11-23T13:40:00Z")
        self.assertIn("cashback FAILED: HTTP 500 after 3 retries", self.line)
        self.assertTrue(self.line.startswith("degraded"))

    def test_challenge_aborts_and_stops_the_later_steps(self):
        log = []
        steps = {"stores": step(log=log, name="stores"),
                 "prices": step(error=ChallengeError("GET /api/pricepds: cf-mitigated=challenge"), log=log, name="prices"),
                 "sets": step(log=log, name="sets"), "cashback": step(log=log, name="cashback")}
        code = self.go(steps)
        self.assertEqual(code, run.EXIT_ABORTED)
        self.assertEqual(log, ["stores", "prices"])
        self.assertEqual(self.status["aborted"], "prices: ChallengeError: GET /api/pricepds: cf-mitigated=challenge")
        self.assertTrue(self.status["steps"]["stores"]["ok"])
        self.assertNotIn("sets", self.status["steps"])
        self.assertTrue(self.line.startswith("aborted"))
        self.assertIn("aborted: prices: ChallengeError", self.line)

    def test_scan_aborted_counts_as_aborted(self):
        self.assertEqual(self.go({"prices": step(error=ScanAborted("80 of 100 calls failed"))}), run.EXIT_ABORTED)

    def test_push_commits_and_pushes(self):
        code = self.go({"prices": step(calls=5)}, push=True)
        self.assertEqual(code, run.EXIT_OK)
        self.assertEqual([c[0] for c in self.git.calls], ["pull", "add", "diff", "commit", "push"])
        self.assertEqual(self.git.calls[3], ["commit", "--quiet", "-m", "scan: 2026-11-23 14:40 CET"])
        self.assertEqual(self.push_state, {"failures": 0, "last": "2026-11-23 14:40 CET",
                                           "lastSuccess": "2026-11-23 14:40 CET", "error": None})
        self.assertTrue(self.line.endswith("· pushed"))
        self.assertEqual(self.status["durationS"], 0.0)

    def test_no_changes_no_push(self):
        self.go({"prices": step()}, push=True, git=FakeGit(staged=False))
        self.assertEqual([c[0] for c in self.git.calls], ["pull", "add", "diff"])
        self.assertTrue(self.line.endswith("· no changes"))

    def test_earlier_failed_push_is_retried_without_changes(self):
        self.go({"prices": step()}, push=True, git=FakeGit(staged=False),
                push_state={"failures": 2, "last": "x", "lastSuccess": None, "error": "e"})
        self.assertEqual([c[0] for c in self.git.calls], ["pull", "add", "diff", "push"])
        self.assertEqual(self.push_state["failures"], 0)

    def test_third_failed_push_alerts(self):
        git = FakeGit(fail={"push": (128, "fatal: Authentication failed")})
        code = self.go({"prices": step()}, push=True, git=git,
                       push_state={"failures": 2, "last": "x", "lastSuccess": "y", "error": "e"})
        self.assertEqual(code, run.EXIT_DEGRADED)
        self.assertEqual(self.push_state["failures"], 3)
        self.assertEqual(self.push_state["error"], "fatal: Authentication failed")
        self.assertEqual(len(self.ntfy.sent), 1)
        self.assertEqual(self.ntfy.sent[0][0], "expert-checker: push failed")
        self.assertEqual(self.ntfy.sent[0][2]["priority"], "high")
        self.assertIn("push FAILED (3 in a row)", self.line)
        self.assertEqual(self.status["warnings"], ["push failed (3 in a row): fatal: Authentication failed"])

    def test_first_and_second_failed_push_do_not_alert(self):
        git = FakeGit(fail={"push": (1, "network")})
        self.go({"prices": step()}, push=True, git=git)
        self.assertEqual(self.push_state["failures"], 1)
        self.assertEqual(self.ntfy.sent, [])

    def test_pull_failure_is_a_warning_and_the_run_continues(self):
        log = []
        git = FakeGit(fail={"pull": (1, "CONFLICT")})
        code = self.go({"prices": step(log=log, name="prices")}, push=True, git=git)
        self.assertEqual(code, run.EXIT_DEGRADED)
        self.assertEqual(log, ["prices"])
        self.assertEqual(self.status["warnings"], ["pull failed: CONFLICT"])
        self.assertIn("pull failed: CONFLICT", self.line)
        self.assertEqual([c[0] for c in self.git.calls], ["pull", "rebase", "add", "diff", "commit", "push"])

    def test_without_push_git_is_not_touched(self):
        self.go({"prices": step()})
        self.assertEqual(self.git.calls, [])

    def test_alerts_file_is_written_and_an_abort_sends_n7(self):
        code = self.go({"prices": step(error=ChallengeError("GET /api/pricepds: cf-mitigated=challenge"))})
        self.assertEqual(code, run.EXIT_ABORTED)
        inbox = run.read_json(self.data / "alerts.json")
        self.assertEqual(len(inbox["alerts"]), 1)
        self.assertEqual(inbox["alerts"][0]["kind"], "failure")
        self.assertEqual(self.ntfy.sent[0][0], "expert-checker: scan failed")
        self.assertEqual(self.status["alerts"], ["2026-11-23T13:40:00Z:failure:failure:run"])
        self.assertIn("· 1 alert(s)", self.line)

    def test_clean_run_has_no_alerts(self):
        self.go({"prices": step()})
        self.assertEqual(self.status["alerts"], [])
        self.assertEqual(run.read_json(self.data / "alerts.json")["alerts"], [])
        self.assertNotIn("alert", self.line)

    def test_push_alert_is_in_the_inbox(self):
        git = FakeGit(fail={"push": (128, "fatal: Authentication failed")})
        self.go({"prices": step()}, push=True, git=git,
                push_state={"failures": 2, "last": "x", "lastSuccess": "y", "error": "e"})
        inbox = run.read_json(self.data / "alerts.json")
        self.assertEqual([a["title"] for a in inbox["alerts"]], ["expert-checker: push failed"])

    def test_lock_is_released_after_the_run(self):
        self.go({"prices": step()})
        held = run.acquire_lock(self.data / ".lock")
        self.assertIsNotNone(held)
        run.release_lock(held)


if __name__ == "__main__":
    unittest.main()
