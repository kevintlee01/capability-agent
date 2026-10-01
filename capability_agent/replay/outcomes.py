"""The replay result taxonomy: success, known business outcome, or failure -- a caller must never have to guess whether 'not found' was a crash."""
from typing import Literal

from pydantic import BaseModel


class FailureDetail(BaseModel):
    step_id: int | None
    expected: str
    observed: str
    message: str
    screenshot_path: str | None = None


class BusinessOutcomeDetail(BaseModel):
    name: str
    description: str


class ReplayOutcome(BaseModel):
    result_type: Literal["success", "business_outcome", "failure"]
    outputs: dict | None = None
    business_outcome: BusinessOutcomeDetail | None = None
    failure: FailureDetail | None = None
    recovered_conditions: list[str] = []
