"""Write-path actions the dashboard can trigger: a real discovery run or a real replay run."""
from __future__ import annotations

import uuid
from pathlib import Path

from capability_agent.artifact.store import load_artifact, save_artifact
from capability_agent.config import settings
from capability_agent.discovery.agent_loop import DiscoveryAgent
from capability_agent.guardrails.allowlist import AllowlistPolicy
from capability_agent.llm.factory import build_llm_client
from capability_agent.replay.engine import replay_artifact


def trigger_discover(name: str, goal: str, params: dict[str, str]) -> str:
    """Run a real LLM discovery session, save the artifact on success, and return the run_id."""
    allowlist = AllowlistPolicy.load(Path(settings.allowlist_path))
    llm = build_llm_client(settings)
    agent = DiscoveryAgent(
        llm=llm, allowlist=allowlist, base_url=settings.target_base_url,
        headless=settings.headless, evidence_base=settings.evidence_dir,
    )
    result = agent.run(name=name, goal=goal, params=params)
    if result.status == "completed" and result.artifact:
        save_artifact(result.artifact, Path(settings.artifact_dir))
    return result.run_id


def trigger_replay(name: str, version: str, params: dict[str, str], allow_risky: bool) -> str:
    """Deterministically replay a saved artifact and return the run_id, even on failure."""
    run_id = f"replay-{uuid.uuid4().hex[:8]}"
    allowlist = AllowlistPolicy.load(Path(settings.allowlist_path))
    artifact = load_artifact(name, version, Path(settings.artifact_dir))
    replay_artifact(
        artifact=artifact, input_params=params, allowlist=allowlist,
        headless=True, allow_risky=allow_risky, evidence_base=settings.evidence_dir, run_id=run_id,
    )
    return run_id
