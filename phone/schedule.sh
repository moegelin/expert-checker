#!/data/data/com.termux/files/usr/bin/bash
# Registers the scan job with Android's JobScheduler through Termux:API (docs/plan.md §3): every 2 h,
# any network, persisted across reboots. Idempotent: the same job id replaces the previous job (also
# the hourly probe job of the phone test). Used by setup.sh and boot.sh.
#
# The job belongs to the Termux:API app, so it survives when Android kills Termux, and it wakes
# Termux again for the run. No wake lock is held here: run.sh takes one for the run only.
# A periodic job runs once anywhere inside each period; run.sh skips 22:00–06:00, so 8 runs a day.
set -eu
export PATH="/data/data/com.termux/files/usr/bin:$PATH"

termux-job-scheduler \
  --job-id 1 \
  --script "$HOME/expert-checker/phone/run.sh" \
  --period-ms 7200000 \
  --network any \
  --battery-not-low false \
  --persisted true
