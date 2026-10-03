"""Dashboard data helpers and FastAPI routes, using isolated temp artifact/evidence directories."""
import json

import dashboard.data as data_module
from dashboard.main import app
from fastapi.testclient import TestClient

from capability_agent.artifact.schema import (
    ActionType, CapabilityArtifact, Checkpoint, Locator, LocatorKind, LocatorStrategy, Param, Step, SurfaceType,
)

client = TestClient(app)


def _write_artifact(tmp_path, name="demo_cap", status="draft"):
    artifact_dir = tmp_path / name
    artifact_dir.mkdir(parents=True)
    locator = Locator(primary=LocatorStrategy(kind=LocatorKind.ROLE, value="Search", role="button"))
    artifact = CapabilityArtifact(
        artifact_id=f"{name}-1", name=name, description="demo", target_app="mock",
        surface_type=SurfaceType.LEGACY_WEB, base_url="http://127.0.0.1:8731", status=status,
        params=[Param(name="member_id", type="string", description="id")],
        steps=[Step(step_id=1, action=ActionType.CLICK, description="click", locator=locator)],
        checkpoint=Checkpoint(locator=locator, description="done"),
    )
    payload = json.loads(artifact.model_dump_json())
    (artifact_dir / "1.0.0.json").write_text(json.dumps(payload))
    return payload


def _write_run(tmp_path, run_id, status="success", pending=False, with_screenshot=False, with_summary=True):
    run_dir = tmp_path / run_id
    (run_dir / "screenshots").mkdir(parents=True) if with_screenshot else run_dir.mkdir(parents=True)
    events = [{"ts": "t0", "type": "run_started", "detail": {"run_type": "replay"}}]
    (run_dir / "log.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")
    if with_summary:
        (run_dir / "summary.json").write_text(json.dumps({"status": status}))
    if pending:
        (run_dir / "intervention.json").write_text(json.dumps({"goal": "g", "reason": "stuck", "step_id": 1}))
    if with_screenshot:
        (run_dir / "screenshots" / "shot.png").write_bytes(b"\x89PNG")
    return run_dir


def test_list_artifact_summaries_empty_when_dir_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(data_module, "ARTIFACT_DIR", tmp_path / "nope")
    assert data_module.list_artifact_summaries() == []


def test_list_artifact_summaries_reads_real_files(tmp_path, monkeypatch):
    monkeypatch.setattr(data_module, "ARTIFACT_DIR", tmp_path)
    _write_artifact(tmp_path)
    (tmp_path / "stray.txt").write_text("not a capability dir")
    summaries = data_module.list_artifact_summaries()
    assert len(summaries) == 1
    assert summaries[0]["name"] == "demo_cap"
    assert summaries[0]["param_count"] == 1


def test_get_artifact_returns_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(data_module, "ARTIFACT_DIR", tmp_path)
    assert data_module.get_artifact("nope", "1.0.0") is None


def test_get_artifact_returns_parsed_json(tmp_path, monkeypatch):
    monkeypatch.setattr(data_module, "ARTIFACT_DIR", tmp_path)
    _write_artifact(tmp_path)
    artifact = data_module.get_artifact("demo_cap", "1.0.0")
    assert artifact["name"] == "demo_cap"


def test_list_run_summaries_skips_dirs_without_events(tmp_path, monkeypatch):
    monkeypatch.setattr(data_module, "EVIDENCE_DIR", tmp_path)
    (tmp_path / "empty-run").mkdir()
    (tmp_path / "stray.txt").write_text("not a run dir")
    assert data_module.list_run_summaries() == []


def test_list_run_summaries_reports_pending_escalation(tmp_path, monkeypatch):
    monkeypatch.setattr(data_module, "EVIDENCE_DIR", tmp_path)
    _write_run(tmp_path, "run-1", pending=True, with_summary=False)
    summaries = data_module.list_run_summaries()
    assert summaries[0]["pending_escalation"] is True
    assert summaries[0]["status"] == "pending"


def test_get_run_detail_returns_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(data_module, "EVIDENCE_DIR", tmp_path)
    assert data_module.get_run_detail("nope") is None


def test_get_run_detail_includes_intervention_until_resumed(tmp_path, monkeypatch):
    monkeypatch.setattr(data_module, "EVIDENCE_DIR", tmp_path)
    _write_run(tmp_path, "run-2", pending=True)
    detail = data_module.get_run_detail("run-2")
    assert detail["intervention"]["reason"] == "stuck"
    assert detail["resume_note"] is None


def test_get_run_detail_shows_resume_note_once_resumed(tmp_path, monkeypatch):
    monkeypatch.setattr(data_module, "EVIDENCE_DIR", tmp_path)
    run_dir = _write_run(tmp_path, "run-3", pending=True)
    (run_dir / "resume.signal").write_text(json.dumps({"note": "fixed it"}))
    detail = data_module.get_run_detail("run-3")
    assert detail["intervention"] is None
    assert detail["resume_note"]["note"] == "fixed it"


