"""The capability artifact schema: a typed, versioned, replayable flow.

Design intent: a capability artifact is a contract between three readers --
a human reviewer, the deterministic replay engine, and a calling AI agent.
None of them should need the raw LLM transcript to understand it.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class SurfaceType(str, Enum):
    WEB = "web"
    LEGACY_WEB = "legacy_web"
    DESKTOP = "desktop"


class ActionType(str, Enum):
    NAVIGATE = "navigate"
    CLICK = "click"
    FILL = "fill"
    SELECT_OPTION = "select_option"
    WAIT_FOR = "wait_for"
    EXTRACT = "extract"
    ASSERT_CHECKPOINT = "assert_checkpoint"


class RiskLevel(str, Enum):
    SAFE = "safe"
    RISKY = "risky"


class LocatorKind(str, Enum):
    ROLE = "role"
    TEXT = "text"
    LABEL = "label"
    CSS = "css"
    XPATH = "xpath"
    TEST_ID = "test_id"


class LocatorStrategy(BaseModel):
    """One way to find a control. Artifacts rank several, most-robust first."""

    kind: LocatorKind
    value: str
    role: str | None = None
    nth: int | None = None


class Locator(BaseModel):
    """Robust control targeting: a primary strategy plus ordered fallbacks."""

    primary: LocatorStrategy
    fallbacks: list[LocatorStrategy] = Field(default_factory=list)
    frame_path: list[str] = Field(default_factory=list)

    def all_strategies(self) -> list[LocatorStrategy]:
        return [self.primary, *self.fallbacks]


class RetryPolicy(BaseModel):
    max_attempts: int = 1
    backoff_ms: int = 500


class Step(BaseModel):
    """A single recorded action. value/locator may reference {{params.x}}."""

    step_id: int
    action: ActionType
    description: str
    locator: Locator | None = None
    value: str | None = None
    extract_as: str | None = None
    risk_level: RiskLevel | None = None
    timeout_ms: int = 5000
    retry: RetryPolicy = Field(default_factory=RetryPolicy)


class Param(BaseModel):
    """A typed input the calling agent supplies per invocation."""

    name: str
    type: Literal["string", "number", "boolean"]
    required: bool = True
    description: str
    example: str | None = None


class Output(BaseModel):
    """A typed value the capability returns to the calling agent."""

    name: str
    type: Literal["string", "number", "boolean", "object"]
    description: str
    source_step_id: int


class Checkpoint(BaseModel):
    """The condition that proves the goal was actually reached."""

    locator: Locator
    expected_text_contains: str | None = None
    description: str


class OutcomeDefinition(BaseModel):
    """A known, named business outcome this capability can legitimately hit.

    These are discovered during the LLM run, not inferred generically by
    replay -- only the domain run knows "no such member" is a valid answer.
    """

    name: str
    detector: Locator
    description: str
    expected_text_contains: str | None = None


class DiscoveryMeta(BaseModel):
    """Pointer back to the evidence of the run that produced this artifact."""

    model: str
    run_id: str
    step_count: int
    duration_ms: int
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CapabilityArtifact(BaseModel):
    """A typed, versioned, agent-invocable capability."""

    artifact_id: str
    name: str
    version: str = "1.0.0"
    description: str
    target_app: str
    surface_type: SurfaceType
    base_url: str
    status: Literal["draft", "approved"] = "draft"
    created_by: Literal["llm_discovery", "human_authored", "human_edited"] = "llm_discovery"
    allowlist_scope: list[str] = Field(default_factory=list)
    params: list[Param] = Field(default_factory=list)
    outputs: list[Output] = Field(default_factory=list)
    steps: list[Step]
    checkpoint: Checkpoint
    known_outcomes: list[OutcomeDefinition] = Field(default_factory=list)
    discovery_meta: DiscoveryMeta | None = None

    def param_names(self) -> set[str]:
        return {p.name for p in self.params}
