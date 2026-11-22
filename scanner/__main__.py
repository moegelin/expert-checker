"""CLI: python -m scanner <command>."""

import argparse
import sys

from . import probe


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m scanner")
    commands = parser.add_subparsers(dest="command", required=True)

    p = commands.add_parser("probe", help="M0 hosting probe (docs/plan.md §6)")
    p.add_argument("--out", default="data/probe.json", help="probe log (default: data/probe.json)")
    p.add_argument("--sweep", choices=("auto", "always", "never"), default="auto",
                   help="sweep all stores: auto = first run, then when the last sweep is 6 h old")
    p.add_argument("--event", choices=("schedule", "manual"), default=None,
                   help="how the run was started (phone test; Actions sets it from GITHUB_EVENT_NAME)")
    p.add_argument("--network", choices=("wifi", "mobile", "unknown"), default=None,
                   help="network of the run (phone test; phone/run-probe.sh detects it)")
    p.set_defaults(run=probe.main)

    s = commands.add_parser("probe-status", help="one status line of a probe file; exit 0 when its window is done, else 3")
    s.add_argument("--out", default="data/probe.json", help="probe log (default: data/probe.json)")
    s.set_defaults(run=probe.status)

    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
