"""The systemd units and run.sh behave as the README promises: paths with a space survive
systemd's parsing, and a push run that ends with alerts still commits state/pushed.json."""

from __future__ import annotations

import os
import shlex
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = ROOT / "deploy"


class UnitFileTests(unittest.TestCase):
    def test_environment_assignments_survive_systemd_word_splitting(self) -> None:
        # systemd unquotes Environment= lines and splits them on whitespace into
        # KEY=VALUE words, so an unquoted path with a space becomes two assignments and
        # the second half is dropped ("Invalid environment assignment, ignoring").
        # The repo path has a space ("Github Projects"), so every value must be quoted.
        for unit in ("airep-social.service", "airep-social.timer"):
            for line in (DEPLOY / unit).read_text(encoding="utf-8").splitlines():
                if not line.startswith("Environment="):
                    continue
                words = shlex.split(line.split("=", 1)[1])
                for word in words:
                    self.assertIn("=", word, f"{unit}: {word!r} is not a KEY=VALUE assignment")
                    key, value = word.split("=", 1)
                    self.assertTrue(key.isidentifier(), f"{unit}: bad key {key!r}")
                    if key == "AIREP_SOCIAL_PYTHON":
                        self.assertTrue(
                            value.endswith("/venv/bin/python"), f"{unit}: truncated {value!r}"
                        )

    def test_service_runs_the_repo_script_from_the_repo(self) -> None:
        text = (DEPLOY / "airep-social.service").read_text(encoding="utf-8")
        self.assertIn(f"WorkingDirectory={ROOT}\n", text)
        self.assertIn(f'ExecStart=/usr/bin/env bash "{DEPLOY / "run.sh"}"\n', text)


class RunShTests(unittest.TestCase):
    """run.sh against a throwaway repo and a stand-in python; no network, no Buffer."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self.repo = tmp / "repo"
        (self.repo / "deploy").mkdir(parents=True)
        (self.repo / "state").mkdir()
        (self.repo / "site" / "images").mkdir(parents=True)
        (self.repo / "deploy" / "run.sh").write_bytes((DEPLOY / "run.sh").read_bytes())
        (self.repo / "state" / "pushed.json").write_text('{\n  "posts": {}\n}\n')
        self.env = env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@x",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@x",
        }
        self._git("init", "-q", "-b", "main")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "init")
        origin = tmp / "origin.git"
        subprocess.run(
            ["git", "clone", "-q", "--bare", str(self.repo), str(origin)], check=True, env=env
        )
        self._git("remote", "add", "origin", str(origin))
        self._git("fetch", "-q", "origin")
        self._git("branch", "-q", "--set-upstream-to=origin/main", "main")
        # The stand-in python: build.py changes nothing; push.py --live records a post
        # (as the real one does after Buffer accepts it) and then exits 1 for an alert.
        self.fake_py = tmp / "fakepy"
        self.fake_py.write_text(
            "#!/usr/bin/env bash\n"
            'case "$1" in\n'
            "  build.py) exit 0 ;;\n"
            '  push.py) echo \'{"posts": {"x": {"linkedin": {"post_id": "p1"}}}}\' '
            "> state/pushed.json; exit 1 ;;\n"
            "esac\n"
        )
        self.fake_py.chmod(self.fake_py.stat().st_mode | stat.S_IXUSR)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=self.repo, check=True, capture_output=True, text=True, env=self.env
        ).stdout

    def test_state_is_committed_and_pushed_even_when_push_py_reports_alerts(self) -> None:
        # push.py exits 1 whenever the run had an alert (a disconnected page is a
        # persistent one). Buffer has the posts by then, so state/pushed.json must still
        # be committed and pushed, or the next Sunday has no record of them.
        result = subprocess.run(
            ["bash", "deploy/run.sh"],
            cwd=self.repo,
            capture_output=True,
            text=True,
            env={**self.env, "AIREP_SOCIAL_PYTHON": str(self.fake_py)},
        )
        self.assertNotEqual(result.returncode, 0, "the alert must still fail the unit")
        self.assertIn("chore(state)", self._git("log", "-1", "--format=%s"))
        self.assertIn("chore(state)", self._git("log", "-1", "--format=%s", "origin/main"))
        self.assertEqual(self._git("status", "--porcelain"), "")


if __name__ == "__main__":
    unittest.main()
