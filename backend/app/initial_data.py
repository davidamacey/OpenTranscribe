"""
Initial data setup script for the transcribe app.
Creates a test user and sets up initial database values.
"""
import logging
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.user import User
from app.core.security import get_password_hash
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_db(db: Session) -> None:
    """
    Initialize database with a test user
    """
    # Create test user if it doesn't exist
    user = db.query(User).filter(User.email == "admin@example.com").first()
    if not user:
        user = User(
            email="admin@example.com",
            full_name="Admin User",
            hashed_password=get_password_hash("password"),
            is_superuser=True,
            role="admin",
        )
        db.add(user)
        db.commit()
        logger.info("Created test admin user: admin@example.com / password")
    else:
        logger.info("Test admin user already exists")


def main() -> None:
    """
    Run the init DB function
    """
    logger.info("Creating initial data")
    db = next(get_db())
    init_db(db)
    logger.info("Initial data created")


if __name__ == "__main__":
    main()
