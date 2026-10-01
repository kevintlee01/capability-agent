"""_StepRecorder: locator construction, parameterization, extraction bookkeeping, and artifact assembly."""
from capability_agent.discovery.agent_loop import AgentDecision, _StepRecorder


def _decision(**overrides):
    base = dict(reasoning="do it", action="click", target_role="button", target_name="Search")
    base.update(overrides)
    return AgentDecision(**base)


def test_record_builds_role_locator_with_text_fallback():
    recorder = _StepRecorder(base_url="http://x", params={})
    step = recorder.record(_decision())
    assert step.locator.primary.role == "button"
    assert step.locator.primary.value == "Search"
    assert step.locator.fallbacks[0].value == "Search"
    assert step.step_id == 1


def test_record_increments_step_ids():
    recorder = _StepRecorder(base_url="http://x", params={})
    recorder.record(_decision())
    second = recorder.record(_decision(target_name="Submit"))
    assert second.step_id == 2


def test_record_omits_locator_when_no_target_role():
    recorder = _StepRecorder(base_url="http://x", params={})
    step = recorder.record(_decision(action="navigate", target_role=None, target_name=None, value="/home"))
    assert step.locator is None
    assert step.value == "/home"


def test_parameterize_replaces_matching_param_values():
    recorder = _StepRecorder(base_url="http://x", params={"member_id": "10001"})
    step = recorder.record(_decision(action="fill", target_role="textbox", target_name=None, value="10001"))
    assert step.value == "{{params.member_id}}"


def test_parameterize_leaves_unrelated_values_untouched():
    recorder = _StepRecorder(base_url="http://x", params={"member_id": "10001"})
    step = recorder.record(_decision(action="click", target_name="Search"))
    assert step.locator.primary.value == "Search"


def test_record_extraction_stores_value_by_name():
    recorder = _StepRecorder(base_url="http://x", params={})
    recorder.record_extraction("balance", "$42.00")
    assert recorder.extracted["balance"] == "$42.00"


def test_build_artifact_includes_params_outputs_and_checkpoint():
    recorder = _StepRecorder(base_url="http://x", params={"member_id": "10001"})
    recorder.record(_decision(action="fill", target_role="textbox", target_name=None, value="10001"))
    finish = _decision(
        action="finish_success", target_role=None, target_name=None,
        outputs={"balance": "$42.00"}, checkpoint_role="heading", checkpoint_name="Accounts",
        checkpoint_text_contains="Accounts",
    )
    artifact = recorder.build_artifact(
        name="demo", description="goal", decision=finish, model_name="fake-model", run_id="r1", duration_ms=10,
    )
    assert artifact.name == "demo"
    assert artifact.params[0].name == "member_id"
    assert artifact.outputs[0].name == "balance"
    assert artifact.checkpoint.locator.primary.value == "Accounts"
    assert artifact.discovery_meta.model == "fake-model"
    assert artifact.discovery_meta.step_count == 1


def test_build_artifact_with_no_steps_defaults_output_source_step_id_to_zero():
    recorder = _StepRecorder(base_url="http://x", params={})
    finish = _decision(action="finish_success", target_role=None, target_name=None, outputs={"x": "y"})
    artifact = recorder.build_artifact(
        name="demo", description="goal", decision=finish, model_name="m", run_id="r1", duration_ms=0,
    )
    assert artifact.outputs[0].source_step_id == 0
