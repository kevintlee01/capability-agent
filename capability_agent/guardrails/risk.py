"""Classify actions as safe/reversible vs risky/irreversible: risky steps replay only on 'approved' artifacts unless --allow-risky is passed."""
from capability_agent.artifact.schema import ActionType, RiskLevel, Step

READ_ONLY_ACTIONS = {ActionType.NAVIGATE, ActionType.EXTRACT, ActionType.WAIT_FOR, ActionType.ASSERT_CHECKPOINT}

# Keywords found in a step's own description that mark it as irreversible.
RISKY_KEYWORDS = ("submit", "confirm", "open account", "delete", "transfer", "close account", "approve")


def classify_step_risk(step: Step) -> RiskLevel:
    """Best-effort default; an explicit step.risk_level always wins."""
    if step.action in READ_ONLY_ACTIONS:
        return RiskLevel.SAFE
    description_lower = step.description.lower()
    if any(keyword in description_lower for keyword in RISKY_KEYWORDS):
        return RiskLevel.RISKY
    return RiskLevel.SAFE


def requires_approval_to_replay(step: Step, artifact_status: str, allow_risky: bool) -> bool:
    risk = step.risk_level or classify_step_risk(step)
    if risk != RiskLevel.RISKY:
        return False
    return not (artifact_status == "approved" or allow_risky)
