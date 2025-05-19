"""
Script to create an admin user in the database directly using SQL.
"""
import os
import psycopg2
from dotenv import load_dotenv
from passlib.context import CryptContext

# Load environment variables
load_dotenv()

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Database connection parameters
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
DB_HOST = os.getenv("POSTGRES_SERVER", "postgres")  # Using service name from docker-compose
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "transcribe_app")

# Default admin user settings
DEFAULT_ADMIN_EMAIL = "admin@example.com"
DEFAULT_ADMIN_PASSWORD = "admin"
DEFAULT_ADMIN_NAME = "Admin"

def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)

def create_admin_user():
    """Create an admin user directly using SQL."""
    
    # Connect to the database
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    
    # Create a cursor
    cursor = conn.cursor()
    
    try:
        # Check if the admin user already exists
        cursor.execute("SELECT id FROM \"user\" WHERE email = %s", (DEFAULT_ADMIN_EMAIL,))
        user = cursor.fetchone()
        
        if user:
            print(f"Admin user with email '{DEFAULT_ADMIN_EMAIL}' already exists.")
            return
        
        # Get the hashed password
        hashed_password = get_password_hash(DEFAULT_ADMIN_PASSWORD)
        
        # Insert the admin user
        cursor.execute(
            """
            INSERT INTO \"user\" (
                email, 
                hashed_password, 
                full_name, 
                is_active, 
                is_superuser,
                role,
                created_at,
                updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW()) RETURNING id
            """,
            (
                DEFAULT_ADMIN_EMAIL,
                hashed_password,
                DEFAULT_ADMIN_NAME,
                True,
                True,
                "admin"
            )
        )
        
        # Commit the transaction
        conn.commit()
        
        print(f"Admin user created with email: {DEFAULT_ADMIN_EMAIL}")
        print(f"Password: {DEFAULT_ADMIN_PASSWORD}")
        print("Please change this password after first login!")
    
    except Exception as e:
        # Rollback in case of an error
        conn.rollback()
        print(f"Error creating admin user: {e}")
    
    finally:
        # Close the cursor and connection
        cursor.close()
        conn.close()

if __name__ == "__main__":
    create_admin_user()
