"""`python -m scanner run`: one scan run (docs/plan.md §2 and §3).

Takes the lock, pulls the repo (with --push), runs the steps that are due by the cadence table of §3,
evaluates the alert rules (§5, alerts.py), writes data/status.json, commits and pushes data/ (with --push),
and prints one status line last.
Exit codes: 0 clean, 1 degraded (a step, the pull or the push failed; the run happened), 2 aborted
(challenge, rate limit, too many failed calls), 3 another run holds the lock.
"""

import fcntl
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import alerts, prices, repo, sets, stores
from .expert_api import ChallengeError, ExpertApi, ExpertApiError, RateLimitedError, ScanAborted
from .jsonfile import read_json, write_json  # noqa: F401  (tests and steps use run.read_json / run.write_json)
from .notify import Ntfy
from .probe import berlin, detect_runner, iso, parse_time

STEP_ORDER = ("stores", "prices", "sets", "cashback")
STORES_EVERY = timedelta(days=7)
SETS_MOBILE_EVERY = timedelta(hours=24)
CASHBACK_EVERY = timedelta(hours=6)
SLACK = timedelta(minutes=30)  # a periodic job runs anywhere inside its period (finding F5)
STORES_SLACK = timedelta(hours=1)
PUSH_FAILURES_TO_ALERT = 3  # N7 after three failed pushes in a row (≈ 6 h)
STOP_ERRORS = (ChallengeError, RateLimitedError, ScanAborted)
EXIT_OK, EXIT_DEGRADED, EXIT_ABORTED, EXIT_LOCKED = 0, 1, 2, 3

STEPS = {"stores": stores.step, "prices": prices.step, "sets": sets.step}  # name -> fn(ctx) -> summary dict; cashback in M4


class Context:
    """What a step gets: the API client, the data and config dirs, the run's network and time, the push channel."""

    def __init__(self, api, data, network, now, ntfy, status, config=None, options=None):
        self.api = api
        self.data = data
        self.config = config if config is not None else data.parent / "config"
        self.network = network
        self.now = now
        self.ntfy = ntfy
        self.status = status  # the status of the previous run (read-only for steps)
        self.options = options or {}  # sub-command flags, for example {"force": True} for `stores --force`


def main(args, env=os.environ, now=None, steps=None, api=None, git=None, ntfy=None, clock=time.monotonic):
    data = Path(args.data)
    data.mkdir(parents=True, exist_ok=True)
    lock = acquire_lock(data / ".lock")
    if lock is None:
        print("another run is active")
        return EXIT_LOCKED
    try:
        return _run(args, env, now or datetime.now(timezone.utc), steps if steps is not None else STEPS,
                    api, git, ntfy, clock, data)
    finally:
        release_lock(lock)


def _run(args, env, now, steps, api, git, ntfy, clock, data):
    started = clock()
    api = api or ExpertApi()
    ntfy = ntfy or Ntfy(env=env)
    git = git or repo.Git(cwd=str(data.parent))
    push_wanted = bool(getattr(args, "push", False))
    event = getattr(args, "event", None) or "manual"
    network = getattr(args, "network", None) or "unknown"
    previous = read_json(data / "status.json") or {}
    push_state = read_json(data / ".push.json") or {"failures": 0, "last": None, "lastSuccess": None, "error": None}
    warnings = []
    inbox = alerts.Alerts(data, ntfy, now)

    if push_wanted:
        ok, error = repo.pull(git)
        if not ok:
            warnings.append(f"pull failed: {error}")

    due = due_steps(previous, now, network)
    results = dict(previous.get("steps", {}))
    aborted = None
    ctx = Context(api, data, network, now, ntfy, previous)
    for name in STEP_ORDER:
        if aborted is not None:
            break
        if name not in due:
            continue
        fn = steps.get(name)
        if fn is None:
            continue  # not implemented yet: lastRun stays, the step is due again next run
        entry = {**results.get(name, {}), "lastAttempt": iso(now), "ok": False, "error": None}
        calls_before = len(api.calls)
        try:
            summary = fn(ctx) or {}
            entry.update(summary)
            entry["ok"] = True
            entry["lastRun"] = iso(now)
        except STOP_ERRORS as e:
            entry["error"] = f"{type(e).__name__}: {e}"
            aborted = f"{name}: {entry['error']}"
        except ExpertApiError as e:
            entry["error"] = str(e)
        entry["calls"] = len(api.calls) - calls_before
        results[name] = entry

    skipped = [n for n in STEP_ORDER if n not in due]
    failed_steps = [n for n in STEP_ORDER if n in due and n in steps and not results.get(n, {}).get("ok")]
    status = {
        "lastRun": iso(now),
        "berlinTime": berlin(now).strftime("%Y-%m-%d %H:%M"),
        "event": event,
        "network": network,
        "runner": detect_runner(env),
        "aborted": aborted,
        "warnings": warnings,
        "steps": results,
        "skipped": skipped,
        "calls": len(api.calls),
        "alerts": [],
        "durationS": None,
    }
    status["alerts"] = inbox.evaluate(ctx, status)
    warnings.extend(inbox.warnings)
    inbox.save()

    push = {"wanted": push_wanted, "committed": False, "pushed": None, "error": None}
    if push_wanted:
        status["durationS"] = round(clock() - started, 1)
        write_json(data / "status.json", status)
        push = push_data(git, push_state, berlin(now).strftime("%Y-%m-%d %H:%M %Z"), inbox)
        write_json(data / ".push.json", push_state)
        if push["error"]:
            warnings.append(f"push failed ({push_state['failures']} in a row): {push['error']}")
            inbox.save()  # the push alert, if any, lands in the next commit like status.json
    status["durationS"] = round(clock() - started, 1)
    if not push_wanted or push["error"]:
        write_json(data / "status.json", status)  # the push result of this run lands in the next commit

    if aborted:
        code = EXIT_ABORTED
    elif failed_steps or warnings:
        code = EXIT_DEGRADED
    else:
        code = EXIT_OK
    print(status_line(status, push, push_state, code))
    return code


