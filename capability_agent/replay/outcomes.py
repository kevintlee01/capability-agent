"""The replay result taxonomy: success, known business outcome, or failure.

This three-way split is the core design move for error handling: a caller
must never have to guess whether 'no such member' was a crash.
"""
from typing import Literal

from pydantic import BaseModel


class FailureDetail(BaseModel):
    step_id: int | None
    expected: str
    observed: str
    message: str


class BusinessOutcomeDetail(BaseModel):
    name: str
    description: str


class ReplayOutcome(BaseModel):
    result_type: Literal["success", "business_outcome", "failure"]
    outputs: dict | None = None
    business_outcome: BusinessOutcomeDetail | None = None
    failure: FailureDetail | None = None
    recovered_conditions: list[str] = []
