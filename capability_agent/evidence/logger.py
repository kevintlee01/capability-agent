"""Append-only, redacted evidence log for a single discovery or replay run."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from capability_agent.guardrails.redact import redact_dict


class RunLogger:
    def __init__(self, run_id: str, run_type: str, base_dir: Path = Path("evidence")):
        self.run_id = run_id
        self.run_dir = base_dir / run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.run_dir / "log.jsonl"
        self.event("run_started", {"run_type": run_type, "run_id": run_id})

    def event(self, event_type: str, detail: dict) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "detail": redact_dict(detail),
        }
        with self.log_path.open("a") as fh:
            fh.write(json.dumps(entry) + "\n")

    def screenshot_path(self, name: str) -> Path:
        path = self.run_dir / "screenshots" / f"{name}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def write_summary(self, summary: dict) -> None:
        (self.run_dir / "summary.json").write_text(json.dumps(redact_dict(summary), indent=2))
