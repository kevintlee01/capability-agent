"""Guardrail unit tests: allowlist, risk classification, redaction."""
import pytest

from capability_agent.artifact.schema import ActionType, RiskLevel, Step
from capability_agent.guardrails.allowlist import AllowlistPolicy, GuardrailViolation
from capability_agent.guardrails.redact import redact_dict, redact_text
from capability_agent.guardrails.risk import classify_step_risk, requires_approval_to_replay


def _policy() -> AllowlistPolicy:
    return AllowlistPolicy(
        allowed_domains=["127.0.0.1:*"],
        allowed_route_prefixes=["/member"],
        allowed_actions=["navigate", "click"],
    )


def test_allowlist_blocks_unlisted_domain():
    with pytest.raises(GuardrailViolation):
        _policy().check_url("http://evil.example.com/member/1")


def test_allowlist_blocks_unlisted_route():
    with pytest.raises(GuardrailViolation):
        _policy().check_url("http://127.0.0.1:8731/admin")


def test_allowlist_allows_listed_route():
    _policy().check_url("http://127.0.0.1:8731/member/10001")


def test_allowlist_blocks_disallowed_action():
    with pytest.raises(GuardrailViolation):
        _policy().check_action("fill")


def test_risk_classification_flags_submit_keyword():
    step = Step(step_id=1, action=ActionType.CLICK, description="click submit to confirm transfer")
    assert classify_step_risk(step) == RiskLevel.RISKY


def test_risk_classification_leaves_reads_safe():
    step = Step(step_id=1, action=ActionType.EXTRACT, description="read the balance")
    assert classify_step_risk(step) == RiskLevel.SAFE


def test_risky_step_blocked_on_draft_artifact_without_override():
    step = Step(step_id=1, action=ActionType.CLICK, description="click confirm")
    assert requires_approval_to_replay(step, artifact_status="draft", allow_risky=False) is True
    assert requires_approval_to_replay(step, artifact_status="approved", allow_risky=False) is False
    assert requires_approval_to_replay(step, artifact_status="draft", allow_risky=True) is False


def test_redact_text_scrubs_ssn_and_email():
    scrubbed = redact_text("ssn 123-45-6789 contact a@b.com")
    assert "123-45-6789" not in scrubbed
    assert "a@b.com" not in scrubbed


def test_redact_dict_scrubs_sensitive_field_names():
    scrubbed = redact_dict({"password": "hunter2", "note": "fine"})
    assert scrubbed["password"] == "[REDACTED]"
    assert scrubbed["note"] == "fine"
