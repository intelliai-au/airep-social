"""The systemd units and run.sh behave as the README promises: paths with a space survive
systemd's parsing, and a push run that ends with alerts still commits state/pushed.json."""

from __future__ import annotations

import fcntl
import os
import re
import shlex
import stat
import subprocess
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = ROOT / "deploy"
# The units hard-code the canonical checkout (systemd wants absolute paths), while the
# tests may run from an author.py worktree under ~/.local/state, so the expected path is
# never derived from the test file's own location (that failed the first December run).
CANONICAL = Path.home() / "Documents" / "Github Projects" / "airep-social"
UNITS = (
    "airep-social.service",
    "airep-social.timer",
    "airep-social-author@.service",
    "airep-social-author@write.timer",
    "airep-social-author@film.timer",
)


class UnitFileTests(unittest.TestCase):
    def test_environment_assignments_survive_systemd_word_splitting(self) -> None:
        # systemd unquotes Environment= lines and splits them on whitespace into
        # KEY=VALUE words, so an unquoted path with a space becomes two assignments and
        # the second half is dropped ("Invalid environment assignment, ignoring").
        # The repo path has a space ("Github Projects"), so every value must be quoted.
        for unit in UNITS:
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
        self.assertIn(f"WorkingDirectory={CANONICAL}\n", text)
        self.assertIn(f'ExecStart=/usr/bin/env bash "{CANONICAL / "deploy" / "run.sh"}"\n', text)

    def test_author_units_run_author_py_from_the_repo_with_a_phase(self) -> None:
        text = (DEPLOY / "airep-social-author@.service").read_text(encoding="utf-8")
        self.assertIn(f"WorkingDirectory={CANONICAL}\n", text)
        self.assertIn(f'"{CANONICAL / "author.py"}" %i\n', text)
        # Never beside the push, but by a shared lock (run.sh and author.py), not
        # Conflicts=, which kills whichever unit was already running.
        self.assertNotRegex(text, r"(?m)^Conflicts=")
        for phase in ("write", "film"):
            timer = (DEPLOY / f"airep-social-author@{phase}.timer").read_text(encoding="utf-8")
            self.assertIn(f"Unit=airep-social-author@{phase}.service\n", timer)
            self.assertIn("02:00:00\n", timer)

    def test_the_push_can_outwait_an_author_run(self) -> None:
        # run.sh waits for the lock an author run holds (up to its own 3h timeout), so
        # the push's start timeout must cover that wait plus its own work.
        def timeout(unit: str) -> timedelta:
            text = (DEPLOY / unit).read_text(encoding="utf-8")
            match = re.search(r"^TimeoutStartSec=(.+)$", text, re.M)
            assert match, unit
            units = {"h": "hours", "min": "minutes", "s": "seconds"}
            parts = re.findall(r"(\d+)(h|min|s)", match.group(1))
            return timedelta(**{units[u]: int(n) for n, u in parts})

        author = timeout("airep-social-author@.service")
        push = timeout("airep-social.service")
        self.assertGreaterEqual(push - author, timedelta(minutes=20))


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
        # The stand-in python logs each call. build.py changes nothing and exits
        # $FAKE_BUILD_STATUS; push.py --live records a post (as the real one does after
        # Buffer accepts it) and then exits 1 for an alert.
        self.calls = tmp / "calls.log"
        self.fake_py = tmp / "fakepy"
        self.fake_py.write_text(
            "#!/usr/bin/env bash\n"
            'echo "$*" >> "$FAKE_LOG"\n'
            'case "$1" in\n'
            '  build.py) exit "${FAKE_BUILD_STATUS:-0}" ;;\n'
            '  push.py) echo \'{"posts": {"x": {"linkedin": {"post_id": "p1"}}}}\' '
            "> state/pushed.json\n"
            # $FAKE_RACE: another clone pushes to origin while the push is running.
            '    if [ -n "${FAKE_RACE:-}" ]; then\n'
            '      git -C "$FAKE_RACE" commit -q --allow-empty -m race\n'
            '      git -C "$FAKE_RACE" push -q origin main\n'
            "    fi\n"
            "    exit 1 ;;\n"
            "esac\n"
        )
        self.fake_py.chmod(self.fake_py.stat().st_mode | stat.S_IXUSR)
        # A lock of the test's own: the default is the one author.py holds, and an
        # author run's session runs this suite, so sharing it would wait on itself.
        self.lock = tmp / "run.lock"
        self.run_env = {
            **env,
            "AIREP_SOCIAL_PYTHON": str(self.fake_py),
            "AIREP_SOCIAL_LOCK": str(self.lock),
            "FAKE_LOG": str(self.calls),
        }

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
        result = self._run_sh()
        self.assertNotEqual(result.returncode, 0, "the alert must still fail the unit")
        self.assertIn("chore(state)", self._git("log", "-1", "--format=%s"))
        self.assertIn("chore(state)", self._git("log", "-1", "--format=%s", "origin/main"))
        self.assertEqual(self._git("status", "--porcelain"), "")

    def test_a_build_failure_still_schedules_the_fortnight(self) -> None:
        # build.py renders every post, so a film missing weeks ahead fails it. The
        # fortnight's posts may still be fine (push.py HEAD-checks each one and skips
        # and alerts on a missing image), so the push must run; the unit still fails.
        result = self._run_sh(FAKE_BUILD_STATUS="1")
        self.assertNotEqual(result.returncode, 0, "the build failure must still fail the unit")
        self.assertEqual(self._calls(), ["build.py", "push.py --live"])
        self.assertIn("chore(state)", self._git("log", "-1", "--format=%s", "origin/main"))

    def test_a_push_that_lands_meanwhile_is_merged_not_left_diverged(self) -> None:
        # The swarm lane or a session can push to main while push.py runs. The rejected
        # state push left a local commit that diverged main from origin, so every later
        # Sunday stopped at `git pull --ff-only` with nothing scheduled and nobody told.
        other = Path(self._tmp.name) / "other"
        subprocess.run(
            ["git", "clone", "-q", self._git("remote", "get-url", "origin").strip(), str(other)],
            check=True,
            env=self.env,
        )
        result = self._run_sh(FAKE_RACE=str(other))
        self.assertNotEqual(result.returncode, 0, "push.py's alert still fails the unit")
        on_origin = self._git("log", "--format=%s", "origin/main")
        self.assertIn("chore(state)", on_origin)
        self.assertIn("race", on_origin)
        self.assertEqual(self._git("rev-parse", "HEAD"), self._git("rev-parse", "origin/main"))
        self.assertEqual(self._git("status", "--porcelain"), "")

    def test_waits_while_an_author_run_holds_the_lock(self) -> None:
        # The author units used Conflicts=airep-social.service, which in systemd's
        # default replace mode SIGTERMs a running push (state/pushed.json uncommitted,
        # Buffer already holding the posts). Now both take one lock instead.
        with self.lock.open("a") as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            proc = subprocess.Popen(
                ["bash", "deploy/run.sh"],
                cwd=self.repo,
                env=self.run_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                with self.assertRaises(subprocess.TimeoutExpired):
                    proc.wait(timeout=1.5)
                self.assertEqual(self._calls(), [], "ran while the lock was held")
            finally:
                fcntl.flock(held, fcntl.LOCK_UN)
        self.assertNotEqual(proc.wait(timeout=60), 0)
        self.assertEqual(self._calls(), ["build.py", "push.py --live"])

    def _run_sh(self, **extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", "deploy/run.sh"],
            cwd=self.repo,
            capture_output=True,
            text=True,
            env={**self.run_env, **extra},
            timeout=60,
        )

    def _calls(self) -> list[str]:
        if not self.calls.exists():
            return []
        return self.calls.read_text().splitlines()


if __name__ == "__main__":
    unittest.main()
