"""Full replay_artifact() runs against a REAL browser + the REAL mock app, using the actual committed hand-authored artifacts retargeted to the test server's random port."""
from pathlib import Path

import pytest

from capability_agent.artifact.store import load_artifact
from capability_agent.guardrails.allowlist import AllowlistPolicy, GuardrailViolation
from capability_agent.replay.engine import replay_artifact


def _retargeted(name, live_mock_app_url):
    artifact = load_artifact(name, "1.0.0", base_dir=Path("artifacts"))
    return artifact.model_copy(update={"base_url": live_mock_app_url})


def _allowlist():
    return AllowlistPolicy(
        allowed_domains=["127.0.0.1:*"], allowed_route_prefixes=["/"],
        allowed_actions=["navigate", "click", "fill", "select_option", "wait_for", "extract", "assert_checkpoint"],
    )


def test_lookup_balance_success_returns_output(live_mock_app_url, tmp_path):
    artifact = _retargeted("lookup_balance", live_mock_app_url)
    outcome = replay_artifact(artifact, {"member_id": "10001"}, _allowlist(), headless=True, evidence_base=str(tmp_path))
    assert outcome.result_type == "success"
    assert outcome.outputs["balance"] == "$4820.55"


def test_lookup_balance_member_not_found_is_a_business_outcome(live_mock_app_url, tmp_path):
    artifact = _retargeted("lookup_balance", live_mock_app_url)
    outcome = replay_artifact(artifact, {"member_id": "00000"}, _allowlist(), headless=True, evidence_base=str(tmp_path))
    assert outcome.result_type == "business_outcome"
    assert outcome.business_outcome.name == "member_not_found"


def test_lookup_balance_permission_denied_is_a_business_outcome(live_mock_app_url, tmp_path):
    artifact = _retargeted("lookup_balance", live_mock_app_url)
    outcome = replay_artifact(artifact, {"member_id": "40300"}, _allowlist(), headless=True, evidence_base=str(tmp_path))
    assert outcome.result_type == "business_outcome"
    assert outcome.business_outcome.name == "permission_denied"


def test_lookup_balance_session_expired_is_a_business_outcome(live_mock_app_url, tmp_path):
    artifact = _retargeted("lookup_balance", live_mock_app_url)
    outcome = replay_artifact(artifact, {"member_id": "90000"}, _allowlist(), headless=True, evidence_base=str(tmp_path))
    assert outcome.result_type == "business_outcome"
    assert outcome.business_outcome.name == "session_expired"


def _sub_account_params(**overrides):
    base = {"member_id": "20002", "account_type": "Savings", "nickname": "Rainy Day", "initial_deposit": "50"}
    base.update(overrides)
    return base


def test_open_sub_account_risky_step_blocked_without_approval(live_mock_app_url, tmp_path):
    artifact = _retargeted("open_sub_account", live_mock_app_url)
    outcome = replay_artifact(artifact, _sub_account_params(), _allowlist(), headless=True, evidence_base=str(tmp_path))
    assert outcome.result_type == "failure"
    assert "risky" in outcome.failure.observed


def test_open_sub_account_succeeds_with_allow_risky(live_mock_app_url, tmp_path):
    artifact = _retargeted("open_sub_account", live_mock_app_url)
    outcome = replay_artifact(artifact, _sub_account_params(), _allowlist(), headless=True, allow_risky=True, evidence_base=str(tmp_path))
    assert outcome.result_type == "success"


def test_open_sub_account_recovers_from_fraud_hold_interstitial(live_mock_app_url, tmp_path):
    artifact = _retargeted("open_sub_account", live_mock_app_url)
    outcome = replay_artifact(
        artifact, _sub_account_params(member_id="60000"), _allowlist(), headless=True, allow_risky=True, evidence_base=str(tmp_path),
    )
    assert outcome.result_type == "success"
    assert any("fraud_review_hold" in r for r in outcome.recovered_conditions)


def test_open_sub_account_hard_backend_failure_is_a_clean_failure(live_mock_app_url, tmp_path):
    artifact = _retargeted("open_sub_account", live_mock_app_url)
    outcome = replay_artifact(
        artifact, _sub_account_params(member_id="70000"), _allowlist(), headless=True, allow_risky=True, evidence_base=str(tmp_path),
    )
    assert outcome.result_type == "failure"
    assert outcome.failure.screenshot_path


def test_open_sub_account_blank_nickname_is_a_validation_business_outcome(live_mock_app_url, tmp_path):
    artifact = _retargeted("open_sub_account", live_mock_app_url)
    outcome = replay_artifact(
        artifact, _sub_account_params(nickname=""), _allowlist(), headless=True, allow_risky=True, evidence_base=str(tmp_path),
    )
    assert outcome.result_type == "business_outcome"
    assert outcome.business_outcome.name == "validation_error_nickname"


def test_open_sub_account_zero_deposit_is_a_validation_business_outcome(live_mock_app_url, tmp_path):
    artifact = _retargeted("open_sub_account", live_mock_app_url)
    outcome = replay_artifact(
        artifact, _sub_account_params(initial_deposit="0"), _allowlist(), headless=True, allow_risky=True, evidence_base=str(tmp_path),
    )
    assert outcome.result_type == "business_outcome"
    assert outcome.business_outcome.name == "validation_error_deposit"


def test_replay_rejects_a_base_url_outside_the_allowlist(live_mock_app_url, tmp_path):
    artifact = _retargeted("lookup_balance", live_mock_app_url)
    narrow = AllowlistPolicy(allowed_domains=["example.com:*"], allowed_route_prefixes=["/"], allowed_actions=["navigate"])
    with pytest.raises(GuardrailViolation):
        replay_artifact(artifact, {"member_id": "10001"}, narrow, headless=True, evidence_base=str(tmp_path))
