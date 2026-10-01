"""Load and save capability artifacts as versioned JSON files on disk."""
import json
from pathlib import Path

from capability_agent.artifact.schema import CapabilityArtifact

DEFAULT_ARTIFACT_DIR = Path("artifacts")


def artifact_path(name: str, version: str, base_dir: Path = DEFAULT_ARTIFACT_DIR) -> Path:
    return base_dir / name / f"{version}.json"


def save_artifact(artifact: CapabilityArtifact, base_dir: Path = DEFAULT_ARTIFACT_DIR) -> Path:
    path = artifact_path(artifact.name, artifact.version, base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(artifact.model_dump_json(indent=2))
    return path


def load_artifact(name: str, version: str = "latest", base_dir: Path = DEFAULT_ARTIFACT_DIR) -> CapabilityArtifact:
    if version == "latest":
        version = _latest_version(name, base_dir)
    path = artifact_path(name, version, base_dir)
    data = json.loads(path.read_text())
    return CapabilityArtifact.model_validate(data)


def list_artifacts(base_dir: Path = DEFAULT_ARTIFACT_DIR) -> list[tuple[str, str]]:
    if not base_dir.exists():
        return []
    results = []
    for name_dir in sorted(base_dir.iterdir()):
        if name_dir.is_dir():
            for version_file in sorted(name_dir.glob("*.json")):
                results.append((name_dir.name, version_file.stem))
    return results


def _latest_version(name: str, base_dir: Path) -> str:
    versions = sorted((base_dir / name).glob("*.json"))
    if not versions:
        raise FileNotFoundError(f"No artifacts found for capability '{name}'")
    return versions[-1].stem
