"""replay/engine.py's step dispatch, retry, and checkpoint-text logic -- all with a fake browser, no real one."""
from unittest.mock import MagicMock

from capability_agent.artifact.schema import ActionType, Checkpoint, Locator, LocatorKind, LocatorStrategy, RetryPolicy, Step
from capability_agent.evidence.logger import RunLogger
from capability_agent.guardrails.allowlist import GuardrailViolation
from capability_agent.replay.engine import _execute_step, _run_step, _verify_checkpoint
from capability_agent.surface.browser import LocatorResolutionError


def _step(action, **overrides):
    base = dict(step_id=1, action=action, description="do it", retry=RetryPolicy(max_attempts=1))
    base.update(overrides)
    return Step(**base)


def test_execute_step_dispatches_wait_for():
    browser = MagicMock()
    step = _step(ActionType.WAIT_FOR, timeout_ms=1234)
    _execute_step(browser, step, {}, {})
    browser.page.wait_for_timeout.assert_called_once_with(1234)


def test_execute_step_assert_checkpoint_passes_when_visible():
    browser = MagicMock()
    browser.is_visible.return_value = True
    locator = Locator(primary=LocatorStrategy(kind=LocatorKind.ROLE, value="Done", role="heading"))
    step = _step(ActionType.ASSERT_CHECKPOINT, locator=locator)
    _execute_step(browser, step, {}, {})


def test_execute_step_assert_checkpoint_raises_when_not_visible():
    browser = MagicMock()
    browser.is_visible.return_value = False
    locator = Locator(primary=LocatorStrategy(kind=LocatorKind.ROLE, value="Done", role="heading"))
    step = _step(ActionType.ASSERT_CHECKPOINT, locator=locator)
    try:
        _execute_step(browser, step, {}, {})
        assert False, "expected LocatorResolutionError"
    except LocatorResolutionError:
        pass


def test_run_step_retries_then_recovers(tmp_path):
    browser = MagicMock()
    browser.click.side_effect = [LocatorResolutionError("not yet"), None]
    locator = Locator(primary=LocatorStrategy(kind=LocatorKind.ROLE, value="Search", role="button"))
    step = _step(ActionType.CLICK, locator=locator, retry=RetryPolicy(max_attempts=2, backoff_ms=1))
    logger = RunLogger("r1", "replay", base_dir=tmp_path)
    recovered = []
    outcome = _run_step(browser, step, {}, logger, recovered, {})
    assert outcome is None
    assert any("retried" in r for r in recovered)


def test_run_step_fails_after_exhausting_retries(tmp_path):
    browser = MagicMock()
    browser.click.side_effect = LocatorResolutionError("never found")
    locator = Locator(primary=LocatorStrategy(kind=LocatorKind.ROLE, value="Search", role="button"))
    step = _step(ActionType.CLICK, locator=locator, retry=RetryPolicy(max_attempts=2, backoff_ms=1))
    logger = RunLogger("r2", "replay", base_dir=tmp_path)
    outcome = _run_step(browser, step, {}, logger, [], {})
    assert outcome.result_type == "failure"
    assert "after 2 attempt(s)" in outcome.failure.message


def test_run_step_returns_failure_immediately_on_guardrail_violation(tmp_path):
    browser = MagicMock()
    browser.click.side_effect = GuardrailViolation("action not in allowlist")
    locator = Locator(primary=LocatorStrategy(kind=LocatorKind.ROLE, value="Search", role="button"))
    step = _step(ActionType.CLICK, locator=locator, retry=RetryPolicy(max_attempts=3))
    logger = RunLogger("r3", "replay", base_dir=tmp_path)
    outcome = _run_step(browser, step, {}, logger, [], {})
    assert outcome.result_type == "failure"
    assert "not in allowlist" in outcome.failure.observed
    browser.click.assert_called_once()


