#!/data/data/com.termux/files/usr/bin/bash
# Registers the hourly probe job with Android's JobScheduler through Termux:API.
# Idempotent: the same job id replaces the previous job. Used by setup.sh and boot.sh.
#
# The job belongs to the Termux:API app, so it survives when Android kills Termux, and it wakes
# Termux again for the run. No wake lock is held here: run-probe.sh takes one for the run only.
# --battery-not-low false: a low battery must not hide runs during the test.
set -eu
export PATH="/data/data/com.termux/files/usr/bin:$PATH"

termux-job-scheduler \
  --job-id 1 \
  --script "$HOME/expert-checker/phone/run-probe.sh" \
  --period-ms 3600000 \
  --network any \
  --battery-not-low false \
  --persisted true
