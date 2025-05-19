"""
Script to create an admin user in the database.
"""
import os
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from app.db.base import engine
from app.models.user import User
from app.core.security import get_password_hash

# Load environment variables
load_dotenv()

# Default admin user settings
DEFAULT_ADMIN_EMAIL = "admin@example.com"
DEFAULT_ADMIN_PASSWORD = "adminpassword"

def create_admin_user(db: Session):
    """Create an admin user if it doesn't exist."""
    
    # Check if admin user already exists
    admin_user = db.query(User).filter(User.email == DEFAULT_ADMIN_EMAIL).first()
    
    if admin_user:
        print(f"Admin user with email '{DEFAULT_ADMIN_EMAIL}' already exists.")
        return admin_user
    
    # Create new admin user
    new_admin = User(
        email=DEFAULT_ADMIN_EMAIL,
        hashed_password=get_password_hash(DEFAULT_ADMIN_PASSWORD),
        full_name="System Admin",
        is_active=True,
        is_superuser=True,
        role="admin"
    )
    
    db.add(new_admin)
    db.commit()
    db.refresh(new_admin)
    
    print(f"Admin user created with email: {DEFAULT_ADMIN_EMAIL}")
    print("Password: adminpassword")
    print("Please change this password after first login!")
    
    return new_admin

def main():
    """Main function to create admin user."""
    with Session(engine) as db:
        create_admin_user(db)

if __name__ == "__main__":
    main()
