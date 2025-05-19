import contextlib
from sqlalchemy.orm import Session
from app.db.base import SessionLocal
import logging

logger = logging.getLogger(__name__)

@contextlib.contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations.
    
    Usage:
        with session_scope() as db:
            db_obj = db.query(Model).get(id)
            db_obj.property = new_value
            # No need to call commit - it's done automatically if no exceptions
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as e:
        logger.error(f"Session error, rolling back: {str(e)}")
        session.rollback()
        raise
    finally:
        session.close()

def get_refreshed_object(db: Session, model_class, obj_id: int):
    """Get a fresh copy of an object from the database.
    
    Useful for celery tasks that need to get a fresh instance of a model
    after it's been detached from a previous session.
    """
    return db.query(model_class).filter(model_class.id == obj_id).first()
