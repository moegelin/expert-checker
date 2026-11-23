"""CLI: python -m scanner <command>."""

import argparse
import sys

from . import notify, probe, run


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

    r = commands.add_parser("run", help="one scan run: the steps that are due, then commit and push (docs/plan.md §3)")
    r.add_argument("--data", default="data", help="data directory (default: data)")
    r.add_argument("--event", choices=("schedule", "manual"), default="manual")
    r.add_argument("--network", choices=("wifi", "mobile", "unknown"), default="unknown")
    r.add_argument("--push", action="store_true", help="git pull before, commit and push data/ after (the phone)")
    r.set_defaults(run=run.main)

    for name, help_text in (("stores", "store finder → data/stores.json (docs/plan.md §3)"),
                            ("prices", "price scan of the watch list → data/products/*.json (docs/plan.md §3)")):
        c = commands.add_parser(name, help=help_text)
        c.add_argument("--data", default="data", help="data directory (default: data)")
        if name == "stores":
            c.add_argument("--force", action="store_true", help="accept a store count that changed by more than 10 %%")
        c.set_defaults(run=lambda args, name=name: run.run_step(args, name))

    n = commands.add_parser("notify", help="send one ntfy message (NTFY_TOPIC from the environment)")
    n.add_argument("--title", required=True)
    n.add_argument("--message", required=True)
    n.add_argument("--click", default=None, help="URL opened on tap")
    n.add_argument("--tags", default=None, help="comma-separated ntfy tags")
    n.add_argument("--priority", default=None, choices=sorted(notify.PRIORITIES))
    n.set_defaults(run=notify.main)

    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
