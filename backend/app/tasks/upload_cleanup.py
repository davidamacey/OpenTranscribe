"""
Celery beat task for cleaning up expired TUS upload sessions.

Runs every 6 hours to abort any MinIO multipart uploads whose sessions
have passed their expiry time (created_at + 24h) without being completed.
"""

import logging
from datetime import datetime
from datetime import timezone

from app.core.celery import celery_app
from app.db.base import SessionLocal
from app.models.upload_session import UploadSession
from app.services.minio_service import MinIOService

logger = logging.getLogger(__name__)
minio_service = MinIOService()


@celery_app.task(name="system.cleanup_incomplete_tus_uploads")
def cleanup_incomplete_tus_uploads():
    """Abort MinIO multipart uploads for expired TUS sessions.

    Queries for all 'active' UploadSession rows whose expires_at timestamp
    has passed. For each expired session, calls abort_multipart_upload on
    MinIO and marks the session as 'aborted' in the database.

    Each session abort is wrapped in an independent try/except so a single
    MinIO connection failure does not abort the entire cleanup run.
    """
    cutoff = datetime.now(timezone.utc)
    db = SessionLocal()
    aborted_count = 0
    error_count = 0

    try:
        expired_sessions = (
            db.query(UploadSession)
            .filter(
                UploadSession.status == "active",
                UploadSession.expires_at < cutoff,
            )
            .all()
        )

        for session in expired_sessions:
            try:
                if session.minio_upload_id and session.storage_path:
                    minio_service.abort_multipart_upload(
                        session.storage_path, session.minio_upload_id
                    )
                session.status = "aborted"
                aborted_count += 1
            except Exception as e:
                error_count += 1
                logger.warning(
                    f"Failed to abort MinIO upload {session.minio_upload_id} "
                    f"(session {session.upload_id}): {e}"
                )

        db.commit()
        logger.info(
            "TUS cleanup complete",
            extra={
                "event": "tus_cleanup_run",
                "aborted_count": aborted_count,
                "error_count": error_count,
            },
        )
        return {"aborted": aborted_count, "errors": error_count}

    except Exception as e:
        logger.error(f"TUS cleanup task failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()
