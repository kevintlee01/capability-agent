"""The mock operator surface: deliberately bare, per the assignment's scope
note (a full co-browsing console is out of scope). Real part: it reads/writes
the same control files the live run is blocking on, so resuming here truly
hands control back to the same session -- not a new one.
"""
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
