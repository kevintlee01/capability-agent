"""Deliberately bare mock operator surface: reads/writes the same control files the live run is blocking on, so resuming hands back the same session."""
import json
from pathlib import Path


def show_status(run_dir: Path) -> dict | None:
    intervention_path = run_dir / "intervention.json"
    if not intervention_path.exists():
        return None
    return json.loads(intervention_path.read_text())


def resume(run_dir: Path, note: str) -> None:
    resume_path = run_dir / "resume.signal"
    resume_path.write_text(json.dumps({"note": note}))
