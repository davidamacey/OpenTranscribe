"""
Script to create the default admin user.

This script initializes the database with a default admin user
if one doesn't already exist.
"""

import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add the parent directory to the path so we can import from app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings
from app.core.security import get_password_hash
from app.models.user import User


def create_admin_user():
    """
    Create the default admin user if it doesn't exist.

    Returns:
        None

    Raises:
        Exception: If there's an error creating the admin user
    """
    # Create database engine and session
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    try:
        # Check if admin already exists
        admin_email = "admin@example.com"
        existing_admin = db.query(User).filter(User.email == admin_email).first()

        if existing_admin:
            print(f"Admin user with email {admin_email} already exists.")
            return

        # Create admin user
        admin_user = User(
            email=admin_email,
            full_name="Admin User",
            hashed_password=get_password_hash("admin"),
            is_active=True,
            is_superuser=True,
            role="admin",
        )

        db.add(admin_user)
        db.commit()
        print(f"Admin user created with email: {admin_email} and password: admin")

    except Exception as e:
        print(f"Error creating admin user: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    create_admin_user()
