"""Dashboard write-path actions, mocked at the agent/engine/allowlist boundary."""
from unittest.mock import MagicMock, patch

from dashboard.actions import trigger_discover, trigger_replay


def test_trigger_discover_saves_artifact_on_completion():
    fake_result = MagicMock(status="completed", artifact=MagicMock(), run_id="discover-abc123")
    with patch("dashboard.actions.AllowlistPolicy.load"), \
         patch("dashboard.actions.build_llm_client"), \
         patch("dashboard.actions.DiscoveryAgent") as mock_agent_cls, \
         patch("dashboard.actions.save_artifact") as mock_save:
        mock_agent_cls.return_value.run.return_value = fake_result
        run_id = trigger_discover("demo", "look up member 1", {"member_id": "1"})

        assert run_id == "discover-abc123"
        mock_save.assert_called_once()


def test_trigger_discover_skips_save_when_not_completed():
    fake_result = MagicMock(status="failed", artifact=None, run_id="discover-xyz")
    with patch("dashboard.actions.AllowlistPolicy.load"), \
         patch("dashboard.actions.build_llm_client"), \
         patch("dashboard.actions.DiscoveryAgent") as mock_agent_cls, \
         patch("dashboard.actions.save_artifact") as mock_save:
        mock_agent_cls.return_value.run.return_value = fake_result
        run_id = trigger_discover("demo", "goal", {})

        assert run_id == "discover-xyz"
        mock_save.assert_not_called()


def test_trigger_replay_generates_run_id_and_forwards_params():
    fake_artifact = MagicMock()
    with patch("dashboard.actions.AllowlistPolicy.load"), \
         patch("dashboard.actions.load_artifact", return_value=fake_artifact), \
         patch("dashboard.actions.replay_artifact") as mock_replay:
        run_id = trigger_replay("lookup_balance", "1.0.0", {"member_id": "10001"}, allow_risky=True)

        assert run_id.startswith("replay-")
        _, kwargs = mock_replay.call_args
        assert kwargs["artifact"] is fake_artifact
        assert kwargs["input_params"] == {"member_id": "10001"}
        assert kwargs["allow_risky"] is True
        assert kwargs["run_id"] == run_id
