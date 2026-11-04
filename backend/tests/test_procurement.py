"""FR-PRO-01: maintain vendors and purchase requests (CRUD returns the same fields)."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User
from app.models.enums import Department, Role
from app.schemas.procurement import PurchaseOrderCreate, VendorCreate
from app.services import procurement

API = "/api/procurement"
VENDOR = {
    "name": "ACME Industrial",
    "contact": "ap@acme.example.com",
    "lead_time_days": 7,
    "on_time_rate": "0.9500",
}


@pytest.fixture
def headers(
    make_user: Callable[..., User], auth_header: Callable[[User], dict[str, str]]
) -> dict[str, str]:
    return auth_header(make_user(Role.employee, Department.procurement))


def test_vendor_crud(client: TestClient, headers: dict[str, str]) -> None:
    created = client.post(f"{API}/vendors", json=VENDOR, headers=headers)
    assert created.status_code == 201
    vendor = created.json()
    assert {k: vendor[k] for k in VENDOR} == VENDOR

    assert client.get(f"{API}/vendors/{vendor['id']}", headers=headers).json() == vendor
    assert client.get(f"{API}/vendors", headers=headers).json()["items"] == [vendor]

    patched = client.patch(
        f"{API}/vendors/{vendor['id']}", json={"lead_time_days": 3}, headers=headers
    )
    assert patched.status_code == 200
    assert patched.json() == vendor | {"lead_time_days": 3}


def test_vendor_names_are_unique_ignoring_case(client: TestClient, headers: dict[str, str]) -> None:
    client.post(f"{API}/vendors", json=VENDOR, headers=headers)

    res = client.post(f"{API}/vendors", json=VENDOR | {"name": "acme INDUSTRIAL"}, headers=headers)

    assert res.status_code == 409
    assert res.json()["error"]["code"] == "vendor_exists"


@pytest.mark.parametrize(
    "bad",
    [{"on_time_rate": "1.5"}, {"lead_time_days": -1}, {"name": ""}, {"on_time_rate": "0.12345"}],
)
def test_vendor_input_is_validated(client: TestClient, headers: dict[str, str], bad: dict) -> None:  # type: ignore[type-arg]
    res = client.post(f"{API}/vendors", json=VENDOR | bad, headers=headers)

    assert res.status_code == 422
    assert res.json()["error"]["code"] == "validation_error"


def test_purchase_request_crud(client: TestClient, headers: dict[str, str]) -> None:
    vendor_id = client.post(f"{API}/vendors", json=VENDOR, headers=headers).json()["id"]
    body = {
        "item": "Steel brackets",
        "quantity": 400,
        "budget_minor": 425000,
        "currency": "usd",
        "chosen_vendor_id": vendor_id,
    }

    created = client.post(f"{API}/requests", json=body, headers=headers)
    assert created.status_code == 201
    request = created.json()
    assert {k: request[k] for k in body} == body | {"currency": "USD"}
    assert request["status"] == "pending"

    assert client.get(f"{API}/requests/{request['id']}", headers=headers).json() == request
    assert client.get(f"{API}/requests?status=pending", headers=headers).json()["items"] == [
        request
    ]
    assert client.get(f"{API}/requests?status=approved", headers=headers).json()["items"] == []

    patched = client.patch(
        f"{API}/requests/{request['id']}", json={"quantity": 500}, headers=headers
    )
    assert patched.json()["quantity"] == 500


def test_request_with_unknown_vendor_is_404(client: TestClient, headers: dict[str, str]) -> None:
    body = {
        "item": "x",
        "quantity": 1,
        "budget_minor": 1,
        "currency": "USD",
        "chosen_vendor_id": "00000000-0000-0000-0000-000000000000",
    }

    assert client.post(f"{API}/requests", json=body, headers=headers).status_code == 404


def test_cursor_pagination_walks_every_row_once(
    client: TestClient, headers: dict[str, str]
) -> None:
    for i in range(5):
        client.post(f"{API}/vendors", json=VENDOR | {"name": f"Vendor {i}"}, headers=headers)

    seen, cursor = [], None
    while True:
        page = client.get(
            f"{API}/vendors",
            params={"limit": 2, **({"cursor": cursor} if cursor else {})},
            headers=headers,
        ).json()
        seen += [v["name"] for v in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert sorted(seen) == [f"Vendor {i}" for i in range(5)]
    assert seen[0] == "Vendor 4"  # newest first

    bad = client.get(f"{API}/vendors", params={"cursor": "garbage"}, headers=headers)
    assert bad.json()["error"]["code"] == "invalid_cursor"


def test_orders_can_be_listed_and_found_by_number(
    client: TestClient, headers: dict[str, str], db: Session, make_user: Callable[..., User]
) -> None:
    vendor = procurement.create_vendor(db, VendorCreate(**VENDOR), make_user(Role.admin))
    procurement.create_order(
        db,
        PurchaseOrderCreate(
            po_number="PO-1007", vendor_id=vendor.id, amount_minor=425000, currency="USD"
        ),
    )

    [order] = client.get(f"{API}/orders", headers=headers).json()["items"]
    assert order["status"] == "pending_approval"
    assert client.get(f"{API}/orders/PO-1007", headers=headers).json() == order
    assert client.get(f"{API}/orders/PO-9999", headers=headers).status_code == 404


def test_other_departments_cannot_change_procurement(
    client: TestClient,
    make_user: Callable[..., User],
    auth_header: Callable[[User], dict[str, str]],
) -> None:
    sales = auth_header(make_user(Role.employee, Department.sales))
    finance_manager = auth_header(make_user(Role.manager, Department.finance))

    assert client.get(f"{API}/vendors", headers=sales).status_code == 403
    assert client.get(f"{API}/vendors", headers=finance_manager).status_code == 200
    assert client.post(f"{API}/vendors", json=VENDOR, headers=finance_manager).status_code == 403
