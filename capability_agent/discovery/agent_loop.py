"""Observe -> decide -> act loop: the LLM decides, this module executes/guards/records, and compiles a replayable artifact on success."""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from time import monotonic
from typing import Literal

from pydantic import BaseModel, ValidationError

from capability_agent.artifact.schema import (
    ActionType, CapabilityArtifact, Checkpoint, DiscoveryMeta, Locator,
    LocatorKind, LocatorStrategy, Output, Param, Step, SurfaceType,
)
from capability_agent.discovery.prompts import SYSTEM_PROMPT, build_user_prompt
from capability_agent.escalation.control import EscalationContext, SessionControl
from capability_agent.evidence.logger import RunLogger
from capability_agent.guardrails.allowlist import AllowlistPolicy
from capability_agent.llm.base import LLMClient
from capability_agent.surface.browser import BrowserSession
from capability_agent.surface.observation import page_summary

GRACE_STEPS_AFTER_ESCALATION = 5


class AgentDecision(BaseModel):
    reasoning: str
    action: Literal[
        "navigate", "click", "fill", "select_option", "wait_for",
        "extract", "finish_success", "finish_failure", "escalate",
    ]
    target_role: str | None = None
    target_name: str | None = None
    target_nth: int | None = None
    value: str | None = None
    extract_as: str | None = None
    outputs: dict | None = None
    checkpoint_role: str | None = None
    checkpoint_name: str | None = None
    checkpoint_text_contains: str | None = None
    failure_reason: str | None = None


@dataclass
class DiscoveryResult:
    status: Literal["completed", "failed", "escalation_timeout"]
    run_id: str
    artifact: CapabilityArtifact | None = None
    failure_reason: str | None = None


@dataclass
class DiscoveryAgent:
    llm: LLMClient
    allowlist: AllowlistPolicy
    base_url: str
    entry_path: str = "/"
    max_steps: int = 25
    headless: bool = False

    def run(self, name: str, goal: str, params: dict[str, str]) -> DiscoveryResult:
        run_id = f"discover-{uuid.uuid4().hex[:8]}"
        logger = RunLogger(run_id, "discovery")
        browser = BrowserSession(base_url=self.base_url, headless=self.headless)
        page = browser.start()
        control = SessionControl(run_id=run_id, run_dir=logger.run_dir, page=page)
        self.allowlist.check_url(self.base_url)
        browser.goto(self.entry_path)

        recorder = _StepRecorder(base_url=self.base_url, params=params)
        history: list[str] = []
        step_budget = self.max_steps
        start = monotonic()

        try:
            while step_budget > 0:
                step_budget -= 1
                decision = self._decide(page, goal, params, history, logger)

                if decision.action == "finish_success":
                    artifact = recorder.build_artifact(
                        name=name, description=goal, decision=decision,
                        model_name=self.llm.model_name, run_id=run_id,
                        duration_ms=int((monotonic() - start) * 1000),
                    )
                    logger.event("run_finished", {"status": "completed"})
                    logger.write_summary({"status": "completed", "artifact_name": name})
                    return DiscoveryResult(status="completed", run_id=run_id, artifact=artifact)

                if decision.action == "finish_failure":
                    logger.event("run_finished", {"status": "failed", "reason": decision.failure_reason})
                    return DiscoveryResult(status="failed", run_id=run_id, failure_reason=decision.failure_reason)

                if decision.action == "escalate":
                    self._escalate(control, logger, goal, recorder.next_step_id, decision.failure_reason or "model requested escalation", browser)
                    history.append("human intervention completed, re-observing")
                    continue

                self._execute(browser, decision, recorder, logger, history)

            # Step budget exhausted without finishing: that is itself a stuck condition.
            self._escalate(control, logger, goal, recorder.next_step_id, "max discovery steps reached", browser)
            return self._grace_period(browser, control, logger, goal, params, recorder, history, name)
        except Exception as exc:  # noqa: BLE001 - any uncaught failure is a hard failure, logged
            logger.event("run_finished", {"status": "failed", "reason": str(exc)})
            return DiscoveryResult(status="failed", run_id=run_id, failure_reason=str(exc))
        finally:
            browser.close()

    def _grace_period(self, browser, control, logger, goal, params, recorder, history, name) -> DiscoveryResult:
        for _ in range(GRACE_STEPS_AFTER_ESCALATION):
            decision = self._decide(browser.page, goal, params, history, logger)
            if decision.action == "finish_success":
                artifact = recorder.build_artifact(
                    name=name, description=goal, decision=decision,
                    model_name=self.llm.model_name, run_id=control.run_id, duration_ms=0,
                )
                logger.write_summary({"status": "completed_after_escalation"})
                return DiscoveryResult(status="completed", run_id=control.run_id, artifact=artifact)
            if decision.action in ("finish_failure", "escalate"):
                break
            self._execute(browser, decision, recorder, logger, history)
        logger.event("run_finished", {"status": "failed", "reason": "unresolved after escalation"})
        return DiscoveryResult(status="failed", run_id=control.run_id, failure_reason="unresolved after escalation")

    def _decide(self, page, goal, params, history, logger) -> AgentDecision:
        observation = page_summary(page)
        prompt = build_user_prompt(goal, params, observation, history)
        raw = self.llm.complete(SYSTEM_PROMPT, prompt)
        logger.event("llm_raw_response", {"response": raw})
        try:
            decision = AgentDecision.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.event("llm_parse_error", {"error": str(exc)})
            return AgentDecision(reasoning="unparseable response", action="escalate", failure_reason=str(exc))
        logger.event("llm_decision", decision.model_dump())
        return decision

    def _escalate(self, control: SessionControl, logger: RunLogger, goal: str, step_id: int, reason: str, browser: BrowserSession) -> None:
        screenshot = logger.screenshot_path(f"escalation-step{step_id}")
        browser.screenshot(screenshot)
        logger.event("escalation_requested", {"reason": reason, "step_id": step_id, "url": browser.page.url})
        context = EscalationContext(
            run_id=control.run_id, goal=goal, step_id=step_id, reason=reason,
            screenshot_path=str(screenshot), current_url=browser.page.url,
        )
        result = control.request_intervention(context)
        logger.event("escalation_resolved", result)

    def _execute(self, browser: BrowserSession, decision: AgentDecision, recorder: "_StepRecorder", logger: RunLogger, history: list[str]) -> None:
        self.allowlist.check_action(decision.action)
        step = recorder.record(decision)
        try:
            if decision.action == "navigate":
                browser.goto(decision.value or "/")
            elif decision.action == "click":
                browser.click(step.locator)
            elif decision.action == "fill":
                browser.fill(step.locator, decision.value or "")
            elif decision.action == "select_option":
                browser.select_option(step.locator, decision.value or "")
            elif decision.action == "wait_for":
                browser.page.wait_for_timeout(step.timeout_ms)
            elif decision.action == "extract":
                text = browser.extract_text(step.locator)
                recorder.record_extraction(decision.extract_as or "value", text)
            history.append(f"{decision.action} {decision.target_role or ''} '{decision.target_name or decision.value or ''}' -> ok")
            logger.event("action_executed", {"action": decision.action, "target": decision.target_name})
        except Exception as exc:  # noqa: BLE001 - surfaced to history so the model can adapt
            history.append(f"{decision.action} failed: {exc}")
            logger.event("action_failed", {"action": decision.action, "error": str(exc)})


