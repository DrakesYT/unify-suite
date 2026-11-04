"""Who may read or change which department's data. Plain rules — the LLM never decides this."""

from app.models import User
from app.models.enums import Department, Role


def can_access(user: User, department: Department, *, write: bool) -> bool:
    """
    admin      everything
    executive  read every department, change nothing
    manager    own department fully, other departments read-only
    employee   own department only
    """
    if user.role == Role.admin:
        return True
    if user.role == Role.executive:
        return not write
    if user.department == department:
        return True
    return user.role == Role.manager and not write
