"""CLI command wiring: argument parsing, exit codes, and correct delegation -- heavy lifting (discovery/replay) is mocked here since it's already tested exhaustively elsewhere."""
import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from capability_agent.cli import app
from capability_agent.discovery.agent_loop import DiscoveryResult
from capability_agent.replay.outcomes import BusinessOutcomeDetail, FailureDetail, ReplayOutcome
from capability_agent.escalation import operator_cli

runner = CliRunner()


def test_list_cmd_prints_saved_artifacts(tmp_path, monkeypatch):
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "1.0.0.json").write_text("{}")
    monkeypatch.setattr("capability_agent.cli.settings.artifact_dir", str(tmp_path))
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "demo @ 1.0.0" in result.stdout


def test_replay_cmd_success_exits_zero(tmp_path, monkeypatch):
    monkeypatch.setattr("capability_agent.cli.settings.allowlist_path", "config/allowlist.yml")
    fake_artifact = MagicMock()
    with patch("capability_agent.cli.load_artifact", return_value=fake_artifact), \
         patch("capability_agent.cli.replay_artifact", return_value=ReplayOutcome(result_type="success", outputs={"x": "y"})):
        result = runner.invoke(app, ["replay", "--name", "demo"])
    assert result.exit_code == 0
    assert '"result_type": "success"' in result.stdout


def test_replay_cmd_failure_exits_nonzero(tmp_path, monkeypatch):
    monkeypatch.setattr("capability_agent.cli.settings.allowlist_path", "config/allowlist.yml")
    fake_artifact = MagicMock()
    failure_outcome = ReplayOutcome(
        result_type="failure",
        failure=FailureDetail(step_id=1, expected="x", observed="y", message="boom"),
    )
    with patch("capability_agent.cli.load_artifact", return_value=fake_artifact), \
         patch("capability_agent.cli.replay_artifact", return_value=failure_outcome):
        result = runner.invoke(app, ["replay", "--name", "demo"])
    assert result.exit_code == 1


def test_replay_cmd_business_outcome_exits_zero(monkeypatch):
    monkeypatch.setattr("capability_agent.cli.settings.allowlist_path", "config/allowlist.yml")
    fake_artifact = MagicMock()
    outcome = ReplayOutcome(result_type="business_outcome", business_outcome=BusinessOutcomeDetail(name="not_found", description="d"))
    with patch("capability_agent.cli.load_artifact", return_value=fake_artifact), \
         patch("capability_agent.cli.replay_artifact", return_value=outcome):
        result = runner.invoke(app, ["replay", "--name", "demo"])
    assert result.exit_code == 0


def test_discover_cmd_success_saves_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr("capability_agent.cli.settings.allowlist_path", "config/allowlist.yml")
    monkeypatch.setattr("capability_agent.cli.settings.artifact_dir", str(tmp_path))
    fake_artifact = MagicMock()
    fake_artifact.name = "demo"
    fake_artifact.version = "1.0.0"
    fake_artifact.model_dump_json.return_value = "{}"
    fake_result = DiscoveryResult(status="completed", run_id="discover-1", artifact=fake_artifact)
    with patch("capability_agent.cli.build_llm_client", return_value=MagicMock()), \
         patch("capability_agent.cli.DiscoveryAgent") as mock_agent_cls:
        mock_agent_cls.return_value.run.return_value = fake_result
        result = runner.invoke(app, ["discover", "--name", "demo", "--goal", "do a thing"])
    assert result.exit_code == 0
    assert "completed" in result.stdout


def test_discover_cmd_failure_exits_nonzero(monkeypatch):
    monkeypatch.setattr("capability_agent.cli.settings.allowlist_path", "config/allowlist.yml")
    fake_result = DiscoveryResult(status="failed", run_id="discover-2", failure_reason="could not find it")
    with patch("capability_agent.cli.build_llm_client", return_value=MagicMock()), \
         patch("capability_agent.cli.DiscoveryAgent") as mock_agent_cls:
        mock_agent_cls.return_value.run.return_value = fake_result
        result = runner.invoke(app, ["discover", "--name", "demo", "--goal", "do a thing"])
    assert result.exit_code == 1
    assert "could not find it" in result.stdout


def test_operator_status_reports_no_pending_intervention(tmp_path, monkeypatch):
    monkeypatch.setattr("capability_agent.cli.settings.evidence_dir", str(tmp_path))
    result = runner.invoke(app, ["operator", "status", "run-1"])
    assert result.exit_code == 0
    assert "No pending intervention" in result.stdout


def test_operator_status_shows_pending_context(tmp_path, monkeypatch):
    monkeypatch.setattr("capability_agent.cli.settings.evidence_dir", str(tmp_path))
    run_dir = tmp_path / "run-2"
    run_dir.mkdir()
    (run_dir / "intervention.json").write_text(json.dumps({
        "goal": "look up member", "step_id": 3, "reason": "stuck", "current_url": "http://x/y", "screenshot_path": "shot.png",
    }))
    result = runner.invoke(app, ["operator", "status", "run-2"])
    assert result.exit_code == 0
    assert "look up member" in result.stdout
    assert "stuck" in result.stdout


def test_operator_resume_writes_signal(tmp_path, monkeypatch):
    monkeypatch.setattr("capability_agent.cli.settings.evidence_dir", str(tmp_path))
    (tmp_path / "run-3").mkdir()
    result = runner.invoke(app, ["operator", "resume", "run-3", "--note", "fixed it"])
    assert result.exit_code == 0
    assert operator_cli.show_status(tmp_path / "run-3") is None
    assert json.loads((tmp_path / "run-3" / "resume.signal").read_text())["note"] == "fixed it"
