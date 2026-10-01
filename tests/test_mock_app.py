"""The mock app's deterministic outcome fixtures must stay deterministic."""
from fastapi.testclient import TestClient

from mock_app.main import app

client = TestClient(app)


def test_known_member_returns_detail_page():
    response = client.get("/member/10001")
    assert response.status_code == 200
    assert "SAV-10001" in response.text


def test_unknown_member_is_not_found():
    response = client.get("/member/00000")
    assert response.status_code == 404


def test_restricted_member_is_permission_denied():
    response = client.get("/member/40300")
    assert response.status_code == 403


def test_expired_member_is_session_expired():
    response = client.get("/member/90000")
    assert response.status_code == 440


def test_open_subaccount_validation_error_on_zero_deposit():
    response = client.post(
        "/member/10001/open-subaccount",
        data={"account_type": "Savings", "nickname": "Rainy Day", "initial_deposit": "0"},
    )
    assert response.status_code == 200
    assert "greater than zero" in response.text


def test_open_subaccount_hard_failure_member():
    response = client.post(
        "/member/70000/open-subaccount",
        data={"account_type": "Savings", "nickname": "Test", "initial_deposit": "10"},
    )
    assert response.status_code == 500


def test_open_subaccount_success_returns_confirmation():
    response = client.post(
        "/member/20002/open-subaccount",
        data={"account_type": "Checking", "nickname": "New Checking", "initial_deposit": "25"},
    )
    assert response.status_code == 200
    assert "Sub-Account Opened" in response.text
