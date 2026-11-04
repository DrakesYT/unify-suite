"""Admin commands run inside the backend container.

    python -m app.cli create-user EMAIL "Full Name" ROLE DEPARTMENT

The password is asked for interactively, so it never appears in shell history or logs.
"""

import argparse
import getpass
import sys

from pydantic import ValidationError

from app.db import session_factory
from app.errors import ApiError
from app.models.enums import Department, Role
from app.schemas.auth import UserCreate
from app.services.users import create_user


def _create_user(args: argparse.Namespace) -> int:
    password = getpass.getpass("Password: ")
    if getpass.getpass("Repeat password: ") != password:
        print("Passwords do not match.", file=sys.stderr)
        return 1
    try:
        data = UserCreate(
            email=args.email,
            full_name=args.full_name,
            role=args.role,
            department=args.department,
            password=password,
        )
        with session_factory()() as db:
            user = create_user(db, data)
    except ValidationError as exc:
        print(exc.errors()[0]["loc"][0], exc.errors()[0]["msg"], file=sys.stderr)
        return 1
    except ApiError as exc:
        print(exc.message, file=sys.stderr)
        return 1
    print(f"Created {user.email} ({user.role}, {user.department})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-user", help="add a user who can sign in")
    create.add_argument("email")
    create.add_argument("full_name")
    create.add_argument("role", choices=[r.value for r in Role])
    create.add_argument("department", choices=[d.value for d in Department])
    args = parser.parse_args(argv)
    return _create_user(args)


if __name__ == "__main__":
    raise SystemExit(main())
