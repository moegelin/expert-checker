#!/data/data/com.termux/files/usr/bin/bash
# One-time setup of the phone test (docs/plan.md §1, "Hosting decision 2026-11-22"). Run inside Termux:
#
#   pkg install -y git && git clone https://github.com/moegelin/expert-checker.git ~/expert-checker
#   bash ~/expert-checker/phone/setup.sh
#
# Needs the apps Termux, Termux:API and Termux:Boot, all from F-Droid (same signature), with battery
# set to "Unrestricted", and Termux:Boot opened once. The script checks what it can.
set -eu
export PATH="/data/data/com.termux/files/usr/bin:$PATH"
REPO="$HOME/expert-checker"
ENV_FILE="$HOME/.expert-checker.env"

echo "== packages"
pkg install -y python git curl termux-api tzdata

echo "== Termux:API app"
if ! timeout 20 termux-battery-status >/dev/null 2>&1; then
  echo "termux-battery-status gave no answer: install the Termux:API app from F-Droid and allow it to run"
  echo "in the background (battery: Unrestricted), then run this script again."
  exit 1
fi

echo "== Termux:Boot"
mkdir -p "$HOME/.termux/boot"
cp "$REPO/phone/boot.sh" "$HOME/.termux/boot/expert-checker.sh"
chmod +x "$HOME/.termux/boot/expert-checker.sh" "$REPO"/phone/*.sh

echo "== healthchecks.io"
if [ ! -f "$ENV_FILE" ]; then
  printf 'Ping URL of the healthchecks.io check (https://hc-ping.com/<uuid>), empty = no dead-man switch: '
  read -r url
  printf 'HEALTHCHECKS_URL=%s\n' "$url" > "$ENV_FILE"
fi
# shellcheck disable=SC1090
. "$ENV_FILE"
echo "HEALTHCHECKS_URL=${HEALTHCHECKS_URL:-<none>}"

echo "== time zone"
python3 -c 'from zoneinfo import ZoneInfo; ZoneInfo("Europe/Berlin")' \
  || echo "no tz database: the probe assumes CET (UTC+1) for the Berlin hour"

echo "== tests"
(cd "$REPO" && python3 -m unittest discover -q -s tests -t .)

echo "== schedule (hourly, survives reboots)"
bash "$REPO/phone/schedule.sh"
termux-job-scheduler --pending

echo "== first run, by hand"
bash "$REPO/phone/run-probe.sh" manual || true
tail -n 3 "$REPO/data/probe-phone.log"
echo
echo "Setup done. Next: switch Wi-Fi off and run  bash ~/expert-checker/phone/run-probe.sh manual  on mobile data."
