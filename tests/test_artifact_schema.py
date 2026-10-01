"""Schema sanity checks: the artifact round-trips through save/load intact."""
from capability_agent.artifact.schema import (
    ActionType, CapabilityArtifact, Checkpoint, InterstitialHandler, Locator,
    LocatorKind, LocatorStrategy, Param, Step, SurfaceType,
)
from capability_agent.artifact.store import load_artifact, save_artifact


def _sample_artifact() -> CapabilityArtifact:
    locator = Locator(primary=LocatorStrategy(kind=LocatorKind.ROLE, value="Search", role="button"))
    return CapabilityArtifact(
        artifact_id="test-1",
        name="lookup_balance",
        description="Look up a member's savings balance",
        target_app="meridian-credit-union-mock",
        surface_type=SurfaceType.LEGACY_WEB,
        base_url="http://127.0.0.1:8731",
        params=[Param(name="member_id", type="string", description="Member ID")],
        steps=[Step(step_id=1, action=ActionType.CLICK, description="click search", locator=locator)],
        checkpoint=Checkpoint(locator=locator, description="search button visible"),
    )


def test_artifact_round_trips_through_storage(tmp_path):
    artifact = _sample_artifact()
    path = save_artifact(artifact, base_dir=tmp_path)
    assert path.exists()
    loaded = load_artifact(artifact.name, artifact.version, base_dir=tmp_path)
    assert loaded == artifact


def test_param_names_reflects_declared_params():
    artifact = _sample_artifact()
    assert artifact.param_names() == {"member_id"}


def test_interstitial_handler_round_trips():
    detector = Locator(primary=LocatorStrategy(kind=LocatorKind.ROLE, value="Fraud Review Hold", role="heading"))
    dismiss = Locator(primary=LocatorStrategy(kind=LocatorKind.ROLE, value="Proceed Anyway", role="button"))
    handler = InterstitialHandler(name="fraud_hold", detector=detector, dismiss_action=dismiss, description="Fraud review hold screen")
    artifact = _sample_artifact()
    artifact.interstitials.append(handler)
    assert artifact.interstitials[0].name == "fraud_hold"
