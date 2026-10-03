"""DiscoveryAgent's full loop against a REAL browser + REAL mock app, with a scripted FakeLLM (no network)."""
import threading
import time
from pathlib import Path

from capability_agent.discovery.agent_loop import DiscoveryAgent
from capability_agent.escalation import operator_cli
from capability_agent.guardrails.allowlist import AllowlistPolicy
from capability_agent.replay.engine import replay_artifact


class FakeLLMClient:
    model_name = "fake-llm-v1"

    def __init__(self, decisions):
        self._decisions = list(decisions)
        self.calls = 0

    def complete(self, system_prompt, user_prompt):
        import json

        decision = self._decisions[min(self.calls, len(self._decisions) - 1)]
        self.calls += 1
        return decision if isinstance(decision, str) else json.dumps(decision)


class PersistentResumer:
    """Watches tmp_path for an intervention.json and resumes it automatically, simulating an operator."""

    def __init__(self, base_dir: Path, note: str, delay_s: float = 0.2):
        self.base_dir = base_dir
        self.note = note
        self.delay_s = delay_s
        self._stop = False
        self._thread = threading.Thread(target=self._watch, daemon=True)

    def _watch(self):
        deadline = time.monotonic() + 10
        while not self._stop and time.monotonic() < deadline:
            if self.base_dir.exists():
                for run_dir in self.base_dir.iterdir():
                    if (run_dir / "intervention.json").exists() and not (run_dir / "resume.signal").exists():
                        time.sleep(self.delay_s)
                        operator_cli.resume(run_dir, self.note)
                        return
            time.sleep(0.05)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop = True
        self._thread.join(timeout=2)


def _allowlist():
    return AllowlistPolicy(
        allowed_domains=["127.0.0.1:*"], allowed_route_prefixes=["/"],
        allowed_actions=["navigate", "click", "fill", "select_option", "wait_for", "extract"],
    )


def _agent(llm, base_url, tmp_path, max_steps=10):
    return DiscoveryAgent(
        llm=llm, allowlist=_allowlist(), base_url=base_url,
        entry_path="/", max_steps=max_steps, headless=True, evidence_base=str(tmp_path),
    )


def test_discovery_completes_and_builds_an_artifact(live_mock_app_url, tmp_path):
    decisions = [
        {"reasoning": "fill member id", "action": "fill", "target_role": "textbox", "target_nth": 0, "value": "10001"},
        {"reasoning": "search", "action": "click", "target_role": "button", "target_name": "Search"},
        {"reasoning": "done", "action": "finish_success", "checkpoint_role": "heading", "checkpoint_name": "Accounts"},
    ]
    agent = _agent(FakeLLMClient(decisions), live_mock_app_url, tmp_path)
    result = agent.run(name="demo", goal="look up member 10001", params={"member_id": "10001"})
    assert result.status == "completed"
    assert result.artifact is not None
    assert result.artifact.name == "demo"


def test_discovery_finish_failure_is_reported(live_mock_app_url, tmp_path):
    decisions = [{"reasoning": "give up", "action": "finish_failure", "failure_reason": "cannot find it"}]
    agent = _agent(FakeLLMClient(decisions), live_mock_app_url, tmp_path)
    result = agent.run(name="demo", goal="goal", params={})
    assert result.status == "failed"
    assert result.failure_reason == "cannot find it"


def test_discovery_escalate_then_resume_completes(live_mock_app_url, tmp_path):
    decisions = [
        {"reasoning": "stuck", "action": "escalate", "failure_reason": "ambiguous state"},
        {"reasoning": "done", "action": "finish_success", "checkpoint_role": "heading", "checkpoint_name": "Member Search"},
    ]
    agent = _agent(FakeLLMClient(decisions), live_mock_app_url, tmp_path)
    with PersistentResumer(tmp_path, "operator looked and unblocked it"):
        result = agent.run(name="demo", goal="goal", params={})
    assert result.status == "completed"


def test_discovery_detects_stuck_loop_and_escalates_before_exhausting_step_budget(live_mock_app_url, tmp_path):
    decisions = [
        {"reasoning": "click something that is not there", "action": "click", "target_role": "button", "target_name": "Nonexistent Button"},
        {"reasoning": "try the exact same thing again", "action": "click", "target_role": "button", "target_name": "Nonexistent Button"},
        {"reasoning": "done", "action": "finish_success", "checkpoint_role": "heading", "checkpoint_name": "Member Search"},
    ]
    llm = FakeLLMClient(decisions)
    agent = _agent(llm, live_mock_app_url, tmp_path, max_steps=10)
    with PersistentResumer(tmp_path, "unstuck it"):
        result = agent.run(name="demo", goal="goal", params={})
    assert result.status == "completed"
    assert llm.calls == 3, "should escalate right after 2 identical failures, not burn all 10 steps"
    log_path = next(tmp_path.glob("discover-*/log.jsonl"))
    assert "stuck_loop_detected" in log_path.read_text()


