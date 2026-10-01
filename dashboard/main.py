"""Gorgeous read-mostly dashboard: artifacts, run evidence, and escalations."""
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from capability_agent.escalation import operator_cli
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
    })


@app.get("/artifacts/{name}/{version}", response_class=HTMLResponse)
def artifact_detail(request: Request, name: str, version: str):
    artifact = get_artifact(name, version)
    return templates.TemplateResponse(request, "artifact_detail.html", {"artifact": artifact, "name": name, "version": version})


@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run_detail(request: Request, run_id: str):
    run = get_run_detail(run_id)
    return templates.TemplateResponse(request, "run_detail.html", {"run": run})


@app.post("/runs/{run_id}/resume")
def resume_run(run_id: str, note: str = Form("")):
    operator_cli.resume(EVIDENCE_DIR / run_id, note or "resumed from dashboard")
    return RedirectResponse(url=f"/runs/{run_id}", status_code=303)
