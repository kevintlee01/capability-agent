"""Replay a saved capability artifact deterministically against a live surface."""
from __future__ import annotations

import re
import uuid

from playwright.sync_api import Page

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


def replay_artifact(
    artifact: CapabilityArtifact,
    input_params: dict[str, str],
    allowlist: AllowlistPolicy,
    headless: bool = True,
    allow_risky: bool = False,
    evidence_base: str = "evidence",
) -> ReplayOutcome:
    missing = artifact.param_names() - input_params.keys()
    if missing:
        raise ValueError(f"Missing required input params: {sorted(missing)}")

    run_id = f"replay-{uuid.uuid4().hex[:8]}"
    logger = RunLogger(run_id, "replay")
    allowlist.check_url(artifact.base_url)
    browser = BrowserSession(base_url=artifact.base_url, headless=headless)
    page = browser.start()
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
                failure = FailureDetail(
                    step_id=step.step_id, expected="approval or --allow-risky",
                    observed="risky step blocked", message=f"Step {step.step_id} ('{step.description}') is risky and the artifact is not approved.",
                )
                logger.write_summary({"status": "failure", "reason": "risky_step_blocked"})
                return ReplayOutcome(result_type="failure", failure=failure)

            outcome = _run_step(browser, step, input_params, logger, recovered, extracted)
            if outcome is not None:
                logger.write_summary({"status": outcome.result_type})
                return outcome

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
        logger.write_summary({"status": "failure", "reason": "checkpoint_not_met"})
        return ReplayOutcome(result_type="failure", failure=FailureDetail(
            step_id=None, expected=artifact.checkpoint.description, observed="checkpoint element not found",
            message="Replay completed all steps but the success checkpoint was not met.",
        ), recovered_conditions=recovered)

    expected_text = artifact.checkpoint.expected_text_contains
    if expected_text:
        actual = browser.extract_text(locator)
        if expected_text not in actual:
            logger.write_summary({"status": "failure", "reason": "checkpoint_text_mismatch"})
            return ReplayOutcome(result_type="failure", failure=FailureDetail(
                step_id=None, expected=f"text containing '{expected_text}'", observed=actual,
                message="Checkpoint element found but did not contain the expected text.",
            ), recovered_conditions=recovered)

    outputs = {out.name: extracted.get(out.name) for out in artifact.outputs}
    logger.event("checkpoint_verified", {"outputs": outputs})
    logger.write_summary({"status": "success", "outputs": outputs})
    return ReplayOutcome(result_type="success", outputs=outputs, recovered_conditions=recovered)
