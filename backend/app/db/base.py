from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# Create SQLAlchemy engine with connection pool settings
# Backend (FastAPI) handles concurrent API requests — needs larger pool.
# Celery workers each fork their own process with a separate engine, so
# pool_size here mainly affects the backend web server.
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,  # Verify connections before using them
    pool_recycle=3600,  # Recycle connections after 1 hour
    pool_size=10,  # Connections to maintain (handles concurrent API requests)
    max_overflow=20,  # Burst connections beyond pool_size
)

# Create sessionmaker
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create base class for models
Base = declarative_base()


# Dependency for database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
