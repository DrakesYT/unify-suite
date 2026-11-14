"""Human approvals (FR-APR-01). Who may decide is plain role + department code."""

import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import ApprovalRequest, User
from app.models.base import utcnow
from app.models.enums import ApprovalStatus, Department, Role
from app.services import audit
from app.services.pagination import paginate


def create_approval(
    db: Session,
    *,
    action: str,
    payload: dict[str, Any],
    required_role: Role,
    department: Department,
    requested_by_id: uuid.UUID | None,
    execution_id: uuid.UUID | None = None,
    step_id: uuid.UUID | None = None,
) -> ApprovalRequest:
    approval = ApprovalRequest(
        action=action,
        payload=payload,
        required_role=required_role,
        department=department,
        requested_by_id=requested_by_id,
        execution_id=execution_id,
        step_id=step_id,
    )
    db.add(approval)
    db.flush()
    audit.record(
        db,
        action="approval.requested",
        entity="approval_request",
        entity_id=approval.id,
        actor_id=requested_by_id,
        detail={"action": action, "department": department},
    )
    return approval


def can_decide(user: User, approval: ApprovalRequest) -> bool:
    if user.role == Role.admin:
        return True
    return user.role == approval.required_role and user.department == approval.department


def _visible_to(user: User):  # type: ignore[no-untyped-def]
    if user.role in (Role.admin, Role.executive):
        return None
    if user.role == Role.manager:
        return or_(
            ApprovalRequest.department == user.department,
            ApprovalRequest.requested_by_id == user.id,
        )
    return ApprovalRequest.requested_by_id == user.id


def list_approvals(
    db: Session, user: User, limit: int, cursor: str | None, status: ApprovalStatus | None
) -> tuple[list[ApprovalRequest], str | None]:
    stmt = select(ApprovalRequest)
    visible = _visible_to(user)
    if visible is not None:
        stmt = stmt.where(visible)
    if status:
        stmt = stmt.where(ApprovalRequest.status == status)
    return paginate(db, stmt, ApprovalRequest, limit, cursor)


def get_approval(db: Session, user: User, approval_id: uuid.UUID) -> ApprovalRequest:
    approval = db.get(ApprovalRequest, approval_id)
    visible = _visible_to(user)
    if approval is None or (
        visible is not None
        and db.scalar(select(ApprovalRequest.id).where(ApprovalRequest.id == approval_id, visible))
        is None
    ):
        raise ApiError(404, "not_found", "Approval request not found")
    return approval


def decide(
    db: Session, user: User, approval_id: uuid.UUID, *, approve: bool, comment: str | None
) -> ApprovalRequest:
    """Record the decision. The caller resumes any paused workflow afterwards."""
    approval = db.get(ApprovalRequest, approval_id, with_for_update=True)
    if approval is None:
        raise ApiError(404, "not_found", "Approval request not found")
    if not can_decide(user, approval):
        raise ApiError(
            403,
            "forbidden",
            f"Only a {approval.department} {approval.required_role} can decide this",
        )
    if approval.requested_by_id == user.id:
        raise ApiError(403, "self_approval", "You cannot approve or reject your own request")
    if approval.status != ApprovalStatus.pending:
        raise ApiError(409, "already_decided", f"This request was already {approval.status}")
    if not approve and not (comment or "").strip():
        raise ApiError(422, "comment_required", "Say why when you reject")

    approval.status = ApprovalStatus.approved if approve else ApprovalStatus.rejected
    approval.decided_by_id = user.id
    approval.decided_at = utcnow()
    approval.comment = (comment or "").strip() or None
    audit.record(
        db,
        action=f"approval.{approval.status}",
        entity="approval_request",
        entity_id=approval.id,
        actor_id=user.id,
        detail={"action": approval.action, "comment": approval.comment}
        # An admin deciding for a department is an override: say so where auditors look.
        | ({"admin_override": True} if user.role == Role.admin else {}),
    )
    db.commit()
    return approval
