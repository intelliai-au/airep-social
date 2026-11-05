"""state/pushed.json: every Buffer post push.py has created, keyed by post slug and channel."""

from __future__ import annotations

import json
from pathlib import Path

STATE_PATH = Path(__file__).resolve().parent / "state" / "pushed.json"


def load_state(path: Path = STATE_PATH) -> dict[str, dict[str, dict[str, str]]]:
    """The mapping slug -> channel -> {post_id, due_at, pushed_at}; empty when absent."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("posts", {})


def save_state(state: dict[str, dict[str, dict[str, str]]], path: Path = STATE_PATH) -> None:
    """Write the state sorted and indented so the timer's commits diff cleanly."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"posts": {slug: dict(sorted(chs.items())) for slug, chs in sorted(state.items())}}
    path.write_text(json.dumps(body, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def record(
    state: dict[str, dict[str, dict[str, str]]],
    slug: str,
    channel: str,
    post_id: str,
    due_at: str,
    pushed_at: str,
) -> None:
    """Mark one channel of one post as pushed (mutates *state*)."""
    state.setdefault(slug, {})[channel] = {
        "post_id": post_id,
        "due_at": due_at,
        "pushed_at": pushed_at,
    }
