"""Cross-browser smoke test: the same deterministic replay flows must behave identically on Chromium, Firefox, and WebKit."""
from pathlib import Path

import pytest

from capability_agent.artifact.store import load_artifact
from capability_agent.guardrails.allowlist import AllowlistPolicy
from capability_agent.replay.engine import replay_artifact


def _retargeted(name, live_mock_app_url):
    artifact = load_artifact(name, "1.0.0", base_dir=Path("artifacts"))
    return artifact.model_copy(update={"base_url": live_mock_app_url})


def _allowlist():
    return AllowlistPolicy(
        allowed_domains=["127.0.0.1:*"], allowed_route_prefixes=["/"],
        allowed_actions=["navigate", "click", "fill", "select_option", "wait_for", "extract", "assert_checkpoint"],
    )


@pytest.mark.cross_browser
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_lookup_balance_succeeds_on_every_browser_engine(engine, live_mock_app_url, tmp_path):
    artifact = _retargeted("lookup_balance", live_mock_app_url)
    outcome = replay_artifact(
        artifact, {"member_id": "10001"}, _allowlist(), headless=True, evidence_base=str(tmp_path), engine=engine,
    )
    assert outcome.result_type == "success"
    assert outcome.outputs["balance"] == "$4820.55"


@pytest.mark.cross_browser
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_fraud_hold_interstitial_recovers_on_every_browser_engine(engine, live_mock_app_url, tmp_path):
    artifact = _retargeted("open_sub_account", live_mock_app_url)
    params = {"member_id": "60000", "account_type": "Savings", "nickname": "Rainy Day", "initial_deposit": "50"}
    outcome = replay_artifact(
        artifact, params, _allowlist(), headless=True, allow_risky=True, evidence_base=str(tmp_path), engine=engine,
    )
    assert outcome.result_type == "success"
    assert any("fraud_review_hold" in r for r in outcome.recovered_conditions)