def test_verify_checkpoint_fails_when_expected_text_missing(tmp_path):
    browser = MagicMock()
    browser.is_visible.return_value = True
    browser.extract_text.return_value = "Balance: $12.00"
    checkpoint = Checkpoint(
        locator=Locator(primary=LocatorStrategy(kind=LocatorKind.ROLE, value="Done", role="heading")),
        description="done", expected_text_contains="Account Opened",
    )
    artifact = MagicMock(checkpoint=checkpoint, outputs=[])
    logger = RunLogger("r4", "replay", base_dir=tmp_path)
    outcome = _verify_checkpoint(browser, artifact, {}, {}, [], logger)
    assert outcome.result_type == "failure"
    assert "Account Opened" in outcome.failure.expected


def test_verify_checkpoint_text_match_is_case_and_whitespace_insensitive(tmp_path):
    browser = MagicMock()
    browser.is_visible.return_value = True
    browser.extract_text.return_value = "  ACCOUNTS  "
    checkpoint = Checkpoint(
        locator=Locator(primary=LocatorStrategy(kind=LocatorKind.ROLE, value="Accounts", role="heading")),
        description="done", expected_text_contains="Accounts",
    )
    artifact = MagicMock(checkpoint=checkpoint, outputs=[])
    logger = RunLogger("r5", "replay", base_dir=tmp_path)
    outcome = _verify_checkpoint(browser, artifact, {}, {}, [], logger)
    assert outcome.result_type == "success"


def test_replay_artifact_detects_outcome_before_any_step_runs(tmp_path, monkeypatch):
    from capability_agent.artifact.schema import CapabilityArtifact, OutcomeDefinition, SurfaceType
    from capability_agent.guardrails.allowlist import AllowlistPolicy
    import capability_agent.replay.engine as engine_module

    fake_browser = MagicMock()
    fake_browser.is_visible.return_value = True
    monkeypatch.setattr(engine_module, "BrowserSession", lambda **kwargs: fake_browser)

    artifact = CapabilityArtifact(
        artifact_id="x-1", name="x", description="d", target_app="t", surface_type=SurfaceType.LEGACY_WEB,
        base_url="http://127.0.0.1:9", steps=[],
        checkpoint=Checkpoint(locator=Locator(primary=LocatorStrategy(kind=LocatorKind.ROLE, value="Done", role="heading")), description="done"),
        known_outcomes=[OutcomeDefinition(
            name="already_there", description="detected immediately",
            detector=Locator(primary=LocatorStrategy(kind=LocatorKind.TEXT, value="Already")),
        )],
    )
    allowlist = AllowlistPolicy(allowed_domains=["127.0.0.1:*"], allowed_route_prefixes=["/"], allowed_actions=["navigate"])
    outcome = engine_module.replay_artifact(artifact, {}, allowlist, evidence_base=str(tmp_path))
    assert outcome.result_type == "business_outcome"
    assert outcome.business_outcome.name == "already_there"


def test_replay_artifact_backfills_screenshot_on_step_failure(tmp_path, monkeypatch):
    from capability_agent.artifact.schema import CapabilityArtifact, SurfaceType
    from capability_agent.guardrails.allowlist import AllowlistPolicy
    import capability_agent.replay.engine as engine_module

    fake_browser = MagicMock()
    fake_browser.is_visible.return_value = False
    fake_browser.click.side_effect = LocatorResolutionError("gone")
    monkeypatch.setattr(engine_module, "BrowserSession", lambda **kwargs: fake_browser)

    step = _step(ActionType.CLICK, locator=Locator(primary=LocatorStrategy(kind=LocatorKind.ROLE, value="Go", role="button")))
    artifact = CapabilityArtifact(
        artifact_id="x-2", name="x", description="d", target_app="t", surface_type=SurfaceType.LEGACY_WEB,
        base_url="http://127.0.0.1:9", steps=[step],
        checkpoint=Checkpoint(locator=Locator(primary=LocatorStrategy(kind=LocatorKind.ROLE, value="Done", role="heading")), description="done"),
    )
    allowlist = AllowlistPolicy(allowed_domains=["127.0.0.1:*"], allowed_route_prefixes=["/"], allowed_actions=["click"])
    outcome = engine_module.replay_artifact(artifact, {}, allowlist, evidence_base=str(tmp_path))
    assert outcome.result_type == "failure"
    assert outcome.failure.screenshot_path
    fake_browser.screenshot.assert_called_once()
