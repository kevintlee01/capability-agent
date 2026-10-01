"""CLI entry point: discover a capability, replay it, or act as the operator."""
from __future__ import annotations

from pathlib import Path

import typer

from capability_agent.artifact.schema import CapabilityArtifact
from capability_agent.artifact.store import list_artifacts, load_artifact, save_artifact
from capability_agent.config import settings
from capability_agent.discovery.agent_loop import DiscoveryAgent
from capability_agent.escalation import operator_cli
from capability_agent.guardrails.allowlist import AllowlistPolicy
from capability_agent.llm.openai_client import OpenAIClient
from capability_agent.replay.engine import replay_artifact

app = typer.Typer(help="Computer-use discovery + deterministic replay system.")
operator_app = typer.Typer(help="Mock operator surface for human handoff.")
app.add_typer(operator_app, name="operator")


def _parse_params(raw: list[str]) -> dict[str, str]:
    parsed = {}
    for item in raw:
        key, _, value = item.partition("=")
        parsed[key] = value
    return parsed


@app.command()
def discover(
    name: str = typer.Option(..., help="Capability name, e.g. open_sub_account"),
    goal: str = typer.Option(..., help="Natural-language goal for the agent"),
    param: list[str] = typer.Option([], help="key=value, repeatable"),
    entry_path: str = typer.Option("/", help="Path to start the run at"),
    max_steps: int = typer.Option(settings.max_discovery_steps),
    headless: bool = typer.Option(settings.headless),
):
    """Run a real LLM-driven discovery session and save the resulting artifact."""
    allowlist = AllowlistPolicy.load(Path(settings.allowlist_path))
    llm = OpenAIClient(api_key=settings.openai_api_key, model_name=settings.openai_model)
    agent = DiscoveryAgent(
        llm=llm, allowlist=allowlist, base_url=settings.target_base_url,
        entry_path=entry_path, max_steps=max_steps, headless=headless,
    )
    result = agent.run(name=name, goal=goal, params=_parse_params(param))
    typer.echo(f"Run {result.run_id}: {result.status}")
    if result.status == "completed" and result.artifact:
        path = save_artifact(result.artifact, Path(settings.artifact_dir))
        typer.echo(f"Artifact saved to {path}")
    elif result.failure_reason:
        typer.echo(f"Failure: {result.failure_reason}")
        raise typer.Exit(code=1)


@app.command()
def replay(
    name: str = typer.Option(...),
    version: str = typer.Option("latest"),
    param: list[str] = typer.Option([], help="key=value, repeatable"),
    headless: bool = typer.Option(True),
    allow_risky: bool = typer.Option(False),
):
    """Deterministically replay a saved artifact, no LLM involved."""
    allowlist = AllowlistPolicy.load(Path(settings.allowlist_path))
    artifact: CapabilityArtifact = load_artifact(name, version, Path(settings.artifact_dir))
    outcome = replay_artifact(
        artifact=artifact, input_params=_parse_params(param), allowlist=allowlist,
        headless=headless, allow_risky=allow_risky, evidence_base=settings.evidence_dir,
    )
    typer.echo(outcome.model_dump_json(indent=2))
    if outcome.result_type == "failure":
        raise typer.Exit(code=1)


@app.command(name="list")
def list_cmd():
    """List saved capability artifacts."""
    for name, version in list_artifacts(Path(settings.artifact_dir)):
        typer.echo(f"{name} @ {version}")


@operator_app.command("status")
def operator_status(run_id: str):
    context = operator_cli.show_status(Path(settings.evidence_dir) / run_id)
    if context is None:
        typer.echo("No pending intervention for that run.")
        return
    typer.echo(f"Goal: {context['goal']}")
    typer.echo(f"Stuck at step {context['step_id']}: {context['reason']}")
    typer.echo(f"Current URL: {context['current_url']}")
    typer.echo(f"Screenshot: {context['screenshot_path']}")


@operator_app.command("resume")
def operator_resume(run_id: str, note: str = typer.Option("", help="What the human did")):
    operator_cli.resume(Path(settings.evidence_dir) / run_id, note)
    typer.echo(f"Resume signal sent for {run_id}.")


if __name__ == "__main__":
    app()
