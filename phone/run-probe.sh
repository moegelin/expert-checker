#!/data/data/com.termux/files/usr/bin/bash
# One probe run on the phone (docs/plan.md §1, "Hosting decision 2026-11-22").
#
#   run-probe.sh            scheduled run (JobScheduler, hourly); skipped outside 06:00–22:00 Berlin
#   run-probe.sh manual     run now, by hand, also at night
#
# Writes data/probe-phone.json (records + verdict), data/probe-phone.log (one line per start) and
# data/probe-phone-last.md (the output of the last run). Pings healthchecks.io when
# HEALTHCHECKS_URL is set in ~/.expert-checker.env, and posts a notification per run.
set -u
export PATH="/data/data/com.termux/files/usr/bin:$PATH"  # JobScheduler starts no login shell
export LANG="${LANG:-en_US.UTF-8}"

REPO="$HOME/expert-checker"
OUT="$REPO/data/probe-phone.json"
LOG="$REPO/data/probe-phone.log"
LAST="$REPO/data/probe-phone-last.md"
EVENT="${1:-schedule}"
[ -f "$HOME/.expert-checker.env" ] && . "$HOME/.expert-checker.env"
HEALTHCHECKS_URL="${HEALTHCHECKS_URL:-}"

cd "$REPO" || exit 1
mkdir -p data
now="$(TZ=Europe/Berlin date '+%Y-%m-%d %H:%M %Z')"
hour="$(TZ=Europe/Berlin date '+%-H')"
if [ "$EVENT" = schedule ] && { [ "$hour" -lt 6 ] || [ "$hour" -ge 22 ]; }; then
  echo "$now  schedule  skipped (outside 06:00–22:00)" >> "$LOG"
  exit 0
fi

termux-wake-lock
trap 'termux-wake-unlock' EXIT

# Wi-Fi connected with an address → wifi, else mobile data. "unknown" when Termux:API does not answer.
network="$(timeout 15 termux-wifi-connectioninfo 2>/dev/null | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except ValueError:
    print("unknown")
else:
    wifi = d.get("supplicant_state") == "COMPLETED" and d.get("ip") not in (None, "", "0.0.0.0")
    print("wifi" if wifi else "mobile")
' 2>/dev/null)"
[ -n "$network" ] || network=unknown

python3 -m scanner probe --out "$OUT" --event "$EVENT" --network "$network" > "$LAST" 2>&1
rc=$?

status="$(python3 -m scanner probe-status --out "$OUT" 2>/dev/null)"
done_rc=$?  # 0 = the 24 h window is over, 3 = still running
[ -n "$status" ] || status="no summary (probe crashed, see data/probe-phone-last.md)"
echo "$now  $EVENT  $network  rc=$rc  $status" >> "$LOG"

# Exit codes of the probe: 0 clean, 1 degraded (a call failed after retries, the run happened),
# 2 aborted (challenge, rate limit, too many failures), anything else = crash.
case "$rc" in
  0) kind=ok ;;
  1) kind=degraded ;;
  *) kind=failed ;;
esac

if [ -n "$HEALTHCHECKS_URL" ]; then
  if [ "$kind" = failed ]; then
    tail -c 2000 "$LAST" | curl -fsS -m 10 --retry 3 -o /dev/null --data-binary @- "$HEALTHCHECKS_URL/fail" || true
  else
    curl -fsS -m 10 --retry 3 -o /dev/null "$HEALTHCHECKS_URL" || true
  fi
fi

if [ "$kind" = failed ]; then
  termux-notification --id expert-probe-failed --priority high --sound \
    --title "expert probe FAILED ($network, exit $rc)" --content "$now · $status · see data/probe-phone-last.md"
else
  termux-notification --id expert-probe --alert-once --title "expert probe $kind ($network)" --content "$now · $status"
fi

if [ "$done_rc" -eq 0 ]; then
  termux-job-scheduler --cancel --job-id 1 >/dev/null 2>&1 || true
  termux-notification --id expert-probe-done --priority high --sound \
    --title "expert probe: test finished" --content "$status · job cancelled; read data/probe-phone-last.md"
  echo "$now  test finished, job cancelled: $status" >> "$LOG"
fi
exit "$rc"
