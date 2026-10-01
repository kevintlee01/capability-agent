"""Hand-author 'open_sub_account' to exercise risky-step blocking, interstitial dismissal, validation business outcomes, and a hard failure."""
from capability_agent.artifact.schema import (
    ActionType, CapabilityArtifact, Checkpoint, InterstitialHandler, Locator,
    LocatorKind, LocatorStrategy, OutcomeDefinition, Param, Step, SurfaceType,
)
from capability_agent.artifact.store import save_artifact

account_type_field = Locator(primary=LocatorStrategy(kind=LocatorKind.CSS, value="select[name=account_type]"))
nickname_field = Locator(primary=LocatorStrategy(kind=LocatorKind.CSS, value="input[name=nickname]"))
deposit_field = Locator(primary=LocatorStrategy(kind=LocatorKind.CSS, value="input[name=initial_deposit]"))
open_account_button = Locator(
    primary=LocatorStrategy(kind=LocatorKind.ROLE, value="Open Account", role="button"),
    fallbacks=[LocatorStrategy(kind=LocatorKind.TEXT, value="Open Account")],
)

artifact = CapabilityArtifact(
    artifact_id="open_sub_account-handauthored",
    name="open_sub_account",
    version="1.0.0",
    description="Open a new sub-account for a member and reach the confirmation screen",
    target_app="meridian-credit-union-mock",
    surface_type=SurfaceType.LEGACY_WEB,
    base_url="http://127.0.0.1:8731",
    status="draft",
    created_by="human_authored",
    allowlist_scope=["/member/*/open-subaccount*"],
    params=[
        Param(name="member_id", type="string", description="Member ID to open the sub-account for", example="20002"),
        Param(name="account_type", type="string", description="Savings or Checking", example="Savings"),
        Param(name="nickname", type="string", description="Nickname for the new sub-account", example="Rainy Day"),
        Param(name="initial_deposit", type="string", description="Initial deposit amount", example="50"),
    ],
    outputs=[],
    steps=[
        Step(step_id=1, action=ActionType.NAVIGATE, description="go to the open sub-account form", value="/member/{{params.member_id}}/open-subaccount"),
        Step(step_id=2, action=ActionType.SELECT_OPTION, description="choose the account type", locator=account_type_field, value="{{params.account_type}}"),
        Step(step_id=3, action=ActionType.FILL, description="fill the nickname", locator=nickname_field, value="{{params.nickname}}"),
        Step(step_id=4, action=ActionType.FILL, description="fill the initial deposit", locator=deposit_field, value="{{params.initial_deposit}}"),
        Step(step_id=5, action=ActionType.CLICK, description="click Open Account to open the sub-account", locator=open_account_button),
    ],
    checkpoint=Checkpoint(
        locator=Locator(primary=LocatorStrategy(kind=LocatorKind.ROLE, value="Sub-Account Opened", role="heading")),
        description="Sub-Account Opened heading is visible",
    ),
    known_outcomes=[
        OutcomeDefinition(
            name="validation_error_nickname",
            detector=Locator(primary=LocatorStrategy(kind=LocatorKind.TEXT, value="Nickname is required")),
            description="The nickname field was left blank.",
        ),
        OutcomeDefinition(
            name="validation_error_deposit",
            detector=Locator(primary=LocatorStrategy(kind=LocatorKind.TEXT, value="greater than zero")),
            description="The initial deposit was zero or negative.",
        ),
    ],
    interstitials=[
        InterstitialHandler(
            name="fraud_review_hold",
            detector=Locator(primary=LocatorStrategy(kind=LocatorKind.ROLE, value="Fraud Review Hold", role="heading")),
            dismiss_action=Locator(primary=LocatorStrategy(kind=LocatorKind.ROLE, value="Proceed Anyway", role="button")),
            description="Member is flagged for manual fraud review; proceeding anyway is the recorded recovery.",
        ),
    ],
)

path = save_artifact(artifact)
print(f"saved to {path}")
