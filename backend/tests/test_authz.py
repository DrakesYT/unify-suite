"""FR-AUTH-02: each user has one role and one department, and endpoints enforce both."""

from collections.abc import Callable, Iterator

import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient

from app.deps import require_department, require_roles
from app.main import create_app
from app.models import User
from app.models.enums import Department, Role
from app.services.authz import can_access

MakeUser = Callable[..., User]
AuthHeader = Callable[[User], dict[str, str]]


@pytest.fixture
def guarded_client(client: TestClient) -> Iterator[TestClient]:
    """An app with a finance router guarded exactly the way department routers are."""
    finance = APIRouter(
        prefix="/api/finance", dependencies=[Depends(require_department(Department.finance))]
    )
    finance.add_api_route("/invoices", lambda: {"ok": True}, methods=["GET", "POST"])
    admin_only = APIRouter(dependencies=[Depends(require_roles(Role.admin))])
    admin_only.add_api_route("/api/admin/ping", lambda: {"ok": True}, methods=["GET"])

    app = create_app()
    app.include_router(finance)
    app.include_router(admin_only)
    app.dependency_overrides.update(client.app.dependency_overrides)  # type: ignore[attr-defined]
    with TestClient(app) as test_client:
        yield test_client


def test_sales_employee_gets_403_on_finance(
    guarded_client: TestClient, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    user = make_user(Role.employee, Department.sales)

    res = guarded_client.get("/api/finance/invoices", headers=auth_header(user))

    assert res.status_code == 403
    assert res.json() == {"error": {"code": "forbidden", "message": "No access to finance data"}}


def test_finance_employee_can_read_and_write_finance(
    guarded_client: TestClient, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    headers = auth_header(make_user(Role.employee, Department.finance))

    assert guarded_client.get("/api/finance/invoices", headers=headers).status_code == 200
    assert guarded_client.post("/api/finance/invoices", headers=headers).status_code == 200


@pytest.mark.parametrize(
    ("role", "department", "read", "write"),
    [
        (Role.manager, Department.sales, 200, 403),
        (Role.manager, Department.finance, 200, 200),
        (Role.executive, Department.sales, 200, 403),
        (Role.admin, Department.hr, 200, 200),
    ],
)
def test_cross_department_rules(
    guarded_client: TestClient,
    make_user: MakeUser,
    auth_header: AuthHeader,
    role: Role,
    department: Department,
    read: int,
    write: int,
) -> None:
    headers = auth_header(make_user(role, department))

    assert guarded_client.get("/api/finance/invoices", headers=headers).status_code == read
    assert guarded_client.post("/api/finance/invoices", headers=headers).status_code == write


def test_guard_requires_a_token(guarded_client: TestClient) -> None:
    assert guarded_client.get("/api/finance/invoices").status_code == 401


def test_role_guard(
    guarded_client: TestClient, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    manager = make_user(Role.manager, Department.finance)
    admin = make_user(Role.admin, Department.finance)

    assert guarded_client.get("/api/admin/ping", headers=auth_header(manager)).status_code == 403
    assert guarded_client.get("/api/admin/ping", headers=auth_header(admin)).status_code == 200


def test_can_access_matrix() -> None:
    def user(role: Role, department: Department) -> User:
        return User(role=role, department=department)

    sales = Department.sales
    finance = Department.finance
    assert can_access(user(Role.employee, sales), sales, write=True)
    assert not can_access(user(Role.employee, sales), finance, write=False)
    assert can_access(user(Role.manager, sales), finance, write=False)
    assert not can_access(user(Role.manager, sales), finance, write=True)
    assert not can_access(user(Role.executive, finance), finance, write=True)
    assert can_access(user(Role.admin, sales), finance, write=True)
