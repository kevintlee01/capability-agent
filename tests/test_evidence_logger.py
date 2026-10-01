"""RunLogger: event redaction, screenshot paths, and summary writing."""
import json

from capability_agent.evidence.logger import RunLogger


def test_run_logger_writes_run_started_event_on_init(tmp_path):
    logger = RunLogger("r1", "discovery", base_dir=tmp_path)
    lines = (tmp_path / "r1" / "log.jsonl").read_text().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["type"] == "run_started"
    assert entry["detail"]["run_type"] == "discovery"


def test_run_logger_redacts_sensitive_fields_before_writing(tmp_path):
    logger = RunLogger("r2", "replay", base_dir=tmp_path)
    logger.event("action_executed", {"password": "hunter2", "note": "fine"})
    lines = (tmp_path / "r2" / "log.jsonl").read_text().splitlines()
    last = json.loads(lines[-1])
    assert last["detail"]["password"] == "[REDACTED]"
    assert last["detail"]["note"] == "fine"


def test_screenshot_path_creates_screenshots_subdirectory(tmp_path):
    logger = RunLogger("r3", "replay", base_dir=tmp_path)
    path = logger.screenshot_path("failure-step1")
    assert path.parent.name == "screenshots"
    assert path.parent.exists()
    assert path.name == "failure-step1.png"


def test_write_summary_redacts_and_persists_json(tmp_path):
    logger = RunLogger("r4", "replay", base_dir=tmp_path)
    logger.write_summary({"status": "success", "token": "secret-abc"})
    summary = json.loads((tmp_path / "r4" / "summary.json").read_text())
    assert summary["status"] == "success"
    assert summary["token"] == "[REDACTED]"
