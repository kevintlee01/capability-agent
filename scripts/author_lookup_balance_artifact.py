"""One-off script: hand-author a 'lookup_balance' artifact to prove the
replay engine (locators, params, checkpoint, known business outcomes) works
end to end against the live mock app, independent of the LLM discovery path.
This is NOT the required real discovery-run evidence -- see README for that.
"""
from capability_agent.artifact.schema import (
    ActionType, CapabilityArtifact, Checkpoint, Locator, LocatorKind,
    LocatorStrategy, Output, OutcomeDefinition, Param, Step, SurfaceType,
)
from capability_agent.artifact.store import save_artifact

member_id_field = Locator(primary=LocatorStrategy(kind=LocatorKind.CSS, value="input[name=member_id]"))
search_button = Locator(
    primary=LocatorStrategy(kind=LocatorKind.ROLE, value="Search", role="button"),
    fallbacks=[LocatorStrategy(kind=LocatorKind.TEXT, value="Search")],
)
balance_cell = Locator(primary=LocatorStrategy(kind=LocatorKind.CSS, value='table[border="1"]'))
balance_cell.primary.value = 'table[border="1"] >> nth=1'

artifact = CapabilityArtifact(
    artifact_id="lookup_balance-handauthored",
    name="lookup_balance",
    version="1.0.0",
    description="Look up a member by ID and read their first account's balance",
    target_app="meridian-credit-union-mock",
    surface_type=SurfaceType.LEGACY_WEB,
    base_url="http://127.0.0.1:8731",
    status="approved",
    created_by="human_authored",
    allowlist_scope=["/", "/member/*"],
    params=[Param(name="member_id", type="string", description="Member ID to look up", example="10001")],
    outputs=[Output(name="balance", type="string", description="First account's balance", source_step_id=4)],
    steps=[
        Step(step_id=1, action=ActionType.NAVIGATE, description="go to search page", value="/"),
        Step(step_id=2, action=ActionType.FILL, description="fill member id", locator=member_id_field, value="{{params.member_id}}"),
        Step(step_id=3, action=ActionType.CLICK, description="click submit to search", locator=search_button, risk_level="safe"),
        Step(
            step_id=4, action=ActionType.EXTRACT, description="extract first account balance", extract_as="balance",
            locator=Locator(primary=LocatorStrategy(kind=LocatorKind.CSS, value='table[border="1"] >> nth=1 >> tr >> nth=1 >> td >> nth=2')),
        ),
    ],
    checkpoint=Checkpoint(
        locator=Locator(primary=LocatorStrategy(kind=LocatorKind.ROLE, value="Member Detail", role="heading")),
        description="Member Detail heading is visible",
    ),
    known_outcomes=[
        OutcomeDefinition(
            name="member_not_found",
            detector=Locator(primary=LocatorStrategy(kind=LocatorKind.TEXT, value="No member found")),
            description="No member record exists for the given ID.",
        ),
        OutcomeDefinition(
            name="permission_denied",
            detector=Locator(primary=LocatorStrategy(kind=LocatorKind.ROLE, value="Access Denied", role="heading")),
            description="The teller session lacks permission to view this record.",
        ),
        OutcomeDefinition(
            name="session_expired",
            detector=Locator(primary=LocatorStrategy(kind=LocatorKind.ROLE, value="Session Expired", role="heading")),
            description="The teller session timed out mid-flow.",
        ),
    ],
)

path = save_artifact(artifact)
print(f"saved to {path}")
