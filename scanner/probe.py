"""M0 hosting probe, docs/plan.md §3 and §6: do the expert API calls work from GitHub Actions?"""

import json
import math
import os
import statistics
import time
import urllib.parse
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .expert_api import (
    ONLINE_SHOP,
    ChallengeError,
    ExpertApi,
    ExpertApiError,
    RateLimitedError,
    ScanAborted,
)

PRICE_CALLS = [
    # (name, webcode, store id)
    ("pricepds Philips 65OLED951 @ Online-Shop", "11128346052", ONLINE_SHOP),
    ('pricepds Sony BRAVIA 9 II 65" @ Berlin Tauentzien', "11128378730", "e_34627162"),
    ("pricepds LG OLED65C69LB @ Rangsdorf", "11128647509", "e_32472581"),
]
SWEEP_WEBCODE = "11128346052"  # Philips 65OLED951
MIN_STORES = 300
WINDOW = timedelta(hours=72)
SWEEP_EVERY = timedelta(hours=6)
SWEEP_SLACK = timedelta(minutes=30)  # Actions schedules start late by varying amounts
SCHEDULE_MINUTE = 23  # cron "23 * * * *" in probe.yml
MAX_FIRST_TRY_500 = 0.10
STOP_ERRORS = (ChallengeError, RateLimitedError, ScanAborted)