def run_step(args, name, now=None, api=None, ntfy=None, env=os.environ):
    """`python -m scanner stores|prices`: one step on its own (the Mac). Writes the data files, not status.json.
    Exit codes as `run`: 0 ok, 1 failed, 2 aborted, 3 locked."""
    data = Path(args.data)
    data.mkdir(parents=True, exist_ok=True)
    lock = acquire_lock(data / ".lock")
    if lock is None:
        print("another run is active")
        return EXIT_LOCKED
    try:
        api = api or ExpertApi()
        ctx = Context(api, data, getattr(args, "network", None) or "unknown", now or datetime.now(timezone.utc),
                      ntfy or Ntfy(env=env), read_json(data / "status.json") or {},
                      options={"force": bool(getattr(args, "force", False))})
        try:
            summary = STEPS[name](ctx) or {}
        except STOP_ERRORS as e:
            print(f"{name} aborted: {type(e).__name__}: {e} · {len(api.calls)} calls")
            return EXIT_ABORTED
        except ExpertApiError as e:
            print(f"{name} FAILED: {e} · {len(api.calls)} calls")
            return EXIT_DEGRADED
        print(f"{name} ok · {len(api.calls)} calls · " + json.dumps(summary, ensure_ascii=False))
        return EXIT_OK
    finally:
        release_lock(lock)


def push_data(git, push_state, stamp, inbox):
    """Commit `data/` when it changed, push when something is committed or an earlier push failed.
    N7 through `inbox` (alerts.Alerts) after three failed pushes in a row."""
    committed, error = repo.commit(git, f"scan: {stamp}")
    result = {"wanted": True, "committed": committed, "pushed": None, "error": error}
    if error:
        return result
    if not committed and push_state["failures"] == 0:
        return result
    pushed, error = repo.push(git)
    result["pushed"], result["error"] = pushed, error
    push_state["last"] = stamp
    if pushed:
        push_state.update({"failures": 0, "lastSuccess": stamp, "error": None})
    else:
        push_state["failures"] += 1
        push_state["error"] = error
        if push_state["failures"] % PUSH_FAILURES_TO_ALERT == 0:
            inbox.emit("failure", "failure:push",
                       f"{push_state['failures']} pushes in a row failed; the app shows old data. "
                       f"Check the PAT (expiry) and the network. Last error: {error}",
                       priority="high", title="expert-checker: push failed")
    return result


def due_steps(status, now, network):
    last = {name: _last_run(status, name) for name in STEP_ORDER}
    due = {"prices"}
    if _older(last["stores"], now, STORES_EVERY - STORES_SLACK):
        due.add("stores")
    if network == "wifi" or _older(last["sets"], now, SETS_MOBILE_EVERY - SLACK):
        due.add("sets")
    if _older(last["cashback"], now, CASHBACK_EVERY - SLACK):
        due.add("cashback")
    return due


def _last_run(status, name):
    value = (status.get("steps") or {}).get(name, {}).get("lastRun")
    return parse_time(value) if value else None


def _older(last, now, age):
    return last is None or now - last >= age


def acquire_lock(path):
    """Non-blocking exclusive lock on `path`; None when another run holds it (finding F1)."""
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    os.write(fd, f"{os.getpid()}\n".encode())
    return fd


def release_lock(fd):
    fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)


def status_line(status, push, push_state, code):
    kind = {EXIT_OK: "ok", EXIT_DEGRADED: "degraded", EXIT_ABORTED: "aborted"}[code]
    parts = []
    for name in STEP_ORDER:
        s = status["steps"].get(name)
        if name in status["skipped"]:
            parts.append(f"{name} not due")
        elif s is None or s.get("lastAttempt") != status["lastRun"]:
            parts.append(f"{name} –")
        elif s.get("ok"):
            parts.append(f"{name} ok ({s.get('calls', 0)} calls)")
        else:
            parts.append(f"{name} FAILED: {s.get('error')}")
    if not push["wanted"]:
        push_text = "no push"
    elif push["error"]:
        push_text = f"push FAILED ({push_state['failures']} in a row)"
    elif push["pushed"]:
        push_text = "pushed"
    elif push["committed"]:
        push_text = "committed"
    else:
        push_text = "no changes"
    line = f"{kind} · {status['berlinTime']} · {status['network']} · " + " · ".join(parts) + f" · {push_text}"
    if status.get("alerts"):
        line += f" · {len(status['alerts'])} alert(s)"
    if status["aborted"]:
        line += f" · aborted: {status['aborted']}"
    for w in status["warnings"]:
        line += f" · {w}"
    return line

