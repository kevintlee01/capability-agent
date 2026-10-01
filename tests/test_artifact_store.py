"""Artifact store: save/load round-trip, latest-version resolution, and missing-data error paths."""
import pytest

from capability_agent.artifact.schema import (
    ActionType, CapabilityArtifact, Checkpoint, Locator, LocatorKind, LocatorStrategy, Step, SurfaceType,
)
from capability_agent.artifact.store import list_artifacts, load_artifact, save_artifact


def _artifact(name="demo", version="1.0.0") -> CapabilityArtifact:
    locator = Locator(primary=LocatorStrategy(kind=LocatorKind.ROLE, value="Search", role="button"))
    return CapabilityArtifact(
        artifact_id=f"{name}-1", name=name, version=version, description="d",
        target_app="mock", surface_type=SurfaceType.LEGACY_WEB, base_url="http://127.0.0.1:8731",
        steps=[Step(step_id=1, action=ActionType.CLICK, description="click", locator=locator)],
        checkpoint=Checkpoint(locator=locator, description="done"),
    )


def test_list_artifacts_returns_empty_when_dir_missing(tmp_path):
    assert list_artifacts(base_dir=tmp_path / "nope") == []


def test_save_then_load_round_trips(tmp_path):
    save_artifact(_artifact(), base_dir=tmp_path)
    loaded = load_artifact("demo", "1.0.0", base_dir=tmp_path)
    assert loaded.name == "demo"
    assert loaded.version == "1.0.0"


def test_load_latest_resolves_highest_version(tmp_path):
    save_artifact(_artifact(version="1.0.0"), base_dir=tmp_path)
    save_artifact(_artifact(version="2.0.0"), base_dir=tmp_path)
    loaded = load_artifact("demo", "latest", base_dir=tmp_path)
    assert loaded.version == "2.0.0"


def test_load_latest_raises_when_no_artifacts_exist(tmp_path):
    with pytest.raises(FileNotFoundError, match="demo"):
        load_artifact("demo", "latest", base_dir=tmp_path)


def test_list_artifacts_lists_every_saved_version(tmp_path):
    save_artifact(_artifact(name="a", version="1.0.0"), base_dir=tmp_path)
    save_artifact(_artifact(name="b", version="1.0.0"), base_dir=tmp_path)
    results = list_artifacts(base_dir=tmp_path)
    assert ("a", "1.0.0") in results
    assert ("b", "1.0.0") in results
