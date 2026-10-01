"""Read-only helpers: turn artifacts/ and evidence/ on disk into view models.

Deliberately has zero write paths except the one escalation resume action --
this is a viewer plus a single, real, already-existing control-transfer call,
not a new surface for arbitrary mutation.
"""
from __future__ import annotations

import json
from pathlib import Path

ARTIFACT_DIR = Path("artifacts")
EVIDENCE_DIR = Path("evidence")


def list_artifact_summaries() -> list[dict]:
    summaries = []
    if not ARTIFACT_DIR.exists():
        return summaries
    for name_dir in sorted(ARTIFACT_DIR.iterdir()):
        if not name_dir.is_dir():
            continue
        for version_file in sorted(name_dir.glob("*.json")):
            data = json.loads(version_file.read_text())
            summaries.append({
                "name": data["name"],
                "version": data["version"],
                "description": data["description"],
                "status": data["status"],
                "created_by": data["created_by"],
                "surface_type": data["surface_type"],
                "param_count": len(data.get("params", [])),
                "output_count": len(data.get("outputs", [])),
                "step_count": len(data.get("steps", [])),
                "outcome_count": len(data.get("known_outcomes", [])),
            })
    return summaries


def get_artifact(name: str, version: str) -> dict | None:
    path = ARTIFACT_DIR / name / f"{version}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    events = []
    for line in path.read_text().splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


def list_run_summaries() -> list[dict]:
    summaries = []
    if not EVIDENCE_DIR.exists():
        return summaries
    for run_dir in sorted(EVIDENCE_DIR.iterdir(), reverse=True):
        if not run_dir.is_dir():
            continue
        events = _read_jsonl(run_dir / "log.jsonl")
        if not events:
            continue
        first = events[0]
        summary_path = run_dir / "summary.json"
        summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
        pending = (run_dir / "intervention.json").exists() and not (run_dir / "resume.signal").exists()
        summaries.append({
            "run_id": run_dir.name,
            "run_type": first.get("detail", {}).get("run_type", "unknown"),
            "started_at": first.get("ts"),
            "event_count": len(events),
            "status": summary.get("status", "pending" if pending else "in_progress"),
            "pending_escalation": pending,
        })
    return summaries


def get_run_detail(run_id: str) -> dict | None:
    run_dir = EVIDENCE_DIR / run_id
    if not run_dir.exists():
        return None
    summary_path = run_dir / "summary.json"
    intervention_path = run_dir / "intervention.json"
    resumed = (run_dir / "resume.signal").exists()
    screenshots_dir = run_dir / "screenshots"
    return {
        "run_id": run_id,
        "events": _read_jsonl(run_dir / "log.jsonl"),
        "summary": json.loads(summary_path.read_text()) if summary_path.exists() else None,
        "intervention": json.loads(intervention_path.read_text()) if intervention_path.exists() and not resumed else None,
        "resume_note": json.loads((run_dir / "resume.signal").read_text()) if resumed else None,
        "screenshots": sorted(p.name for p in screenshots_dir.glob("*.png")) if screenshots_dir.exists() else [],
    }


def outcome_distribution() -> dict[str, int]:
    counts = {"success": 0, "business_outcome": 0, "failure": 0, "other": 0}
    for run in list_run_summaries():
        key = run["status"] if run["status"] in counts else "other"
        counts[key] += 1
    return counts
