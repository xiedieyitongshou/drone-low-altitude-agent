import os
import sys
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import load_environment
from app.db.base import Base
from app.db.models import User
from app.db.session import SessionLocal, engine
from app.services.auth_service import hash_password


def main() -> None:
    load_environment()
    username = os.getenv("INITIAL_ADMIN_USERNAME", "admin").strip()
    password = os.getenv("INITIAL_ADMIN_PASSWORD", "").strip()

    if not username:
        raise SystemExit("INITIAL_ADMIN_USERNAME cannot be blank")
    if len(password) < 8:
        raise SystemExit("INITIAL_ADMIN_PASSWORD must be at least 8 characters")

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        existing_user = db.scalar(select(User).where(User.username == username))
        if existing_user is not None:
            existing_user.role = "admin"
            existing_user.is_active = True
            db.commit()
            print(f"Promoted existing user '{username}' to active admin")
            return

        admin = User(
            username=username,
            password_hash=hash_password(password),
            display_name=username,
            role="admin",
            is_active=True,
        )
        db.add(admin)
        db.commit()
        print(f"Created initial admin '{username}'")


if __name__ == "__main__":
    main()
