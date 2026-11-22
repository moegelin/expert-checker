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
    p.set_defaults(run=probe.main)

    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
