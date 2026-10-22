"""Create an administrator account or promote an existing account.

    python -m scripts.create_admin --username admin
    python -m scripts.create_admin --username admin --password-env ADMIN_PASSWORD

The password is read from a hidden prompt or an environment variable, never from the
command line.
"""

import argparse
import getpass
import os
import sys

from app.db.session import get_sessionmaker
from app.services.user_service import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    USERNAME_PATTERN,
    UsernameTakenError,
    create_user,
    find_user,
    set_password,
)

ADMIN_MIN_PASSWORD_LENGTH = max(MIN_PASSWORD_LENGTH, 12)


def _read_password(env_name: str | None) -> str:
    if env_name:
        password = os.environ.get(env_name, "")
        if not password:
            raise SystemExit(f"Environment variable {env_name} is empty")
        return password
    password = getpass.getpass("New admin password: ")
    if password != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords do not match")
    return password


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password-env", help="read the password from this environment variable")
    parser.add_argument("--keep-password", action="store_true",
                        help="promote an existing account without changing its password")
    args = parser.parse_args(argv)

    if not USERNAME_PATTERN.match(args.username):
        raise SystemExit("Username must be 3-32 letters, digits, '.', '_' or '-'")

    with get_sessionmaker()() as db:
        user = find_user(db, args.username)
        if user is not None and args.keep_password:
            user.role = "admin"
            db.commit()
            print(f"Promoted '{user.username}' to admin.")
            return 0

        password = _read_password(args.password_env)
        if not ADMIN_MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
            raise SystemExit(f"Admin passwords must be {ADMIN_MIN_PASSWORD_LENGTH}-{MAX_PASSWORD_LENGTH} characters")

        if user is None:
            try:
                user = create_user(db, args.username, password, role="admin")
            except UsernameTakenError:
                raise SystemExit("That username was just taken; run the command again") from None
            print(f"Created admin '{user.username}'.")
        else:
            user.role = "admin"
            set_password(user, password)
            db.commit()
            print(f"Updated '{user.username}': role admin, new password, existing sign-ins revoked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
