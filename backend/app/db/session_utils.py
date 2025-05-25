import contextlib
from sqlalchemy.orm import Session
from app.db.base import SessionLocal, engine
from sqlalchemy.exc import SQLAlchemyError
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
    try:
        # First try with the provided session
        return db.query(model_class).filter(model_class.id == obj_id).first()
    except SQLAlchemyError as e:
        logger.warning(f"Session error while getting object, creating new session: {e}")
        # If that fails, create a new session as a fallback
        temp_session = SessionLocal()
        try:
            return temp_session.query(model_class).filter(model_class.id == obj_id).first()
        finally:
            temp_session.close()

def refresh_session_object(obj, session=None):
    """Refresh a detached object with a new session if needed.
    
    Args:
        obj: The object to refresh
        session: Optional session to use (creates a new one if not provided)
    
    Returns:
        The refreshed object and the session used (to be closed by the caller)
    """
    if obj is None:
        return None, None
    
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True
    
    try:
        # Check if object is attached to this session
        if obj in session:
            # Already attached, just refresh
            session.refresh(obj)
            return obj, session
        else:
            # Get a fresh copy from the database
            new_obj = session.query(obj.__class__).get(obj.id)
            return new_obj, session
    except Exception as e:
        logger.error(f"Error refreshing object: {e}")
        if close_session:
            session.close()
        return None, None
