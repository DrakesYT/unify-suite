"""FR-PRO-02 deterministic vendor ranking with a reason, FR-PRO-03 PO from an approved request."""

import os
import random
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.llm import LLMError
from app.llm.fake import FakeLLMClient
from app.models import User, Vendor, VendorQuote
from app.models.enums import Department, Role
from app.services.procurement import rank_vendors

API = "/api/procurement"
AuthHeader = Callable[[User], dict[str, str]]
# (name, unit price in cents, lead time days, on-time rate)
VENDORS = [
    ("Alpha Metals", 1000, 10, "0.90"),
    ("Beta Supply", 1200, 5, "0.98"),
    ("Gamma Traders", 900, 20, "0.70"),
]
REQUEST = {"item": "Steel brackets", "quantity": 100, "budget_minor": 110000, "currency": "USD"}
REASON = (
    "Beta Supply is recommended: fastest delivery at 5 days and a 98% on-time record outweigh its "
    "higher 1,200.00 USD total, which is over the budget."
)


def _offers() -> list[tuple[Vendor, VendorQuote]]:
    return [
        (
            Vendor(
                id=f"00000000-0000-0000-0000-00000000000{i}",
                name=n,
                lead_time_days=lead,
                on_time_rate=Decimal(rate),
            ),
            VendorQuote(unit_price_minor=price, currency="USD"),
        )
        for i, (n, price, lead, rate) in enumerate(VENDORS, start=1)
    ]


def test_ranking_is_deterministic_and_explained_by_its_numbers() -> None:
    ranking = rank_vendors(100, 110000, _offers())

    # Beta:  50%*0.75 + 25%*1.00 + 25%*0.98 = 0.870
    # Alpha: 50%*0.90 + 25%*0.50 + 25%*0.90 = 0.800
    # Gamma: 50%*1.00 + 25%*0.25 + 25%*0.70 = 0.7375 → 73.8
    assert [(r.vendor_name, r.score) for r in ranking] == [
        ("Beta Supply", Decimal("87.0")),
        ("Alpha Metals", Decimal("80.0")),
        ("Gamma Traders", Decimal("73.8")),
    ]
    assert [r.over_budget for r in ranking] == [True, False, False]
    assert ranking[0].total_minor == 120000

    shuffled = _offers()
    random.Random(7).shuffle(shuffled)
    assert rank_vendors(100, 110000, shuffled) == ranking


def test_ties_break_on_price_then_name() -> None:
    offers = [
        (
            Vendor(
                id=f"00000000-0000-0000-0000-00000000001{i}",
                name=n,
                lead_time_days=5,
                on_time_rate=Decimal("0.9"),
            ),
            VendorQuote(unit_price_minor=1000, currency="USD"),
        )
        for i, n in enumerate(["Zeta", "Eta"])
    ]
    assert [r.vendor_name for r in rank_vendors(10, 100000, offers)] == ["Eta", "Zeta"]


@pytest.fixture
def people(make_user: Callable[..., User], auth_header: AuthHeader) -> dict[str, dict[str, str]]:
    return {
        "buyer": auth_header(make_user(Role.employee, Department.procurement)),
        "manager": auth_header(make_user(Role.manager, Department.procurement)),
        "finance_manager": auth_header(make_user(Role.manager, Department.finance)),
    }


@pytest.fixture
def request_id(client: TestClient, people: dict[str, dict[str, str]]) -> str:
    h = people["buyer"]
    rid = client.post(f"{API}/requests", json=REQUEST, headers=h).json()["id"]
    for name, price, lead, rate in VENDORS:
        vid = client.post(
            f"{API}/vendors",
            json={"name": name, "lead_time_days": lead, "on_time_rate": rate},
            headers=h,
        ).json()["id"]
        res = client.post(
            f"{API}/requests/{rid}/quotes",
            json={"vendor_id": vid, "unit_price_minor": price},
            headers=h,
        )
        assert res.status_code == 201, res.text
    return rid


def _compare(client: TestClient, headers: dict[str, str], rid: str) -> Any:
    return client.post(f"{API}/compare-vendors", json={"request_id": rid}, headers=headers)


def test_compare_ranks_and_explains(
    client: TestClient, people: dict[str, dict[str, str]], request_id: str, fake_llm: FakeLLMClient
) -> None:
    fake_llm.replies.append({"reason": REASON})

    res = _compare(client, people["buyer"], request_id)

    assert res.status_code == 200, res.text
    body = res.json()
    assert [r["vendor_name"] for r in body["ranking"]] == [
        "Beta Supply",
        "Alpha Metals",
        "Gamma Traders",
    ]
    assert body["reason"] == REASON
    assert (
        "Beta Supply" in fake_llm.calls[0].user
    )  # the model is shown the ranking, not asked to make it
    stored = client.get(f"{API}/requests/{request_id}", headers=people["buyer"]).json()[
        "comparison"
    ]
    assert stored["ranking"][0]["vendor_name"] == "Beta Supply"

    fake_llm.replies.append({"reason": REASON})
    assert _compare(client, people["buyer"], request_id).json()["ranking"] == body["ranking"]


def test_reason_must_name_the_winner(
    client: TestClient, people: dict[str, dict[str, str]], request_id: str, fake_llm: FakeLLMClient
) -> None:
    fake_llm.replies += [
        {"reason": "Alpha Metals is the best balance of price and reliability for this."},
        {"reason": REASON},
    ]

    assert _compare(client, people["buyer"], request_id).json()["reason"] == REASON


