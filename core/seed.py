import logging
import os

from core.db import SessionLocal
from core.models import ROLE_ADMIN, User
from core.security import hash_password

logger = logging.getLogger("startup")


def seed_admin_user():
    """Create the first admin account from ADMIN_EMAIL/ADMIN_PASSWORD env vars, if configured and not already present."""
    admin_email = os.getenv("ADMIN_EMAIL")
    admin_password = os.getenv("ADMIN_PASSWORD")

    if not admin_email or not admin_password:
        logger.info("ADMIN_EMAIL/ADMIN_PASSWORD not set - skipping admin seed.")
        return

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == admin_email.lower()).first()
        if existing:
            logger.info(f"Admin user already exists: {admin_email}")
            return

        admin = User(
            email=admin_email.lower(),
            hashed_password=hash_password(admin_password),
            full_name="Administrator",
            role=ROLE_ADMIN,
        )
        db.add(admin)
        db.commit()
        logger.info(f"Seeded admin user: {admin_email}")
    finally:
        db.close()
