import unittest
from types import SimpleNamespace

from scanner import repo


class FakeGit:
    """Records the git argument lists; `fail` maps the first argument to (returncode, stderr)."""

    def __init__(self, fail=None, staged=True):
        self.calls, self.fail, self.staged = [], fail or {}, staged

    def __call__(self, *args):
        self.calls.append(list(args))
        if args[0] == "diff":
            return SimpleNamespace(returncode=1 if self.staged else 0, stdout="", stderr="")
        code, err = self.fail.get(args[0], (0, ""))
        return SimpleNamespace(returncode=code, stdout="", stderr=err)


class PullTest(unittest.TestCase):
    def test_ok(self):
        g = FakeGit()
        self.assertEqual(repo.pull(g), (True, None))
        self.assertEqual(g.calls, [["pull", "--rebase", "--autostash", "--quiet"]])

    def test_failure_aborts_the_rebase(self):
        g = FakeGit(fail={"pull": (1, "CONFLICT (content): data/status.json\n")})
        ok, error = repo.pull(g)
        self.assertFalse(ok)
        self.assertEqual(error, "CONFLICT (content): data/status.json")
        self.assertEqual(g.calls[1], ["rebase", "--abort"])


class CommitPushTest(unittest.TestCase):
    def test_commit_when_changed(self):
        g = FakeGit()
        self.assertEqual(repo.commit(g, "scan: 2026-11-23 14:40 CET"), (True, None))
        self.assertEqual(g.calls, [["add", "-A", "--", "data"], ["diff", "--cached", "--quiet"],
                                   ["commit", "--quiet", "-m", "scan: 2026-11-23 14:40 CET"]])

    def test_no_commit_without_changes(self):
        g = FakeGit(staged=False)
        self.assertEqual(repo.commit(g, "scan"), (False, None))
        self.assertEqual([c[0] for c in g.calls], ["add", "diff"])

    def test_commit_failure(self):
        g = FakeGit(fail={"commit": (128, "fatal: empty ident name")})
        self.assertEqual(repo.commit(g, "scan"), (False, "fatal: empty ident name"))

    def test_push(self):
        self.assertEqual(repo.push(FakeGit()), (True, None))
        g = FakeGit(fail={"push": (128, "remote: Invalid username or token.\nfatal: Authentication failed")})
        pushed, error = repo.push(g)
        self.assertFalse(pushed)
        self.assertIn("Authentication failed", error)

    def test_git_wrapper_disables_prompts(self):
        seen = {}

        def runner(cmd, **kw):
            seen.update(cmd=cmd, **kw)
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        repo.Git(cwd="/repo", runner=runner, env={"PATH": "/bin"})("status")
        self.assertEqual(seen["cmd"], ["git", "status"])
        self.assertEqual(seen["cwd"], "/repo")
        self.assertEqual(seen["env"], {"PATH": "/bin", "GIT_TERMINAL_PROMPT": "0"})
        self.assertTrue(seen["capture_output"])


if __name__ == "__main__":
    unittest.main()
