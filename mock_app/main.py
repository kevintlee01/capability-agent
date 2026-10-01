"""Legacy-styled mock back-office app: the target surface for the agent."""
import time

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from mock_app.data import create_sub_account, find_member

app = FastAPI(title="Meridian Credit Union - Teller Console")
templates = Jinja2Templates(directory="mock_app/templates")


@app.get("/", response_class=HTMLResponse)
def search_page(request: Request):
    return templates.TemplateResponse(request, "search.html", {"error": None})


@app.post("/search", response_class=HTMLResponse)
def search_submit(request: Request, member_id: str = Form(...)):
    member_id = member_id.strip()
    if not member_id:
        return templates.TemplateResponse(request, "search.html", {"error": "Member ID is required."})
    if find_member(member_id) is None:
        return templates.TemplateResponse(request, "search.html", {"error": f"No member found for ID {member_id}."})
    return RedirectResponse(url=f"/member/{member_id}", status_code=303)


def _restricted_member_response(request: Request, member_id: str):
    if member_id == "40300":
        return templates.TemplateResponse(request, "permission_denied.html", {"member_id": member_id}, status_code=403)
    if member_id == "90000":
        return templates.TemplateResponse(request, "session_expired.html", {"member_id": member_id}, status_code=440)
    return None


@app.get("/member/{member_id}", response_class=HTMLResponse)
def member_detail(request: Request, member_id: str):
    restricted = _restricted_member_response(request, member_id)
    if restricted is not None:
        return restricted
    if member_id == "50000":
        time.sleep(3.5)
    member = find_member(member_id)
    if member is None:
        return templates.TemplateResponse(request, "not_found.html", {"member_id": member_id}, status_code=404)
    return templates.TemplateResponse(request, "member_detail.html", {"member": member})


@app.get("/member/{member_id}/open-subaccount", response_class=HTMLResponse)
def open_subaccount_form(request: Request, member_id: str):
    restricted = _restricted_member_response(request, member_id)
    if restricted is not None:
        return restricted
    member = find_member(member_id)
    if member is None:
        return templates.TemplateResponse(request, "not_found.html", {"member_id": member_id}, status_code=404)
    return templates.TemplateResponse(request, "open_subaccount.html", {"member": member, "error": None})


@app.post("/member/{member_id}/open-subaccount", response_class=HTMLResponse)
def open_subaccount_submit(
    request: Request,
    member_id: str,
    account_type: str = Form(...),
    nickname: str = Form(""),
    initial_deposit: str = Form(...),
):
    restricted = _restricted_member_response(request, member_id)
    if restricted is not None:
        return restricted
    member = find_member(member_id)
    if member is None:
        return templates.TemplateResponse(request, "not_found.html", {"member_id": member_id}, status_code=404)

    try:
        deposit = float(initial_deposit)
    except ValueError:
        deposit = -1.0
    if not nickname.strip():
        return templates.TemplateResponse(
            request, "open_subaccount.html", {"member": member, "error": "Nickname is required."}
        )
    if deposit <= 0:
        return templates.TemplateResponse(
            request, "open_subaccount.html", {"member": member, "error": "Initial deposit must be greater than zero."}
        )

    if member_id == "70000":
        return templates.TemplateResponse(request, "server_error.html", {"member_id": member_id}, status_code=500)
    if member_id == "60000":
        return templates.TemplateResponse(
            request,
            "fraud_hold.html",
            {"member": member, "account_type": account_type, "nickname": nickname, "initial_deposit": deposit},
        )

    account = create_sub_account(member_id, account_type, nickname.strip(), deposit)
    return templates.TemplateResponse(request, "confirmation.html", {"member": member, "account": account})


@app.post("/member/{member_id}/open-subaccount/confirm-hold", response_class=HTMLResponse)
def confirm_fraud_hold(
    request: Request,
    member_id: str,
    account_type: str = Form(...),
    nickname: str = Form(...),
    initial_deposit: float = Form(...),
):
    member = find_member(member_id)
    account = create_sub_account(member_id, account_type, nickname, initial_deposit)
    return templates.TemplateResponse(request, "confirmation.html", {"member": member, "account": account})
