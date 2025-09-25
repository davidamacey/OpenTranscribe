import logging

from app.core.celery import celery_app
from app.db.base import SessionLocal
from app.models.media import MediaFile
from app.services.analytics_service import AnalyticsService

# Setup logging
logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="analyze_transcript")
def analyze_transcript_task(self, file_id: int):
    """
    Analyze a transcript to extract comprehensive analytics:
    - Speaker talk time and statistics
    - Turn-taking analysis
    - Interruption detection
    - Question analysis
    - Overall metrics

    Args:
        file_id: Database ID of the MediaFile to analyze
    """
    task_id = self.request.id
    db = SessionLocal()

    try:
        # Get media file from database
        media_file = db.query(MediaFile).filter(MediaFile.id == file_id).first()
        if not media_file:
            raise ValueError(f"Media file with ID {file_id} not found")

        # Create task record
        from app.utils.task_utils import create_task_record
        from app.utils.task_utils import update_task_status

        create_task_record(db, task_id, media_file.user_id, file_id, "analytics")

        # Update task status
        update_task_status(db, task_id, "in_progress", progress=0.1)

        # Compute comprehensive analytics using the new service
        success = AnalyticsService.compute_and_save_analytics(db, file_id)

        if not success:
            raise ValueError(f"Failed to compute analytics for file {file_id}")

        # Update task progress - analytics computation complete
        update_task_status(db, task_id, "in_progress", progress=0.6)

        # Analytics computation complete - update final progress

        # Update task as completed
        update_task_status(db, task_id, "completed", progress=1.0, completed=True)

        logger.info(
            f"Successfully analyzed file {media_file.filename} with comprehensive analytics"
        )
        return {"status": "success", "file_id": file_id}

    except Exception as e:
        # Handle errors
        logger.error(f"Error analyzing file {file_id}: {str(e)}")
        from app.utils.task_utils import update_task_status

        update_task_status(db, task_id, "failed", error_message=str(e), completed=True)
        return {"status": "error", "message": str(e)}

    finally:
        db.close()
