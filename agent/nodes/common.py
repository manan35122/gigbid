import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def cfg() -> dict:
    return yaml.safe_load((ROOT / "agent" / "config.yaml").read_text(encoding="utf-8"))


def step(node: str, **summary) -> dict:
    """One trace entry (audit/debug record, kept apart from state and memory)."""
    return {"trace": [dict(node=node, ts=time.time(), **summary)], "steps": 1}