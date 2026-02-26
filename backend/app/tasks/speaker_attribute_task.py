"""
Celery task for speaker attribute detection.

Runs on the CPU queue (concurrency=8) after transcription completes.
Non-critical: failure does not affect transcription status.
"""

import logging
import os
import tempfile

from app.core.celery import celery_app
from app.db.base import SessionLocal

logger = logging.getLogger(__name__)


def _is_speaker_attribute_detection_enabled(user_id: int) -> bool:
    """Check if speaker attribute detection is enabled for a user.

    Resolution order: User setting > System setting > .env > default (True).
    """
    from app.models.prompt import UserSetting
    from app.services.system_settings_service import get_setting_bool

    # Check .env default
    env_enabled = os.environ.get("SPEAKER_ATTRIBUTE_DETECTION_ENABLED", "true").lower() == "true"

    db = SessionLocal()
    try:
        # Check system setting (requires db session)
        system_enabled = get_setting_bool(
            db, "speaker_attribute.detection_enabled", default=env_enabled
        )

        # Check user setting
        user_setting = (
            db.query(UserSetting)
            .filter(
                UserSetting.user_id == user_id,
                UserSetting.setting_key == "speaker_attribute_detection_enabled",
            )
            .first()
        )
        if user_setting:
            return str(user_setting.setting_value).lower() == "true"
    finally:
        db.close()

    return system_enabled


@celery_app.task(bind=True, name="detect_speaker_attributes", queue="cpu")
def detect_speaker_attributes_task(self, file_uuid: str, user_id: int):
    """Predict gender/age for all speakers in a media file.

    Runs on CPU queue in parallel with GPU transcription of next file.
    Non-critical - failure does not affect transcription status.
    """
    from datetime import datetime
    from datetime import timezone

    from app.models.media import Speaker
    from app.models.media import TranscriptSegment
    from app.services.minio_service import download_file
    from app.services.speaker_attribute_service import get_cached_attribute_service
    from app.tasks.transcription.audio_processor import get_audio_file_extension
    from app.tasks.transcription.audio_processor import prepare_audio_for_transcription
    from app.utils.uuid_helpers import get_file_by_uuid

    db = SessionLocal()

    try:
        # Check if feature is enabled
        if not _is_speaker_attribute_detection_enabled(user_id):
            logger.info("Speaker attribute detection disabled, skipping")
            return {"status": "skipped", "reason": "disabled"}

        media_file = get_file_by_uuid(db, file_uuid)
        if not media_file:
            logger.error(f"Media file {file_uuid} not found for attribute detection")
            return {"status": "error", "reason": "file_not_found"}

        file_id = int(media_file.id)
        storage_path = str(media_file.storage_path)
        content_type = str(media_file.content_type)
        filename = str(media_file.filename)

        # Get speakers
        speakers = db.query(Speaker).filter(Speaker.media_file_id == file_id).all()
        if not speakers:
            logger.info(f"No speakers found for file {file_id}, skipping attribute detection")
            return {"status": "skipped", "reason": "no_speakers"}

        speaker_mapping = {str(s.name): int(s.id) for s in speakers}

        # Get transcript segments
        segments = (
            db.query(TranscriptSegment)
            .filter(TranscriptSegment.media_file_id == file_id)
            .order_by(TranscriptSegment.start_time)
            .all()
        )

        if not segments:
            return {"status": "skipped", "reason": "no_segments"}

        processed_segments = [
            {
                "start": float(seg.start_time),
                "end": float(seg.end_time),
                "text": seg.text,
                "speaker": (str(seg.speaker.name) if seg.speaker else "SPEAKER_00"),
            }
            for seg in segments
        ]

        # Download audio from MinIO
        logger.info(f"Downloading audio for speaker attribute detection: {file_uuid}")
        file_data, _, _ = download_file(storage_path)
        file_ext = get_audio_file_extension(content_type, filename)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_file_path = os.path.join(temp_dir, f"input{file_ext}")
            with open(temp_file_path, "wb") as f:
                f.write(file_data.read())

            audio_file_path = prepare_audio_for_transcription(
                temp_file_path, content_type, temp_dir
            )

            # Run attribute detection
            service = get_cached_attribute_service()
            results = service.predict_attributes(
                audio_file_path, processed_segments, speaker_mapping
            )

        # Store results in database
        now = datetime.now(timezone.utc)
        updated_count = 0

        for speaker in speakers:
            speaker_label = str(speaker.name)
            if speaker_label in results:
                attrs = results[speaker_label]
                speaker.predicted_gender = attrs.get("predicted_gender")
                speaker.predicted_age_range = attrs.get("predicted_age_range")
                speaker.attribute_confidence = attrs.get("attribute_confidence")
                speaker.attributes_predicted_at = now
                updated_count += 1

        db.commit()

        logger.info(
            f"Speaker attribute detection complete for file {file_uuid}: "
            f"{updated_count}/{len(speakers)} speakers updated"
        )

        return {
            "status": "success",
            "file_uuid": file_uuid,
            "speakers_updated": updated_count,
            "total_speakers": len(speakers),
        }

    except Exception as e:
        logger.error(f"Speaker attribute detection failed for {file_uuid}: {e}")
        logger.error("Full traceback:", exc_info=True)
        return {"status": "error", "message": str(e)}

    finally:
        db.close()
