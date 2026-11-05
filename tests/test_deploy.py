"""The systemd units and run.sh behave as the README promises: paths with a space survive
systemd's parsing, and run.sh is what ExecStart points at."""

from __future__ import annotations

import shlex
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


if __name__ == "__main__":
    unittest.main()
