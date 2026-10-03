"""Replay a saved capability artifact deterministically against a live surface."""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from capability_agent.artifact.schema import ActionType, CapabilityArtifact, Locator, LocatorStrategy
from capability_agent.evidence.logger import RunLogger
from capability_agent.guardrails.allowlist import AllowlistPolicy, GuardrailViolation
from capability_agent.guardrails.risk import requires_approval_to_replay
from capability_agent.replay.outcomes import BusinessOutcomeDetail, FailureDetail, ReplayOutcome
from capability_agent.surface.browser import BrowserSession, LocatorResolutionError

_PARAM_PATTERN = re.compile(r"\{\{params\.(\w+)\}\}")


def _render(text: str | None, params: dict[str, str]) -> str | None:
    if text is None:
        return None
    return _PARAM_PATTERN.sub(lambda m: str(params.get(m.group(1), m.group(0))), text)


def _render_locator(locator: Locator, params: dict[str, str]) -> Locator:
    def render_strategy(s: LocatorStrategy) -> LocatorStrategy:
        return LocatorStrategy(kind=s.kind, value=_render(s.value, params) or "", role=s.role, nth=s.nth)

    return Locator(
        primary=render_strategy(locator.primary),
        fallbacks=[render_strategy(f) for f in locator.fallbacks],
        frame_path=locator.frame_path,
    )


def _check_known_outcomes(browser: BrowserSession, artifact: CapabilityArtifact, params: dict[str, str]) -> ReplayOutcome | None:
    for outcome in artifact.known_outcomes:
        detector = _render_locator(outcome.detector, params)
        if browser.is_visible(detector):
            return ReplayOutcome(
                result_type="business_outcome",
                business_outcome=BusinessOutcomeDetail(name=outcome.name, description=outcome.description),
            )
    return None


def _dismiss_interstitials(browser: BrowserSession, artifact: CapabilityArtifact, params: dict[str, str], logger: RunLogger, recovered: list[str]) -> None:
    """Dismiss every known interstitial currently showing, one pass each."""
    for handler in artifact.interstitials:
        detector = _render_locator(handler.detector, params)
        if browser.is_visible(detector):
            dismiss = _render_locator(handler.dismiss_action, params)
            browser.click(dismiss)
            recovered.append(f"interstitial '{handler.name}' dismissed")
            logger.event("interstitial_dismissed", {"name": handler.name})


def _fail(browser: BrowserSession, logger: RunLogger, recovered: list[str], step_id: int | None, expected: str, observed: str, message: str) -> ReplayOutcome:
    """Every failure path takes a screenshot -- the richer signal on failure."""
    shot = logger.screenshot_path(f"failure-step{step_id or 'checkpoint'}")
    browser.screenshot(shot)
    failure = FailureDetail(step_id=step_id, expected=expected, observed=observed, message=message, screenshot_path=str(shot))
    logger.write_summary({"status": "failure", "step_id": step_id, "message": message})
    return ReplayOutcome(result_type="failure", failure=failure, recovered_conditions=recovered)


def replay_artifact(
    artifact: CapabilityArtifact,
    input_params: dict[str, str],
    allowlist: AllowlistPolicy,
    headless: bool = True,
    allow_risky: bool = False,
    evidence_base: str = "evidence",
    engine: str = "chromium",
    run_id: str | None = None,
) -> ReplayOutcome:
    missing = artifact.param_names() - input_params.keys()
    if missing:
        raise ValueError(f"Missing required input params: {sorted(missing)}")

    run_id = run_id or f"replay-{uuid.uuid4().hex[:8]}"
    logger = RunLogger(run_id, "replay", base_dir=Path(evidence_base))
    allowlist.check_url(artifact.base_url)
    browser = BrowserSession(base_url=artifact.base_url, headless=headless, engine=engine)
    browser.start()
    recovered: list[str] = []
    extracted: dict[str, str] = {}

    try:
        browser.goto("/")
        outcome = _check_known_outcomes(browser, artifact, input_params)
        if outcome:
            logger.write_summary({"status": "business_outcome", "name": outcome.business_outcome.name})
            return outcome

        for step in artifact.steps:
            if requires_approval_to_replay(step, artifact.status, allow_risky):
                return _fail(
                    browser, logger, recovered, step.step_id, "approval or --allow-risky", "risky step blocked",
                    f"Step {step.step_id} ('{step.description}') is risky and the artifact is not approved.",
                )

            outcome = _run_step(browser, step, input_params, logger, recovered, extracted)
            if outcome is not None:
                if outcome.result_type == "failure" and outcome.failure and not outcome.failure.screenshot_path:
                    shot = logger.screenshot_path(f"failure-step{step.step_id}")
                    browser.screenshot(shot)
                    outcome.failure.screenshot_path = str(shot)
                logger.write_summary({"status": outcome.result_type})
                return outcome

            _dismiss_interstitials(browser, artifact, input_params, logger, recovered)

            outcome = _check_known_outcomes(browser, artifact, input_params)
            if outcome:
                logger.write_summary({"status": "business_outcome", "name": outcome.business_outcome.name})
                return outcome

        return _verify_checkpoint(browser, artifact, input_params, extracted, recovered, logger)
    finally:
        browser.close()