def test_get_run_detail_lists_screenshots(tmp_path, monkeypatch):
    monkeypatch.setattr(data_module, "EVIDENCE_DIR", tmp_path)
    _write_run(tmp_path, "run-4", with_screenshot=True)
    detail = data_module.get_run_detail("run-4")
    assert detail["screenshots"] == ["shot.png"]


def test_outcome_distribution_counts_by_status(tmp_path, monkeypatch):
    monkeypatch.setattr(data_module, "EVIDENCE_DIR", tmp_path)
    _write_run(tmp_path, "run-5", status="success")
    _write_run(tmp_path, "run-6", status="failure")
    counts = data_module.outcome_distribution()
    assert counts["success"] == 1
    assert counts["failure"] == 1


def test_index_route_renders_with_no_data(tmp_path, monkeypatch):
    monkeypatch.setattr(data_module, "ARTIFACT_DIR", tmp_path / "artifacts")
    monkeypatch.setattr(data_module, "EVIDENCE_DIR", tmp_path / "evidence")
    import dashboard.main as main_module
    monkeypatch.setattr(main_module, "list_artifact_summaries", data_module.list_artifact_summaries)
    monkeypatch.setattr(main_module, "list_run_summaries", data_module.list_run_summaries)
    monkeypatch.setattr(main_module, "outcome_distribution", data_module.outcome_distribution)
    response = client.get("/")
    assert response.status_code == 200


def test_artifact_detail_route_found_and_not_found(tmp_path, monkeypatch):
    monkeypatch.setattr(data_module, "ARTIFACT_DIR", tmp_path)
    _write_artifact(tmp_path)
    import dashboard.main as main_module
    monkeypatch.setattr(main_module, "get_artifact", data_module.get_artifact)
    found = client.get("/artifacts/demo_cap/1.0.0")
    assert found.status_code == 200
    missing = client.get("/artifacts/nope/1.0.0")
    assert missing.status_code == 200


def test_run_detail_route_found_and_not_found(tmp_path, monkeypatch):
    monkeypatch.setattr(data_module, "EVIDENCE_DIR", tmp_path)
    _write_run(tmp_path, "run-7")
    import dashboard.main as main_module
    monkeypatch.setattr(main_module, "get_run_detail", data_module.get_run_detail)
    found = client.get("/runs/run-7")
    assert found.status_code == 200
    missing = client.get("/runs/nope")
    assert missing.status_code == 200


def test_resume_run_route_writes_signal_and_redirects(tmp_path, monkeypatch):
    monkeypatch.setattr(data_module, "EVIDENCE_DIR", tmp_path)
    import dashboard.main as main_module
    monkeypatch.setattr(main_module, "EVIDENCE_DIR", tmp_path)
    _write_run(tmp_path, "run-8", pending=True)
    response = client.post("/runs/run-8/resume", data={"note": "handled"}, follow_redirects=False)
    assert response.status_code == 303
    assert (tmp_path / "run-8" / "resume.signal").exists()


def test_discover_form_route_renders():
    response = client.get("/discover")
    assert response.status_code == 200


def test_discover_submit_route_forwards_params_and_redirects(monkeypatch):
    import dashboard.main as main_module
    captured = {}

    def fake_trigger_discover(name, goal, params):
        captured["args"] = (name, goal, params)
        return "discover-abc"

    monkeypatch.setattr(main_module, "trigger_discover", fake_trigger_discover)
    response = client.post(
        "/discover",
        data={"name": "demo_cap", "goal": "look up a member", "param__member_id": "10001"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/runs/discover-abc"
    assert captured["args"] == ("demo_cap", "look up a member", {"member_id": "10001"})


def test_replay_submit_route_forwards_params_and_allow_risky(monkeypatch):
    import dashboard.main as main_module
    captured = {}

    def fake_trigger_replay(name, version, params, allow_risky):
        captured["args"] = (name, version, params, allow_risky)
        return "replay-xyz"

    monkeypatch.setattr(main_module, "trigger_replay", fake_trigger_replay)
    response = client.post(
        "/artifacts/lookup_balance/1.0.0/replay",
        data={"param__member_id": "10001", "allow_risky": "on"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/runs/replay-xyz"
    assert captured["args"] == ("lookup_balance", "1.0.0", {"member_id": "10001"}, True)


def test_replay_submit_route_defaults_allow_risky_false_when_unchecked(monkeypatch):
    import dashboard.main as main_module
    captured = {}

    def fake_trigger_replay(name, version, params, allow_risky):
        captured["allow_risky"] = allow_risky
        return "replay-xyz"

    monkeypatch.setattr(main_module, "trigger_replay", fake_trigger_replay)
    client.post("/artifacts/lookup_balance/1.0.0/replay", data={"param__member_id": "10001"}, follow_redirects=False)
    assert captured["allow_risky"] is False