def test_discovery_stuck_loop_counter_resets_after_a_different_action(live_mock_app_url, tmp_path):
    decisions = [
        {"reasoning": "click something that is not there", "action": "click", "target_role": "button", "target_name": "Nonexistent Button"},
        {"reasoning": "try a different nonexistent target", "action": "click", "target_role": "button", "target_name": "Also Nonexistent"},
        {"reasoning": "done", "action": "finish_success", "checkpoint_role": "heading", "checkpoint_name": "Member Search"},
    ]
    llm = FakeLLMClient(decisions)
    agent = _agent(llm, live_mock_app_url, tmp_path, max_steps=10)
    result = agent.run(name="demo", goal="goal", params={})
    assert result.status == "completed"
    assert llm.calls == 3, "two DIFFERENT failures in a row should not trigger stuck-loop escalation"


def test_discovery_unparseable_llm_response_escalates_then_resumes(live_mock_app_url, tmp_path):
    decisions = [
        "not json at all",
        {"reasoning": "done", "action": "finish_success", "checkpoint_role": "heading", "checkpoint_name": "Member Search"},
    ]
    agent = _agent(FakeLLMClient(decisions), live_mock_app_url, tmp_path)
    with PersistentResumer(tmp_path, "fixed it manually"):
        result = agent.run(name="demo", goal="goal", params={})
    assert result.status == "completed"


def test_discovery_max_steps_exhausted_then_succeeds_in_grace_period(live_mock_app_url, tmp_path):
    decisions = [
        {"reasoning": "wait a moment", "action": "wait_for"},
        {"reasoning": "click search", "action": "click", "target_role": "button", "target_name": "Search"},
        {"reasoning": "done", "action": "finish_success", "checkpoint_role": "heading", "checkpoint_name": "Member Search"},
    ]
    agent = _agent(FakeLLMClient(decisions), live_mock_app_url, tmp_path, max_steps=1)
    with PersistentResumer(tmp_path, "let it keep going"):
        result = agent.run(name="demo", goal="goal", params={})
    assert result.status == "completed"


def test_discovery_grace_period_still_stuck_gives_up_cleanly(live_mock_app_url, tmp_path):
    decisions = [
        {"reasoning": "wait a moment", "action": "wait_for"},
        {"reasoning": "still stuck", "action": "escalate", "failure_reason": "still stuck"},
    ]
    agent = _agent(FakeLLMClient(decisions), live_mock_app_url, tmp_path, max_steps=1)
    with PersistentResumer(tmp_path, "take a look"):
        result = agent.run(name="demo", goal="goal", params={})
    assert result.status == "failed"
    assert result.failure_reason == "unresolved after escalation"


def test_discovery_exercises_every_action_dispatch_branch(live_mock_app_url, tmp_path):
    decisions = [
        {"reasoning": "go to the open-subaccount form", "action": "navigate", "value": "/member/20002/open-subaccount"},
        {"reasoning": "click something that is not there", "action": "click", "target_role": "button", "target_name": "Nonexistent Button"},
        {"reasoning": "pick an account type", "action": "select_option", "target_role": "combobox", "target_nth": 0, "value": "Checking"},
        {"reasoning": "read the heading", "action": "extract", "target_role": "heading", "target_nth": 0, "extract_as": "heading_text"},
        {
            "reasoning": "done", "action": "finish_success",
            "checkpoint_role": "heading", "checkpoint_name": "Open Sub-Account", "outputs": {"heading_text": "x"},
        },
    ]
    agent = _agent(FakeLLMClient(decisions), live_mock_app_url, tmp_path, max_steps=10)
    result = agent.run(name="demo", goal="goal", params={})
    assert result.status == "completed"


def test_discovery_hard_crash_in_llm_call_is_a_clean_failure(live_mock_app_url, tmp_path):
    class ExplodingLLM:
        model_name = "fake-llm-v1"

        def complete(self, system_prompt, user_prompt):
            raise RuntimeError("the LLM provider is down")

    agent = _agent(ExplodingLLM(), live_mock_app_url, tmp_path, max_steps=5)
    result = agent.run(name="demo", goal="goal", params={})
    assert result.status == "failed"
    assert "the LLM provider is down" in result.failure_reason


def test_full_pipeline_discovered_artifact_replays_successfully_llm_free(live_mock_app_url, tmp_path):
    decisions = [
        {"reasoning": "fill member id", "action": "fill", "target_role": "textbox", "target_nth": 0, "value": "10001"},
        {"reasoning": "search", "action": "click", "target_role": "button", "target_name": "Search"},
        {"reasoning": "done", "action": "finish_success", "checkpoint_role": "heading", "checkpoint_name": "Member Detail"},
    ]
    agent = _agent(FakeLLMClient(decisions), live_mock_app_url, tmp_path)
    discovery_result = agent.run(name="pipeline_demo", goal="look up member 10001", params={"member_id": "10001"})
    assert discovery_result.status == "completed"

    outcome = replay_artifact(discovery_result.artifact, {"member_id": "10001"}, _allowlist(), headless=True, evidence_base=str(tmp_path))
    assert outcome.result_type == "success"

    outcome_other_member = replay_artifact(discovery_result.artifact, {"member_id": "20002"}, _allowlist(), headless=True, evidence_base=str(tmp_path))
    assert outcome_other_member.result_type == "success"