def _run_step(browser: BrowserSession, step, params: dict[str, str], logger: RunLogger, recovered: list[str], extracted: dict[str, str]) -> ReplayOutcome | None:
    attempts = max(1, step.retry.max_attempts)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            _execute_step(browser, step, params, extracted)
            logger.event("step_executed", {"step_id": step.step_id, "attempt": attempt})
            return None
        except LocatorResolutionError as exc:
            last_error = exc
            if attempt < attempts:
                recovered.append(f"step {step.step_id} retried (attempt {attempt})")
                browser.page.wait_for_timeout(step.retry.backoff_ms)
                continue
        except GuardrailViolation as exc:
            logger.event("guardrail_violation", {"step_id": step.step_id, "error": str(exc)})
            return ReplayOutcome(result_type="failure", failure=FailureDetail(
                step_id=step.step_id, expected="action within allowlist", observed=str(exc), message=str(exc),
            ))
    logger.event("step_failed", {"step_id": step.step_id, "error": str(last_error)})
    return ReplayOutcome(result_type="failure", failure=FailureDetail(
        step_id=step.step_id, expected=step.description, observed=str(last_error),
        message=f"Step {step.step_id} failed after {attempts} attempt(s): {last_error}",
    ))


def _execute_step(browser: BrowserSession, step, params: dict[str, str], extracted: dict[str, str]) -> None:
    value = _render(step.value, params)
    locator = _render_locator(step.locator, params) if step.locator else None
    if step.action == ActionType.NAVIGATE:
        browser.goto(value or "/")
    elif step.action == ActionType.CLICK:
        browser.click(locator)
    elif step.action == ActionType.FILL:
        browser.fill(locator, value or "")
    elif step.action == ActionType.SELECT_OPTION:
        browser.select_option(locator, value or "")
    elif step.action == ActionType.WAIT_FOR:
        browser.page.wait_for_timeout(step.timeout_ms)
    elif step.action == ActionType.EXTRACT:
        extracted[step.extract_as or f"step_{step.step_id}"] = browser.extract_text(locator)
    elif step.action == ActionType.ASSERT_CHECKPOINT:
        if not browser.is_visible(locator):
            raise LocatorResolutionError(f"Assertion failed for step {step.step_id}")


def _verify_checkpoint(browser: BrowserSession, artifact: CapabilityArtifact, params: dict[str, str], extracted: dict[str, str], recovered: list[str], logger: RunLogger) -> ReplayOutcome:
    locator = _render_locator(artifact.checkpoint.locator, params)
    if not browser.is_visible(locator):
        return _fail(
            browser, logger, recovered, None, artifact.checkpoint.description, "checkpoint element not found",
            "Replay completed all steps but the success checkpoint was not met.",
        )

    expected_text = artifact.checkpoint.expected_text_contains
    if expected_text:
        actual = browser.extract_text(locator)
        if expected_text.strip().lower() not in actual.strip().lower():
            return _fail(
                browser, logger, recovered, None, f"text containing '{expected_text}'", actual,
                "Checkpoint element found but did not contain the expected text.",
            )

    outputs = {out.name: extracted.get(out.name) for out in artifact.outputs}
    logger.event("checkpoint_verified", {"outputs": outputs})
    logger.write_summary({"status": "success", "outputs": outputs})
    return ReplayOutcome(result_type="success", outputs=outputs, recovered_conditions=recovered)
