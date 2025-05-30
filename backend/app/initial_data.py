"""
Initial data setup script for the transcribe app.
Creates a test user and sets up initial database values.
"""
import logging
from typing import List
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.user import User
from app.models.media import Tag
from app.core.security import get_password_hash
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_db(db: Session) -> None:
    """
    Initialize database with a test user and default tags
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
    
    # Create default tags if they don't exist
    default_tags = ['Important', 'Meeting', 'Interview', 'Personal']
    
    for tag_name in default_tags:
        tag = db.query(Tag).filter(Tag.name == tag_name).first()
        if not tag:
            tag = Tag(name=tag_name)
            db.add(tag)
            logger.info(f"Created default tag: {tag_name}")
    
    db.commit()


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