@dataclass
class _StepRecorder:
    base_url: str
    params: dict[str, str]
    steps: list[Step] = field(default_factory=list)
    extracted: dict[str, str] = field(default_factory=dict)
    next_step_id: int = 1

    def record(self, decision: AgentDecision) -> Step:
        locator = None
        if decision.target_role:
            locator = Locator(
                primary=LocatorStrategy(
                    kind=LocatorKind.ROLE, value=self._parameterize(decision.target_name or ""),
                    role=decision.target_role, nth=decision.target_nth,
                ),
            )
            if decision.target_name:
                locator.fallbacks.append(LocatorStrategy(kind=LocatorKind.TEXT, value=self._parameterize(decision.target_name)))
        step = Step(
            step_id=self.next_step_id,
            action=ActionType(decision.action),
            description=decision.reasoning,
            locator=locator,
            value=self._parameterize(decision.value) if decision.value else None,
            extract_as=decision.extract_as,
        )
        self.next_step_id += 1
        self.steps.append(step)
        return step

    def record_extraction(self, name: str, text: str) -> None:
        self.extracted[name] = text

    def _parameterize(self, value: str) -> str:
        for name, concrete in self.params.items():
            if concrete and concrete in value:
                value = value.replace(concrete, f"{{{{params.{name}}}}}")
        return value

    def build_artifact(self, name: str, description: str, decision: AgentDecision, model_name: str, run_id: str, duration_ms: int) -> CapabilityArtifact:
        checkpoint_locator = Locator(
            primary=LocatorStrategy(kind=LocatorKind.ROLE, value=decision.checkpoint_name or "", role=decision.checkpoint_role or "heading"),
            fallbacks=[LocatorStrategy(kind=LocatorKind.TEXT, value=decision.checkpoint_name or "")],
        )
        params = [Param(name=k, type="string", required=True, description=f"Input '{k}'", example=v) for k, v in self.params.items()]
        outputs = [
            Output(name=k, type="string", description=f"Extracted value '{k}'", source_step_id=self.steps[-1].step_id if self.steps else 0)
            for k in (decision.outputs or {}).keys()
        ]
        return CapabilityArtifact(
            artifact_id=f"{name}-{uuid.uuid4().hex[:8]}",
            name=name,
            description=description,
            target_app="meridian-credit-union-mock",
            surface_type=SurfaceType.LEGACY_WEB,
            base_url=self.base_url,
            params=params,
            outputs=outputs,
            steps=self.steps,
            checkpoint=Checkpoint(
                locator=checkpoint_locator,
                expected_text_contains=decision.checkpoint_text_contains,
                description=f"Checkpoint: {decision.checkpoint_role} '{decision.checkpoint_name}'",
            ),
            discovery_meta=DiscoveryMeta(model=model_name, run_id=run_id, step_count=len(self.steps), duration_ms=duration_ms),
        )
