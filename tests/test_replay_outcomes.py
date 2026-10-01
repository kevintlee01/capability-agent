"""Replay engine unit tests that don't require a live browser."""
import pytest

from capability_agent.artifact.schema import (
    ActionType, CapabilityArtifact, Checkpoint, Locator, LocatorKind,
    LocatorStrategy, Param, Step, SurfaceType,
)
from capability_agent.guardrails.allowlist import AllowlistPolicy
from capability_agent.replay.engine import _render, _render_locator, replay_artifact


def test_render_substitutes_param_token():
    assert _render("{{params.member_id}}", {"member_id": "10001"}) == "10001"


def test_render_leaves_plain_text_untouched():
    assert _render("Open Account", {"member_id": "10001"}) == "Open Account"


def test_render_locator_substitutes_all_strategies():
    locator = Locator(
        primary=LocatorStrategy(kind=LocatorKind.ROLE, value="{{params.member_id}}", role="link"),
        fallbacks=[LocatorStrategy(kind=LocatorKind.TEXT, value="{{params.member_id}}")],
    )
    rendered = _render_locator(locator, {"member_id": "10001"})
    assert rendered.primary.value == "10001"
    assert rendered.fallbacks[0].value == "10001"


def test_replay_rejects_missing_required_params():
    locator = Locator(primary=LocatorStrategy(kind=LocatorKind.ROLE, value="x", role="button"))
    artifact = CapabilityArtifact(
        artifact_id="a1", name="demo", description="demo",
        target_app="mock", surface_type=SurfaceType.LEGACY_WEB, base_url="http://127.0.0.1:8731",
        params=[Param(name="member_id", type="string", description="id")],
        steps=[Step(step_id=1, action=ActionType.CLICK, description="x", locator=locator)],
        checkpoint=Checkpoint(locator=locator, description="x"),
    )
    with pytest.raises(ValueError, match="member_id"):
        replay_artifact(artifact, input_params={}, allowlist=AllowlistPolicy(
            allowed_domains=["127.0.0.1:*"], allowed_route_prefixes=["/"], allowed_actions=["click"],
        ))
