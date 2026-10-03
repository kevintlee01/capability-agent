"""Mostly-read-only dashboard: artifacts, run evidence, escalations, plus demo-friendly discover/replay buttons."""
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from capability_agent.escalation import operator_cli
from dashboard.actions import trigger_discover, trigger_replay
from dashboard.data import (
    EVIDENCE_DIR, get_artifact, get_run_detail, list_artifact_summaries,
    list_run_summaries, outcome_distribution,
)

app = FastAPI(title="Capability Agent - Mission Control")
app.mount("/evidence", StaticFiles(directory="evidence"), name="evidence")
templates = Jinja2Templates(directory="dashboard/templates")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    artifacts = list_artifact_summaries()
    runs = list_run_summaries()
    return templates.TemplateResponse(request, "index.html", {
        "artifacts": artifacts,
        "runs": runs[:10],
        "total_runs": len(runs),
        "pending_count": sum(1 for r in runs if r["pending_escalation"]),
        "distribution": outcome_distribution(),
        "active": "overview",
        "page_title": "Overview",
        "page_subtitle": "Everything this system has discovered and replayed, in one place.",
    })


@app.get("/artifacts/{name}/{version}", response_class=HTMLResponse)
def artifact_detail(request: Request, name: str, version: str):
    artifact = get_artifact(name, version)
    title = f"{name} v{version}" if artifact else "Capability not found"
    return templates.TemplateResponse(request, "artifact_detail.html", {
        "artifact": artifact, "name": name, "version": version, "active": "capabilities",
        "page_title": title, "page_subtitle": "Capability artifact",
    })


@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run_detail(request: Request, run_id: str):
    run = get_run_detail(run_id)
    return templates.TemplateResponse(request, "run_detail.html", {
        "run": run, "active": "runs",
        "page_title": run_id, "page_subtitle": "Run evidence",
    })


@app.post("/runs/{run_id}/resume")
def resume_run(run_id: str, note: str = Form("")):
    operator_cli.resume(EVIDENCE_DIR / run_id, note or "resumed from dashboard")
    return RedirectResponse(url=f"/runs/{run_id}", status_code=303)


def _extract_params(form) -> dict[str, str]:
    """Pull every 'param__<name>' form field into a plain params dict."""
    prefix = "param__"
    return {k[len(prefix):]: v for k, v in form.items() if k.startswith(prefix) and v}


@app.get("/discover", response_class=HTMLResponse)
def discover_form(request: Request):
    return templates.TemplateResponse(request, "discover.html", {
        "active": "discover", "page_title": "Discover / Replay",
        "page_subtitle": "Kick off a live LLM discovery or re-run a saved capability",
    })


@app.post("/discover")
async def discover_submit(request: Request):
    form = await request.form()
    name = (form.get("name") or "").strip()
    goal = (form.get("goal") or "").strip()
    run_id = await run_in_threadpool(trigger_discover, name, goal, _extract_params(form))
    return RedirectResponse(url=f"/runs/{run_id}", status_code=303)


@app.post("/artifacts/{name}/{version}/replay")
async def replay_submit(request: Request, name: str, version: str):
    form = await request.form()
    allow_risky = form.get("allow_risky") == "on"
    run_id = await run_in_threadpool(trigger_replay, name, version, _extract_params(form), allow_risky)
    return RedirectResponse(url=f"/runs/{run_id}", status_code=303)
