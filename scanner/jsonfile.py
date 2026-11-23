"""JSON files of the repo database (docs/plan.md §2, "Repo as database"): stable key order, 2-space indent,
UTF-8 as is, so that the 8 data commits a day stay small deltas."""

import json


def read_json(path):
    """The parsed file, or None when it is missing or not JSON."""
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
