"""Git steps of a run on the phone (docs/plan.md §2, §3): pull before the scan, commit and push `data/`
after it. Only the phone commits to `data/`, so the rebase never conflicts; if it does, the rebase is
aborted and the run continues with the local code. Credentials come from `git credential.helper store`;
GIT_TERMINAL_PROMPT=0 keeps a missing credential from hanging a scheduled run.
"""

import os
import subprocess

TIMEOUT = 180
TAIL = 300


class Git:
    def __init__(self, cwd=".", runner=subprocess.run, env=os.environ):
        self.cwd = cwd
        self._runner = runner
        self._env = {**env, "GIT_TERMINAL_PROMPT": "0"}

    def __call__(self, *args):
        return self._runner(["git", *args], cwd=self.cwd, capture_output=True, text=True,
                            env=self._env, timeout=TIMEOUT)


def pull(git):
    """`git pull --rebase`. Returns (ok, error)."""
    r = git("pull", "--rebase", "--quiet")
    if r.returncode == 0:
        return True, None
    git("rebase", "--abort")
    return False, _tail(r.stderr or r.stdout) or f"git pull exit {r.returncode}"


def commit(git, message, paths=("data",)):
    """Stages `paths` and commits when something changed. Returns (committed, error)."""
    git("add", "-A", "--", *paths)
    if git("diff", "--cached", "--quiet").returncode == 0:
        return False, None
    r = git("commit", "--quiet", "-m", message)
    if r.returncode != 0:
        return False, _tail(r.stderr or r.stdout) or f"git commit exit {r.returncode}"
    return True, None


def push(git):
    """Returns (pushed, error)."""
    r = git("push", "--quiet")
    if r.returncode == 0:
        return True, None
    return False, _tail(r.stderr or r.stdout) or f"git push exit {r.returncode}"


def _tail(text):
    return (text or "").strip()[-TAIL:]
