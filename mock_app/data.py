"""In-memory fixture data for the mock legacy credit-union app."""
from dataclasses import dataclass, field


@dataclass
class Account:
    account_number: str
    account_type: str
    balance: float


@dataclass
class Member:
    member_id: str
    first_name: str
    last_name: str
    accounts: list[Account] = field(default_factory=list)


# Special member IDs are deliberately reserved to deterministically trigger
# specific runtime outcomes, so replay error-handling is reproducible on demand.
MEMBERS: dict[str, Member] = {
    "10001": Member(
        member_id="10001",
        first_name="Jamie",
        last_name="Rivera",
        accounts=[
            Account("SAV-10001-01", "Savings", 4820.55),
            Account("CHK-10001-01", "Checking", 1203.10),
        ],
    ),
    "20002": Member(
        member_id="20002",
        first_name="Priya",
        last_name="Nair",
        accounts=[Account("SAV-20002-01", "Savings", 998.00)],
    ),
    # 40300 -> permission denied (simulates a restricted/frozen member record).
    "40300": Member(
        member_id="40300",
        first_name="Restricted",
        last_name="Record",
        accounts=[Account("SAV-40300-01", "Savings", 0.0)],
    ),
    # 50000 -> triggers an artificial slow load, to exercise wait/retry logic.
    "50000": Member(
        member_id="50000",
        first_name="Slow",
        last_name="Loader",
        accounts=[Account("SAV-50000-01", "Savings", 250.00)],
    ),
    # 60000 -> triggers an unexpected "fraud hold" interstitial on sub-account open.
    "60000": Member(
        member_id="60000",
        first_name="Fraud",
        last_name="Hold",
        accounts=[Account("SAV-60000-01", "Savings", 75.25)],
    ),
    # 70000 -> triggers a simulated hard server failure on sub-account open.
    "70000": Member(
        member_id="70000",
        first_name="Server",
        last_name="Error",
        accounts=[Account("SAV-70000-01", "Savings", 10.00)],
    ),
    # 90000 -> triggers a simulated session-expired interstitial mid-flow.
    "90000": Member(
        member_id="90000",
        first_name="Session",
        last_name="Expired",
        accounts=[Account("SAV-90000-01", "Savings", 42.00)],
    ),
}


def find_member(member_id: str) -> Member | None:
    return MEMBERS.get(member_id)


def create_sub_account(member_id: str, account_type: str, nickname: str, initial_deposit: float) -> Account:
    member = MEMBERS[member_id]
    seq = len(member.accounts) + 1
    account = Account(
        account_number=f"{account_type[:3].upper()}-{member_id}-{seq:02d}",
        account_type=account_type,
        balance=initial_deposit,
    )
    member.accounts.append(account)
    return account