def test_ranking_survives_a_model_outage(
    client: TestClient, people: dict[str, dict[str, str]], request_id: str, fake_llm: FakeLLMClient
) -> None:
    fake_llm.replies.append(LLMError("down", retryable=False))

    body = _compare(client, people["buyer"], request_id).json()

    assert body["reason"] is None and "vendor_comparator failed" in body["reason_error"]
    assert body["ranking"][0]["vendor_name"] == "Beta Supply"


def test_compare_needs_two_quotes(
    client: TestClient, people: dict[str, dict[str, str]], fake_llm: FakeLLMClient
) -> None:
    rid = client.post(f"{API}/requests", json=REQUEST, headers=people["buyer"]).json()["id"]

    assert _compare(client, people["buyer"], rid).json()["error"]["code"] == "not_enough_quotes"


def test_po_from_request_waits_for_manager_approval(
    client: TestClient, people: dict[str, dict[str, str]], request_id: str, fake_llm: FakeLLMClient
) -> None:
    fake_llm.replies.append({"reason": REASON})
    _compare(client, people["buyer"], request_id)
    order_url = f"{API}/requests/{request_id}/order"

    assert (
        client.post(order_url, json={}, headers=people["buyer"]).json()["error"]["code"]
        == "request_not_approved"
    )
    assert (
        client.post(f"{API}/requests/{request_id}/approve", headers=people["buyer"]).status_code
        == 403
    )
    approved = client.post(f"{API}/requests/{request_id}/approve", headers=people["manager"])
    assert approved.json()["status"] == "approved"

    res = client.post(order_url, json={}, headers=people["buyer"])

    assert res.status_code == 201, res.text
    order = res.json()["order"]
    assert (order["status"], order["amount_minor"]) == (
        "pending_approval",
        120000,
    )  # top-ranked: Beta
    assert (
        client.post(order_url, json={}, headers=people["buyer"]).json()["error"]["code"]
        == "order_pending"
    )
    approval_url = f"/api/approvals/{res.json()['approval_id']}"
    approval = client.get(approval_url, headers=people["manager"]).json()
    assert (approval["action"], approval["payload"]["over_budget"]) == ("approve_po", True)

    assert (
        client.post(
            f"{approval_url}/approve", json={}, headers=people["finance_manager"]
        ).status_code
        == 403
    )
    assert (
        client.post(f"{approval_url}/approve", json={}, headers=people["manager"]).status_code
        == 200
    )

    po = client.get(f"{API}/orders/{order['po_number']}", headers=people["buyer"]).json()
    assert po["status"] == "approved"
    assert (
        client.get(f"{API}/requests/{request_id}", headers=people["buyer"]).json()["status"]
        == "ordered"
    )


def test_rejected_po_keeps_the_request_approved(
    client: TestClient, people: dict[str, dict[str, str]], request_id: str, fake_llm: FakeLLMClient
) -> None:
    client.post(f"{API}/requests/{request_id}/approve", headers=people["manager"])
    alpha = next(
        v["id"]
        for v in client.get(f"{API}/vendors", headers=people["buyer"]).json()["items"]
        if v["name"] == "Alpha Metals"
    )
    res = client.post(
        f"{API}/requests/{request_id}/order", json={"vendor_id": alpha}, headers=people["buyer"]
    ).json()
    assert res["order"]["amount_minor"] == 100000

    client.post(
        f"/api/approvals/{res['approval_id']}/reject",
        json={"comment": "Use Beta"},
        headers=people["manager"],
    )

    assert (
        client.get(f"{API}/orders/{res['order']['po_number']}", headers=people["buyer"]).json()[
            "status"
        ]
        == "rejected"
    )
    assert (
        client.get(f"{API}/requests/{request_id}", headers=people["buyer"]).json()["status"]
        == "approved"
    )


def test_manager_cannot_approve_own_request(
    client: TestClient, make_user: Callable[..., User], auth_header: AuthHeader
) -> None:
    manager = auth_header(make_user(Role.manager, Department.procurement))
    rid = client.post(f"{API}/requests", json=REQUEST, headers=manager).json()["id"]

    assert (
        client.post(f"{API}/requests/{rid}/approve", headers=manager).json()["error"]["code"]
        == "self_approval"
    )


def test_direct_po_also_needs_approval(
    client: TestClient, people: dict[str, dict[str, str]], db: Session
) -> None:
    vid = client.post(
        f"{API}/vendors",
        json={"name": "Solo Vendor", "lead_time_days": 3, "on_time_rate": "0.9"},
        headers=people["buyer"],
    ).json()["id"]

    res = client.post(
        f"{API}/orders",
        json={"po_number": "PO-7001", "vendor_id": vid, "amount_minor": 5000, "currency": "USD"},
        headers=people["buyer"],
    )

    assert res.status_code == 201
    assert res.json()["order"]["status"] == "pending_approval" and res.json()["approval_id"]


@pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_LLM"), reason="set RUN_LIVE_LLM=1 and LIVE_LLM_API_KEY"
)
def test_live_vultr_reason_names_the_winner() -> None:
    from app.agents.vendor_comparator import VendorComparator
    from app.config import get_settings
    from app.llm.vultr import VultrLLMClient
    from app.models import PurchaseRequest
    from app.services.procurement import _facts

    settings = get_settings()
    llm = VultrLLMClient(
        base_url=settings.llm_base_url,
        api_key=os.environ["LIVE_LLM_API_KEY"],
        model=settings.llm_model,
    )
    request = PurchaseRequest(
        item="Steel brackets", quantity=100, budget_minor=110000, currency="USD"
    )

    reply = VendorComparator().run(_facts(request, rank_vendors(100, 110000, _offers())), llm)

    assert "beta supply" in reply.reason.lower()