def main(args, env=os.environ, now=None, api=None):
    now = now or datetime.now(timezone.utc)
    api = api or ExpertApi()
    out = Path(args.out)
    data = json.loads(out.read_text()) if out.exists() else {}
    records = data.get("records", [])

    record = run(api, records, args.sweep, env, now)
    records.append(record)
    summary = summarize(records, now)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "records": records}, indent=2, ensure_ascii=False) + "\n")

    markdown = render(record, summary)
    print(markdown)
    if env.get("GITHUB_STEP_SUMMARY"):
        with open(env["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(markdown + "\n")
    if env.get("GITHUB_OUTPUT"):
        with open(env["GITHUB_OUTPUT"], "a") as f:
            f.write(f"stamp={stamp(now)}\ndone={'true' if summary['done'] else 'false'}\n")
    return exit_code(record)


def run(api, records, sweep_mode, env, now, clock=time.monotonic):
    runner = "actions" if env.get("GITHUB_ACTIONS") else "local"
    event = env.get("GITHUB_EVENT_NAME")
    record = {
        "time": iso(now),
        "runner": runner,
        "event": event,
        "runId": env.get("GITHUB_RUN_ID"),
        "scheduleLagMin": (now.minute - SCHEDULE_MINUTE) % 60 if event == "schedule" else None,
        "calls": [],
        "sweep": None,
        "aborted": None,
    }
    try:
        stores = _call(api, record, "storeFinder", api.store_finder, _check_stores)
        _price_calls(api, record)
        _call(api, record, "getIndex Online-Shop", lambda: api.promotion_index(ONLINE_SHOP), _check_index)
        if sweep_due(records, runner, now, sweep_mode):
            record["sweep"] = sweep(api, stores, clock)
            if record["sweep"]["aborted"]:
                record["aborted"] = record["sweep"]["aborted"]
    except STOP_ERRORS as e:
        record["aborted"] = f"{type(e).__name__}: {e}"
    return record


def _call(api, record, name, fn, check):
    start = len(api.calls)
    try:
        payload, error = fn(), None
    except ExpertApiError as e:
        payload, error = None, e
    record["calls"].append(_call_record(name, api.calls[start], payload, error, check))
    if isinstance(error, STOP_ERRORS):
        raise error
    return payload


def _price_calls(api, record):
    start = len(api.calls)
    stop = None
    try:
        results = api.map(lambda c: api.pricepds(c[1], c[2]), PRICE_CALLS)
    except STOP_ERRORS as e:
        results, stop = [None] * len(PRICE_CALLS), e
    entries = api.calls[start:]
    for (name, webcode, store_id), result in zip(PRICE_CALLS, results):
        query = urllib.parse.urlencode({"webcode": webcode, "storeId": store_id})
        entry = next((e for e in entries if e["query"] == query), None)
        if entry is None:  # skipped after a challenge
            continue
        error = result if isinstance(result, Exception) else None
        if stop is not None:  # map raised, so the payloads are gone
            error = stop if entry["outcome"] == stop.outcome else RuntimeError("not checked: run stopped")
        payload = None if error else result
        record["calls"].append(_call_record(name, entry, payload, error, _check_price))
    if stop is not None:
        raise stop


def _call_record(name, entry, payload, error, check):
    call = {"name": name, **entry}
    if error is not None:
        call["check"] = None
        call["error"] = str(error)
    else:
        call["check"] = check(payload) or "ok"
    return call


def _check_stores(payload):
    count = len(payload) if isinstance(payload, list) else 0
    if count < MIN_STORES:
        return f"{count} stores (< {MIN_STORES})"


def _check_price(payload):
    missing = [k for k in ("articleId", "price") if not isinstance(payload, dict) or payload.get(k) is None]
    if missing:
        return "missing " + ", ".join(missing)


def _check_index(payload):
    keys = ("indexed", "compactPromotionData", "globalPromotions")
    missing = [k for k in keys if not isinstance(payload, dict) or payload.get(k) is None]
    if missing:
        return "missing " + ", ".join(missing)


def sweep_due(records, runner, now, mode):
    if mode != "auto":
        return mode == "always"
    sweeps = [r for r in records if r["runner"] == runner and r.get("sweep") and "calls" in r["sweep"]]
    if not sweeps:
        return True
    return now - parse_time(sweeps[-1]["time"]) >= SWEEP_EVERY - SWEEP_SLACK


def sweep(api, stores, clock=time.monotonic):
    """`pricepds` of one TV at every store and the Online-Shop. Keeps totals only, no prices."""
    if not stores:
        return {"skipped": "no store list", "aborted": None}
    store_ids = list(dict.fromkeys([s["store"]["id"] for s in stores] + [ONLINE_SHOP]))
    start, started = len(api.calls), clock()
    aborted = None
    try:
        results = api.map(lambda store_id: api.pricepds(SWEEP_WEBCODE, store_id), store_ids)
    except STOP_ERRORS as e:
        results, aborted = [], f"{type(e).__name__}: {e}"
    duration = clock() - started
    entries = api.calls[start:]
    ms = sorted(e["ms"] for e in entries if e["ms"] is not None)
    return {
        "stores": len(store_ids),
        "calls": len(entries),
        "durationS": round(duration, 1),
        "firstTry500": sum(1 for e in entries if e["attempts"][:1] == [500]),
        "failedAfterRetries": sum(1 for e in entries if e["outcome"] in ("http_error", "network")),
        "rateLimited429": sum(e["attempts"].count(429) for e in entries),
        "challenges": sum(1 for e in entries if e["outcome"] == "challenge"),
        "nonJson": sum(1 for e in entries if e["snippet"] is not None),
        "withOffer": sum(1 for r in results if _has_offer(r)),
        "p50Ms": percentile(ms, 50),
        "p95Ms": percentile(ms, 95),
        "aborted": aborted,
    }


def _has_offer(result):
    return isinstance(result, dict) and (result.get("price") or {}).get("bruttoPrice") is not None


def summarize(records, now):
    """Totals and verdict over the Actions runs; local runs do not count."""
    runs = [r for r in records if r["runner"] == "actions"]
    started = parse_time(runs[0]["time"]) if runs else None
    calls = [c for r in runs for c in r["calls"]]
    sweeps = [r["sweep"] for r in runs if r.get("sweep") and "calls" in r["sweep"]]

    def total(call_test, sweep_key):
        return sum(1 for c in calls if call_test(c)) + sum(s[sweep_key] for s in sweeps)

    call_count = len(calls) + sum(s["calls"] for s in sweeps)
    first_try_500 = total(lambda c: c["attempts"][:1] == [500], "firstTry500")
    challenges = total(lambda c: c["outcome"] == "challenge", "challenges")
    non_json = total(lambda c: c["snippet"] is not None, "nonJson")
    failed = total(lambda c: c["outcome"] in ("http_error", "network"), "failedAfterRetries")
    rate_limited = sum(c["attempts"].count(429) for c in calls) + sum(s["rateLimited429"] for s in sweeps)
    aborted = sum(1 for r in runs if r["aborted"])
    failed_checks = sum(1 for c in calls if c.get("check") not in ("ok", None))
    ms = sorted(c["ms"] for c in calls if c["ms"] is not None)
    lags = [r["scheduleLagMin"] for r in runs if r["scheduleLagMin"] is not None]
    share_500 = first_try_500 / call_count if call_count else 0.0

    reasons = []
    if challenges:
        reasons.append(f"{challenges} challenge(s)")
    if non_json:
        reasons.append(f"{non_json} non-JSON body/bodies")
    if aborted:
        reasons.append(f"{aborted} aborted run(s)")
    if call_count and share_500 >= MAX_FIRST_TRY_500:
        reasons.append(f"{share_500:.1%} of calls had a 500 at the first attempt (limit < 10 %)")

    done = started is not None and now >= started + WINDOW
    if not done:
        verdict = "pending"
    else:
        verdict = "no-go" if reasons else "go"
    return {
        "startedAt": iso(started) if started else None,
        "endsAt": iso(started + WINDOW) if started else None,
        "done": done,
        "verdict": verdict,
        "reasons": reasons,
        "runs": len(runs),
        "sweeps": len(sweeps),
        "calls": call_count,
        "firstTry500": first_try_500,
        "firstTry500Share": round(share_500, 4),
        "failedAfterRetries": failed,
        "rateLimited429": rate_limited,
        "challenges": challenges,
        "nonJson": non_json,
        "abortedRuns": aborted,
        "failedChecks": failed_checks,
        "latencyMs": {"p50": percentile(ms, 50), "p95": percentile(ms, 95),
                      "sweepP95Max": max((s["p95Ms"] for s in sweeps if s["p95Ms"] is not None), default=None)},
        "scheduleLagMin": {"median": statistics.median(lags) if lags else None, "max": max(lags, default=None)},
        "dataCentres": dict(Counter(c["dc"] for c in calls if c["dc"]).most_common()),
    }


def exit_code(record):
    calls_ok = all(c["outcome"] == "ok" and c["check"] == "ok" for c in record["calls"])
    s = record["sweep"] or {}
    sweep_ok = not s.get("failedAfterRetries") and not s.get("challenges")
    return 0 if calls_ok and sweep_ok and not record["aborted"] else 1


def render(record, summary):
    lines = [f"## expert API probe, {stamp(parse_time(record['time']))} ({record['runner']})", ""]
    lines += ["| Call | Status per attempt | ms | KB | DC | Outcome | Check |", "|---|---|---|---|---|---|---|"]
    for c in record["calls"]:
        kb = f"{c['bytes'] / 1024:.0f}" if c["bytes"] is not None else "–"
        check = c["check"] or c.get("error", "–")
        attempts = ", ".join(str(a) for a in c["attempts"])
        lines.append(f"| {c['name']} | {attempts} | {c['ms']} | {kb} | {c['dc'] or '–'} | {c['outcome']} | {check} |")
    for c in record["calls"]:
        if c["snippet"]:
            lines += ["", f"Non-JSON body of {c['name']}: `{c['snippet'][:120]}`"]
        for error in c["networkErrors"]:
            lines += ["", f"Network error of {c['name']}: `{error}`"]
    s = record["sweep"]
    lines.append("")
    if s is None:
        lines.append("Sweep: not due.")
    elif "calls" not in s:
        lines.append(f"Sweep: skipped ({s['skipped']}).")
    else:
        lines.append(
            f"Sweep: {s['calls']} calls for {s['stores']} stores in {s['durationS']} s, "
            f"first-try 500: {s['firstTry500']}, failed after retries: {s['failedAfterRetries']}, "
            f"429: {s['rateLimited429']}, challenges: {s['challenges']}, non-JSON: {s['nonJson']}, "
            f"with offer: {s['withOffer']}, p50 {s['p50Ms']} ms, p95 {s['p95Ms']} ms."
        )
    if record["aborted"]:
        lines += ["", f"**Run aborted:** {record['aborted']}"]

    v = summary
    lines += ["", f"### Verdict: {v['verdict']}"]
    if v["startedAt"]:
        lines.append(f"Actions runs {stamp(parse_time(v['startedAt']))} to {stamp(parse_time(v['endsAt']))}.")
    else:
        lines.append("No Actions run yet.")
    if v["reasons"]:
        lines.append(("Reasons: " if v["verdict"] == "no-go" else "Issues so far: ") + "; ".join(v["reasons"]) + ".")
    lag, lat = v["scheduleLagMin"], v["latencyMs"]
    dcs = ", ".join(f"{k} {n}" for k, n in v["dataCentres"].items()) or "–"
    lines += [
        "",
        "| Runs | Calls | First-try 500 | Failed after retries | 429 | Challenges | Non-JSON | Aborted | "
        "p50 / p95 ms | Sweep p95 max | Schedule lag median / max | Data centres |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
        f"| {v['runs']} | {v['calls']} | {v['firstTry500']} ({v['firstTry500Share']:.1%}) | "
        f"{v['failedAfterRetries']} | {v['rateLimited429']} | {v['challenges']} | {v['nonJson']} | "
        f"{v['abortedRuns']} | {_dash(lat['p50'])} / {_dash(lat['p95'])} | {_dash(lat['sweepP95Max'])} | "
        f"{_dash(lag['median'])} / {_dash(lag['max'])} min | {dcs} |",
    ]
    return "\n".join(lines)


def _dash(value):
    return "–" if value is None else value


def percentile(sorted_values, p):
    """Nearest-rank percentile of an ascending list."""
    if not sorted_values:
        return None
    return sorted_values[max(math.ceil(p / 100 * len(sorted_values)) - 1, 0)]


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(text):
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def stamp(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
