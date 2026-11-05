"""state/pushed.json round-trips and stays sorted."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import state


class StateTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state" / "pushed.json"
            self.assertEqual(state.load_state(path), {})
            data: dict = {}
            state.record(data, "2026-11-18-x", "linkedin", "p1", "2026-11-17T21:30:00Z", "t1")
            state.record(data, "2026-11-17-y", "facebook", "p2", "2026-11-17T08:30:00Z", "t2")
            state.save_state(data, path)
            back = state.load_state(path)
            self.assertEqual(back, data)
            self.assertEqual(back["2026-11-18-x"]["linkedin"]["post_id"], "p1")
            raw = json.loads(path.read_text())
            self.assertEqual(list(raw["posts"]), ["2026-11-17-y", "2026-11-18-x"])  # sorted


if __name__ == "__main__":
    unittest.main()
