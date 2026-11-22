#!/data/data/com.termux/files/usr/bin/bash
# Termux:Boot runs this after a reboot (setup.sh copies it to ~/.termux/boot/expert-checker.sh).
# It only registers the hourly job again. It takes no wake lock: a permanent wake lock would keep
# the CPU awake all day and cost 10–20 % of the battery; run-probe.sh takes one per run instead.
set -eu
export PATH="/data/data/com.termux/files/usr/bin:$PATH"

bash "$HOME/expert-checker/phone/schedule.sh"
echo "$(date '+%Y-%m-%d %H:%M %Z')  boot: job registered" >> "$HOME/expert-checker/data/probe-phone.log"
