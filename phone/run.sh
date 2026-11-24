#!/data/data/com.termux/files/usr/bin/bash
# One scan run on the phone (docs/plan.md §2, §3).
#
#   run.sh            scheduled run (JobScheduler, every 2 h); skipped outside 06:00–22:00 Berlin
#   run.sh manual     run now, by hand, also at night
#
# Holds a wake lock for the run, detects the network, runs `python -m scanner run --push` (lock file,
# git pull, the due steps, data/status.json, commit and push), pings healthchecks.io when
# HEALTHCHECKS_URL is set in ~/.expert-checker.env, and notifies on a failure. Output of the last run:
# data/run-last.md; one line per start: data/scanner.log (both ignored by git).
set -u
export PATH="/data/data/com.termux/files/usr/bin:$PATH"  # JobScheduler starts no login shell
export LANG="${LANG:-en_US.UTF-8}"

REPO="$HOME/expert-checker"
LOG="$REPO/data/scanner.log"
LAST="$REPO/data/run-last.md"
EVENT="${1:-schedule}"
[ -f "$HOME/.expert-checker.env" ] && . "$HOME/.expert-checker.env"
export HEALTHCHECKS_URL="${HEALTHCHECKS_URL:-}" NTFY_TOPIC="${NTFY_TOPIC:-}"

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

python3 -m scanner run --push --event "$EVENT" --network "$network" > "$LAST" 2>&1
rc=$?
status="$(tail -n 1 "$LAST")"
[ -n "$status" ] || status="no output (crash, see data/run-last.md)"

# Exit codes: 0 clean, 1 degraded (a step or the push failed, the run happened), 2 aborted
# (challenge, rate limit, too many failed calls; the scanner sent N7 itself, 1 per 6 h), 3 another run
# holds the lock, anything else = crash (no N7 possible, so this script sends the failure message).
if [ "$rc" -eq 3 ]; then
  echo "$now  $EVENT  $network  skipped (another run is active)" >> "$LOG"
  exit 0
fi
echo "$now  $EVENT  $network  rc=$rc  $status" >> "$LOG"
case "$rc" in
  0) kind=ok ;;
  1) kind=degraded ;;
  2) kind=aborted ;;
  *) kind=failed ;;
esac

if [ -n "$HEALTHCHECKS_URL" ]; then
  if [ "$kind" = ok ] || [ "$kind" = degraded ]; then
    curl -fsS -m 10 --retry 3 -o /dev/null "$HEALTHCHECKS_URL" || true
  else
    tail -c 2000 "$LAST" | curl -fsS -m 10 --retry 3 -o /dev/null --data-binary @- "$HEALTHCHECKS_URL/fail" || true
  fi
fi

# Local Termux notifications only as the ntfy fallback (2026-11-24): after a crash, and after an aborted
# run whose N7 could not be sent (no topic, or the status line says "ntfy failed"). Clean and degraded
# runs post nothing here: the log, the push age on GitHub and healthchecks cover them.
if [ "$kind" = failed ]; then
  python3 -m scanner notify --title "expert-checker: scan crashed ($network, exit $rc)" \
    --message "$now · $status" --tags rotating_light --priority high >/dev/null 2>&1 \
  || termux-notification --id expert-scan-failed --priority high --sound \
       --title "expert-checker: scan crashed ($network, exit $rc)" --content "$now · $status"
elif [ "$kind" = aborted ] && { [ -z "$NTFY_TOPIC" ] || printf '%s' "$status" | grep -q "ntfy failed"; }; then
  termux-notification --id expert-scan-failed --priority high --sound \
    --title "expert-checker: scan aborted ($network)" --content "$now · $status"
fi
exit "$rc"
