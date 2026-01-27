"""Service for persisting search settings to the database."""
import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# DB keys
_KEY_EMBEDDING_MODEL = "search.embedding_model"
_KEY_EMBEDDING_DIMENSION = "search.embedding_dimension"


def get_search_embedding_model() -> str:
    """Get the current embedding model ID from DB, falling back to config default."""
    value = _get_setting(_KEY_EMBEDDING_MODEL)
    return value if value else settings.SEARCH_EMBEDDING_MODEL


def get_search_embedding_dimension() -> int:
    """Get the current embedding dimension from DB, falling back to config default."""
    value = _get_setting(_KEY_EMBEDDING_DIMENSION)
    try:
        return int(value) if value else settings.SEARCH_EMBEDDING_DIMENSION
    except (ValueError, TypeError):
        return settings.SEARCH_EMBEDDING_DIMENSION


def save_search_embedding_model(model_id: str, dimension: int) -> None:
    """Persist the embedding model selection to the database."""
    _set_setting(
        _KEY_EMBEDDING_MODEL,
        model_id,
        "Search embedding model ID",
    )
    _set_setting(
        _KEY_EMBEDDING_DIMENSION,
        str(dimension),
        "Search embedding vector dimension",
    )
    logger.info(f"Saved search model setting: {model_id} ({dimension}d)")


def _get_setting(key: str) -> Optional[str]:
    """Read a single setting from the database."""
    try:
        from app.db.session_utils import session_scope
        from app.models.system_settings import SystemSettings

        with session_scope() as db:
            row = db.query(SystemSettings).filter(SystemSettings.key == key).first()
            return row.value if row else None
    except Exception as e:
        logger.warning(f"Could not read setting '{key}': {e}")
        return None


def _set_setting(key: str, value: str, description: str = "") -> None:
    """Write a single setting to the database (upsert)."""
    try:
        from app.db.session_utils import session_scope
        from app.models.system_settings import SystemSettings

        with session_scope() as db:
            row = db.query(SystemSettings).filter(SystemSettings.key == key).first()
            if row:
                row.value = value
                if description:
                    row.description = description
            else:
                db.add(SystemSettings(key=key, value=value, description=description))
            db.commit()
    except Exception as e:
        logger.error(f"Could not save setting '{key}': {e}")
