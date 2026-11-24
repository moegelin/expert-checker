#!/data/data/com.termux/files/usr/bin/bash
# One-time setup of the scanner on the phone (docs/plan.md §2, §3). Run inside Termux:
#
#   pkg install -y git && git clone https://github.com/moegelin/expert-checker.git ~/expert-checker
#   bash ~/expert-checker/phone/setup.sh https://hc-ping.com/<uuid> <ntfy topic>
#
# Both arguments are optional; the script asks for what ~/.expert-checker.env lacks. Safe to run again
# (also after `git pull` to pick up a new job period or boot script).
#
# Needs the apps Termux, Termux:API and Termux:Boot, all from F-Droid (same signature), with battery
# set to "Unrestricted", and Termux:Boot opened once. The script checks what it can.
set -eu
export PATH="/data/data/com.termux/files/usr/bin:$PATH"
REPO="$HOME/expert-checker"
ENV_FILE="$HOME/.expert-checker.env"

echo "== packages"
# Upgrade first: on a fresh Termux, installing packages without an upgrade mixes a new libcurl with
# the old OpenSSL and git's https helper cannot start ("CANNOT LINK EXECUTABLE", seen 2026-11-22).
# apt, not pkg: pkg needs curl, which is the broken piece in that state.
apt update && DEBIAN_FRONTEND=noninteractive apt full-upgrade -y -o Dpkg::Options::="--force-confnew"
pkg install -y python git curl termux-api
# Time zone database for the Berlin hour: Termux has no tzdata package, the pip package does the job.
python3 -m pip install -q tzdata || echo "pip tzdata failed: the scanner assumes CET (UTC+1)"
# pypdf reads the cashback Teilnahmebedingungen PDFs (amounts per model); without it amounts stay unknown.
python3 -m pip install -q pypdf || echo "pip pypdf failed: cashback amounts stay unknown"

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

echo "== secrets (~/.expert-checker.env, never in the repo)"
touch "$ENV_FILE"
# shellcheck disable=SC1090
. "$ENV_FILE"
if [ -n "${1:-}" ]; then HEALTHCHECKS_URL="$1"; fi
if [ -n "${2:-}" ]; then NTFY_TOPIC="$2"; fi
if [ -z "${HEALTHCHECKS_URL:-}" ]; then
  printf 'Ping URL of the healthchecks.io check (https://hc-ping.com/<uuid>), empty = no dead-man switch: '
  read -r HEALTHCHECKS_URL
fi
if [ -z "${NTFY_TOPIC:-}" ]; then
  printf 'ntfy topic (the random name the ntfy app subscribes to), empty = no push: '
  read -r NTFY_TOPIC
fi
printf 'HEALTHCHECKS_URL=%s\nNTFY_TOPIC=%s\n' "$HEALTHCHECKS_URL" "$NTFY_TOPIC" > "$ENV_FILE"
chmod 600 "$ENV_FILE"
echo "HEALTHCHECKS_URL=${HEALTHCHECKS_URL:-<none>}  NTFY_TOPIC=${NTFY_TOPIC:+<set>}${NTFY_TOPIC:-<none>}"

echo "== git identity and token"
cd "$REPO"
git config user.name >/dev/null 2>&1 || git config user.name moegelin
git config user.email >/dev/null 2>&1 || git config user.email 81761762+moegelin@users.noreply.github.com
git config credential.helper store
if ! GIT_TERMINAL_PROMPT=0 git push --dry-run --quiet 2>/dev/null; then
  echo "No stored token. The next line asks for the GitHub user (moegelin) and a fine-grained PAT"
  echo "(this repo, Contents read/write); git stores it in ~/.git-credentials for the scheduled runs."
  git push --dry-run
fi

echo "== time zone"
python3 -c 'from zoneinfo import ZoneInfo; ZoneInfo("Europe/Berlin")' \
  || echo "no tz database: the scanner assumes CET (UTC+1) for the Berlin hour"

echo "== tests"
python3 -m unittest -q tests.test_expert_api tests.test_probe tests.test_notify tests.test_repo tests.test_run tests.test_stores tests.test_prices tests.test_alerts tests.test_sets tests.test_cashback

# The first run comes before the job: a new periodic job starts at once and two runs at the same
# time clobbered the probe file in the phone test (finding F1; the lock file guards it now, too).
echo "== first run, by hand"
bash "$REPO/phone/run.sh" manual || true
tail -n 3 "$REPO/data/scanner.log"

echo "== schedule (every 2 h, survives reboots)"
bash "$REPO/phone/schedule.sh"
termux-job-scheduler --pending
echo
echo "Setup done. Manual run: bash ~/expert-checker/phone/run.sh manual · log: tail ~/expert-checker/data/scanner.log"
