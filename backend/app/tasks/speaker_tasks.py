"""
Speaker identification and management tasks
"""

import logging
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.celery import celery_app
from app.core.constants import DEFAULT_LLM_OUTPUT_LANGUAGE
from app.db.base import SessionLocal
from app.models.media import MediaFile
from app.models.media import Speaker
from app.models.media import SpeakerProfile
from app.models.media import TranscriptSegment
from app.models.prompt import UserSetting
from app.services.llm_service import LLMService
from app.services.metadata_speaker_extractor import MetadataSpeakerExtractor
from app.services.metadata_speaker_extractor import build_cross_reference_context
from app.services.metadata_speaker_extractor import cross_reference_attributes

logger = logging.getLogger(__name__)


def _build_full_transcript(transcript_segments: list[TranscriptSegment]) -> str:
    """Build formatted transcript text from segments."""
    lines = []
    for segment in transcript_segments:
        speaker_name = segment.speaker.name if segment.speaker else "Unknown"
        timestamp = f"[{int(segment.start_time // 60):02d}:{int(segment.start_time % 60):02d}]"
        lines.append(f"{speaker_name}: {timestamp} {segment.text}")
    return "\n" + "\n".join(lines)


def _build_speaker_segments(transcript_segments: list[TranscriptSegment]) -> list[dict[str, Any]]:
    """Build speaker segments data for LLM analysis (limited to first 50)."""
    return [
        {
            "speaker_label": segment.speaker.name if segment.speaker else "Unknown",
            "start_time": segment.start_time,
            "end_time": segment.end_time,
            "text": segment.text[:200],
        }
        for segment in transcript_segments[:50]
    ]


def _get_known_speakers(db: Session, user_id: int) -> list[dict[str, Any]]:
    """Get known speaker profiles for the user."""
    profiles = db.query(SpeakerProfile).filter(SpeakerProfile.user_id == user_id).all()
    return [
        {
            "name": profile.name,
            "description": profile.description or "No description available",
            "uuid": profile.uuid,
        }
        for profile in profiles
    ]


def _build_metadata_context(media_file) -> str:
    """Build metadata context from MediaFile for LLM speaker identification.

    Extracts useful contextual information (title, author, description, tags)
    that can help the LLM identify speakers more accurately. Also runs
    structured metadata speaker extraction to produce name hints with roles.
    """
    context_parts = []

    # Run structured metadata extraction for speaker hints
    try:
        extractor = MetadataSpeakerExtractor()
        metadata = {
            "title": media_file.title,
            "author": media_file.author,
            "description": media_file.description,
            "source_url": media_file.source_url,
            "metadata_raw": media_file.metadata_raw,
        }
        extraction_result = extractor.extract(metadata)
        structured_hints = extraction_result.to_structured_context()
        if structured_hints:
            context_parts.append(structured_hints)
            logger.info(
                f"Extracted {len(extraction_result.hints)} speaker hints from metadata "
                f"(format: {extraction_result.content_format})"
            )
    except Exception as e:
        logger.warning(f"Metadata speaker extraction failed: {e}")

    # Original flat metadata context
    if media_file.title:
        context_parts.append(f"File Title: {media_file.title}")

    if media_file.author:
        context_parts.append(f"Creator/Author: {media_file.author}")

    if media_file.description:
        desc = media_file.description
        if len(desc) > 500:
            desc = desc[:500] + "..."
        context_parts.append(f"Description: {desc}")

    if media_file.source_url:
        context_parts.append(f"Source: {media_file.source_url}")

    if media_file.metadata_raw and isinstance(media_file.metadata_raw, dict):
        metadata = media_file.metadata_raw

        tags = metadata.get("tags")
        if isinstance(tags, list) and tags:
            context_parts.append(f"Tags: {', '.join(str(t) for t in tags[:10])}")
        elif isinstance(tags, str) and tags:
            context_parts.append(f"Tags: {tags[:200]}")

        categories = metadata.get("categories")
        if isinstance(categories, list) and categories:
            context_parts.append(f"Categories: {', '.join(str(c) for c in categories[:10])}")

        uploader = metadata.get("uploader")
        if uploader:
            context_parts.append(f"Channel: {str(uploader)[:100]}")

    return "\n".join(context_parts) if context_parts else ""


def _store_metadata_hints_as_suggestions(db: Session, file_id: int, media_file) -> None:
    """Extract speaker name hints from file metadata and store them for immediate display.

    These hints appear in the UI within seconds of transcription completing,
    before the LLM speaker identification task runs.

    Args:
        db: Active database session.
        file_id: Database ID of the media file.
        media_file: MediaFile ORM object to extract metadata from.
    """
    try:
        extractor = MetadataSpeakerExtractor()
        result = extractor.extract(
            {
                "title": media_file.title,
                "author": media_file.author,
                "description": media_file.description,
                "source_url": media_file.source_url,
                "metadata_raw": media_file.metadata_raw,
            }
        )

        if not result.hints:
            return

        # Store all hints in each speaker's attribute_confidence JSONB.
        # Format: {"metadata_hints": [{"name": "Joe Rogan", "role": "host",
        #          "confidence": 0.80, "source": "title"}, ...]}
        speakers = db.query(Speaker).filter(Speaker.media_file_id == file_id).all()
        if not speakers:
            return

        hints_data = [
            {
                "name": h.name,
                "role": h.role,
                "confidence": round(h.confidence, 3),
                "source": h.source,
            }
            for h in result.hints
            if h.confidence >= 0.5  # only include reasonably confident hints
        ]

        if not hints_data:
            return

        for speaker in speakers:
            existing: dict[str, Any] = dict(speaker.attribute_confidence or {})
            existing["metadata_hints"] = hints_data
            speaker.attribute_confidence = existing  # type: ignore[assignment]
            flag_modified(speaker, "attribute_confidence")

        db.flush()
        logger.info(
            f"Stored {len(hints_data)} metadata hints for {len(speakers)} speakers "
            f"in file {file_id}"
        )

    except Exception as e:
        logger.debug(f"Metadata hint storage skipped: {e}")


def _store_alignment_results(db: Session, file_id: int, cross_refs: list[dict]) -> None:
    """Store cross-reference alignment results in speaker attribute_confidence for frontend display.

    Args:
        db: Active database session.
        file_id: Database ID of the media file.
        cross_refs: List of cross-reference dicts produced by cross_reference_attributes().
    """
    try:
        # Group by speaker_label, keep best alignment (match > mismatch > unknown)
        best_per_speaker: dict[str, dict] = {}
        for ref in cross_refs:
            label = ref.get("speaker_label", "")
            alignment = ref.get("alignment", "unknown")
            if alignment == "unknown":
                continue
            existing = best_per_speaker.get(label)
            # Prefer match over mismatch
            if existing is None or alignment == "match":
                best_per_speaker[label] = ref

        if not best_per_speaker:
            return

        speakers = db.query(Speaker).filter(Speaker.media_file_id == file_id).all()
        speaker_map: dict[str, Speaker] = {str(s.name): s for s in speakers}

        for label, ref in best_per_speaker.items():
            spk = speaker_map.get(label)
            if not spk:
                continue
            existing_conf: dict[str, Any] = dict(spk.attribute_confidence or {})
            existing_conf["alignment"] = ref["alignment"]
            existing_conf["alignment_hint"] = ref["hint_name"]
            spk.attribute_confidence = existing_conf  # type: ignore[assignment]
            flag_modified(spk, "attribute_confidence")

        db.flush()
        logger.info(
            f"Stored alignment results for {len(best_per_speaker)} speakers in file {file_id}"
        )
    except Exception as e:
        logger.debug(f"Alignment storage skipped: {e}")


def _get_user_llm_output_language(db: Session, user_id: int) -> str:
    """
    Retrieve user's LLM output language setting from the database.

    Args:
        db: Database session
        user_id: ID of the user

    Returns:
        LLM output language code (default: "en")
    """
    setting = (
        db.query(UserSetting)
        .filter(
            UserSetting.user_id == user_id,
            UserSetting.setting_key == "transcription_llm_output_language",
        )
        .first()
    )

    if setting:
        return str(setting.setting_value)
    return DEFAULT_LLM_OUTPUT_LANGUAGE


def _create_llm_service(user_id: int | None) -> LLMService:
    """Create LLM service based on user settings or system defaults."""
    if user_id:
        llm_service = LLMService.create_from_user_settings(user_id)
    else:
        llm_service = LLMService.create_from_system_settings()

    if not llm_service:
        raise Exception("Could not create LLM service for speaker identification")
    return llm_service


def _run_llm_identification(
    llm_service: LLMService,
    full_transcript: str,
    speaker_segments: list[dict[str, Any]],
    known_speakers: list[dict[str, Any]],
    output_language: str = "en",
    metadata_context: str = "",
) -> dict[str, Any]:
    """Run LLM speaker identification and return predictions."""
    try:
        if hasattr(llm_service, "identify_speakers"):
            return llm_service.identify_speakers(
                transcript=full_transcript,
                speaker_segments=speaker_segments,
                known_speakers=known_speakers,
                output_language=output_language,
                metadata_context=metadata_context,
            )
        logger.warning("Speaker identification not implemented - skipping")
        return {"speaker_predictions": [], "error": "Feature not implemented"}
    finally:
        llm_service.close()


def _store_speaker_predictions(db: Session, file_id: int, predictions: dict[str, Any]) -> None:
    """Store speaker predictions as suggestions in speaker records."""
    for prediction in predictions.get("speaker_predictions", []):
        speaker_label = prediction.get("speaker_label")
        predicted_name = prediction.get("predicted_name")
        confidence = prediction.get("confidence", 0.0)

        if confidence < 0.5:
            continue

        speaker = (
            db.query(Speaker)
            .filter(Speaker.media_file_id == file_id, Speaker.name == speaker_label)
            .first()
        )

        if speaker:
            speaker.suggested_name = predicted_name
            speaker.confidence = confidence
            speaker.suggestion_source = "llm_analysis"  # type: ignore[assignment]

    db.commit()


@celery_app.task(bind=True, name="identify_speakers_llm")
def identify_speakers_llm_task(self, file_uuid: str):
    """
    Use LLM to provide speaker identification suggestions

    This task provides suggestions to help users identify speakers manually.
    The predictions are NOT automatically applied to the transcript.

    Args:
        file_uuid: UUID of the MediaFile
    """
    from app.utils.task_utils import create_task_record
    from app.utils.task_utils import update_task_status
    from app.utils.uuid_helpers import get_file_by_uuid

    task_id = self.request.id
    db = SessionLocal()
    file_id = None

    try:
        media_file = get_file_by_uuid(db, file_uuid)
        if not media_file:
            raise ValueError(f"Media file with UUID {file_uuid} not found")

        file_id = int(media_file.id)

        create_task_record(db, task_id, int(media_file.user_id), file_id, "speaker_identification")
        update_task_status(db, task_id, "in_progress", progress=0.1)

        # Store metadata hints immediately so they appear in the UI before the LLM call
        _store_metadata_hints_as_suggestions(db, file_id, media_file)
        try:
            db.commit()
        except Exception as e:
            logger.debug(f"Metadata hints commit skipped: {e}")
            db.rollback()

        transcript_segments = (
            db.query(TranscriptSegment)
            .filter(TranscriptSegment.media_file_id == file_id)
            .order_by(TranscriptSegment.start_time)
            .all()
        )

        if not transcript_segments:
            raise ValueError(f"No transcript segments found for file {file_id}")

        speakers = db.query(Speaker).filter(Speaker.media_file_id == file_id).all()

        if not speakers:
            logger.info(f"No speakers found for file {file_id}, skipping LLM identification")
            update_task_status(db, task_id, "completed", progress=1.0, completed=True)
            return {"status": "skipped", "message": "No speakers to identify"}

        full_transcript = _build_full_transcript(transcript_segments)
        speaker_segments = _build_speaker_segments(transcript_segments)
        known_speakers = _get_known_speakers(db, int(media_file.user_id))
        metadata_context = _build_metadata_context(media_file)
        if metadata_context:
            logger.info(f"Built metadata context for speaker ID ({len(metadata_context)} chars)")

        update_task_status(db, task_id, "in_progress", progress=0.5)

        predictions = _generate_predictions(
            file_id,
            int(media_file.user_id),
            db,
            full_transcript,
            speaker_segments,
            known_speakers,
            metadata_context,
        )

        update_task_status(db, task_id, "completed", progress=1.0, completed=True)

        return {
            "status": "success",
            "file_id": file_id,
            "predictions_count": len(predictions.get("speaker_predictions", [])),
            "overall_confidence": predictions.get("overall_confidence", "unknown"),
        }

    except Exception as e:
        logger.error(f"Error in speaker identification task for file {file_id}: {str(e)}")
        update_task_status(db, task_id, "failed", error_message=str(e), completed=True)
        return {"status": "error", "message": str(e)}

    finally:
        db.close()


def _generate_predictions(
    file_id: int,
    user_id: int | None,
    db: Session,
    full_transcript: str,
    speaker_segments: list[dict[str, Any]],
    known_speakers: list[dict[str, Any]],
    metadata_context: str = "",
) -> dict[str, Any]:
    """Generate LLM speaker predictions and store them."""
    try:
        logger.info(f"Starting LLM speaker identification for file {file_id}")

        # Get user's language preference for LLM output
        output_language = (
            _get_user_llm_output_language(db, user_id) if user_id else DEFAULT_LLM_OUTPUT_LANGUAGE
        )
        logger.info(f"Using LLM output language: {output_language}")

        # Enhance with cross-reference data if speaker attributes exist
        try:
            speakers_with_attrs = (
                db.query(Speaker)
                .filter(
                    Speaker.media_file_id == file_id,
                    Speaker.predicted_gender.isnot(None),
                )
                .all()
            )
            if speakers_with_attrs:
                speaker_attrs = {
                    str(s.name): {
                        "predicted_gender": s.predicted_gender,
                        "predicted_age_range": s.predicted_age_range,
                    }
                    for s in speakers_with_attrs
                }
                media_file_obj = db.query(MediaFile).filter(MediaFile.id == file_id).first()
                if media_file_obj:
                    extractor = MetadataSpeakerExtractor()
                    extraction = extractor.extract(
                        {
                            "title": media_file_obj.title,
                            "author": media_file_obj.author,
                            "description": media_file_obj.description,
                            "metadata_raw": media_file_obj.metadata_raw,
                        }
                    )
                    cross_refs = cross_reference_attributes(
                        extraction.hints, speaker_attrs, speaker_segments
                    )
                    xref_context = build_cross_reference_context(cross_refs)
                    if xref_context:
                        metadata_context = f"{metadata_context}\n\n{xref_context}"
                        logger.info(f"Added {len(cross_refs)} cross-references to context")
                    # Store alignment results in speaker attribute_confidence for frontend display
                    if cross_refs:
                        _store_alignment_results(db, file_id, cross_refs)
        except Exception as e:
            logger.debug(f"Cross-reference enrichment skipped: {e}")

        llm_service = _create_llm_service(user_id)
        predictions = _run_llm_identification(
            llm_service,
            full_transcript,
            speaker_segments,
            known_speakers,
            output_language,
            metadata_context,
        )

        _store_speaker_predictions(db, file_id, predictions)

        logger.info(
            f"Generated {len(predictions.get('speaker_predictions', []))} speaker predictions"
        )
        return predictions

    except Exception as e:
        logger.error(f"LLM speaker identification failed: {type(e).__name__}: {e}")
        logger.error("Full traceback:", exc_info=True)
        return {"speaker_predictions": [], "error": str(e)}


@celery_app.task(bind=True, name="process_speaker_update_background")
def process_speaker_update_background(
    self,
    speaker_uuid: str,
    user_id: int,
    display_name: str,
    speaker_id: int,
    old_profile_id: int | None,
    new_profile_id: int | None,
    was_auto_labeled: bool,
    display_name_changed: bool,
    media_file_id: int,
):
    """
    Background processing for speaker updates.

    This task handles heavy operations after a speaker's display_name is updated:
    - Profile embedding updates
    - OpenSearch synchronization
    - Retroactive cross-media speaker matching
    - Video cache clearing
    - WebSocket notification

    The speaker update endpoint returns immediately after saving to PostgreSQL,
    and this task runs in the background to complete the processing.

    Args:
        speaker_uuid: UUID of the speaker being updated
        user_id: ID of the user who owns the speaker
        display_name: The new display name for the speaker
        speaker_id: Database ID of the speaker
        old_profile_id: Previous profile ID (if any)
        new_profile_id: New profile ID (if any)
        was_auto_labeled: Whether the speaker was previously auto-labeled
        display_name_changed: Whether the display_name was changed
        media_file_id: ID of the media file the speaker belongs to
    """
    import asyncio

    from app.api.endpoints.speakers import _clear_video_cache_for_speaker
    from app.api.endpoints.speakers import _handle_profile_embedding_updates
    from app.api.endpoints.speakers import _handle_speaker_labeling_workflow
    from app.api.endpoints.speakers import _update_opensearch_profile_info
    from app.api.endpoints.speakers import _update_opensearch_speaker_name
    from app.api.websockets import publish_notification
    from app.utils.uuid_helpers import get_speaker_by_uuid

    db = SessionLocal()

    try:
        logger.info(
            f"Starting background processing for speaker {speaker_uuid} "
            f"(display_name: {display_name})"
        )

        # Get the speaker from the database (fresh state in case it was updated again)
        speaker = get_speaker_by_uuid(db, speaker_uuid)
        if not speaker:
            logger.error(f"Speaker {speaker_uuid} not found in background task")
            return {"status": "error", "message": "Speaker not found"}

        # Use the current display_name from DB in case user updated again before task ran
        display_name = str(speaker.display_name) if speaker.display_name else ""
        new_profile_id = int(speaker.profile_id) if speaker.profile_id else None

        # 1. Handle profile embedding updates
        logger.debug(f"Updating profile embeddings for speaker {speaker_uuid}")
        _handle_profile_embedding_updates(
            db,
            speaker_id,
            old_profile_id,
            new_profile_id,
            was_auto_labeled,
            display_name_changed,
        )

        # 2. Update OpenSearch with speaker name
        if display_name_changed and display_name:
            logger.debug(f"Updating OpenSearch speaker name for {speaker_uuid}")
            _update_opensearch_speaker_name(speaker_uuid, display_name)

        # 3. Update OpenSearch profile info
        logger.debug(f"Updating OpenSearch profile info for speaker {speaker_uuid}")
        _update_opensearch_profile_info(speaker, old_profile_id, display_name_changed, db)

        # 4. Handle speaker labeling workflow (retroactive matching)
        auto_applied_count = 0
        suggested_count = 0
        if display_name_changed and display_name and display_name.strip():
            logger.debug(f"Running retroactive matching for speaker {speaker_uuid}")
            result = _handle_speaker_labeling_workflow(speaker, display_name, db)
            if result:
                auto_applied_count = result.get("auto_applied_count", 0)
                suggested_count = result.get("suggested_count", 0)

        # 5. Clear video cache
        logger.debug(f"Clearing video cache for media file {media_file_id}")
        _clear_video_cache_for_speaker(db, media_file_id)

        # 6. Send WebSocket notification that background processing is complete
        logger.debug(f"Sending WebSocket notification for speaker {speaker_uuid}")

        notification_data = {
            "speaker_uuid": speaker_uuid,
            "display_name": display_name,
            "profile_id": str(speaker.profile.uuid) if speaker.profile else None,
            "auto_applied_count": auto_applied_count,
            "suggested_count": suggested_count,
            "processing_status": "complete",
            "media_file_id": str(speaker.media_file.uuid) if speaker.media_file else None,
        }

        # Publish notification using async pattern
        coro = publish_notification(
            user_id=user_id,
            notification_type="speaker_processing_complete",
            data=notification_data,
        )

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(coro)
        except RuntimeError:
            asyncio.run(coro)

        logger.info(
            f"Background processing complete for speaker {speaker_uuid}. "
            f"Auto-applied: {auto_applied_count}, Suggested: {suggested_count}"
        )

        return {
            "status": "success",
            "speaker_uuid": speaker_uuid,
            "auto_applied_count": auto_applied_count,
            "suggested_count": suggested_count,
        }

    except Exception as e:
        logger.error(
            f"Error in background speaker processing for {speaker_uuid}: {type(e).__name__}: {e}"
        )
        logger.error("Full traceback:", exc_info=True)
        return {"status": "error", "message": str(e)}

    finally:
        db.close()


@celery_app.task(bind=True, name="extract_speaker_embeddings")
def extract_speaker_embeddings_task(
    self,
    file_uuid: str,
    speaker_mapping: dict[str, int],
):
    """
    Extract speaker embeddings asynchronously after transcription completes.

    This task runs in the background to extract voice embeddings for speaker
    matching, allowing the main transcription to complete faster. It downloads
    the audio file from MinIO and processes it independently.

    Args:
        file_uuid: UUID of the MediaFile
        speaker_mapping: Mapping of speaker labels to database IDs
    """
    import os
    import tempfile

    from app.services.minio_service import download_file
    from app.services.speaker_embedding_service import SpeakerEmbeddingService
    from app.services.speaker_matching_service import SpeakerMatchingService
    from app.tasks.transcription.audio_processor import get_audio_file_extension
    from app.tasks.transcription.audio_processor import prepare_audio_for_transcription
    from app.utils.hardware_detection import detect_hardware
    from app.utils.task_utils import create_task_record
    from app.utils.task_utils import update_task_status
    from app.utils.uuid_helpers import get_file_by_uuid

    task_id = self.request.id
    db = SessionLocal()

    try:
        media_file = get_file_by_uuid(db, file_uuid)
        if not media_file:
            raise ValueError(f"Media file with UUID {file_uuid} not found")

        file_id = int(media_file.id)
        user_id = int(media_file.user_id)
        storage_path = str(media_file.storage_path)
        content_type = str(media_file.content_type)
        filename = str(media_file.filename)

        create_task_record(db, task_id, user_id, file_id, "speaker_embedding")
        update_task_status(db, task_id, "in_progress", progress=0.1)

        # Force GPU synchronization before loading embedding model
        hardware_config = detect_hardware()
        hardware_config.optimize_memory_usage()
        logger.info("GPU memory synchronized before speaker embedding extraction")

        # Get transcript segments for embedding extraction
        transcript_segments = (
            db.query(TranscriptSegment)
            .filter(TranscriptSegment.media_file_id == file_id)
            .order_by(TranscriptSegment.start_time)
            .all()
        )

        if not transcript_segments:
            logger.warning(f"No transcript segments found for file {file_id}")
            update_task_status(db, task_id, "completed", progress=1.0, completed=True)
            return {"status": "skipped", "message": "No segments to process"}

        # Convert segments to dict format for embedding service
        processed_segments = [
            {
                "start": seg.start_time,
                "end": seg.end_time,
                "text": seg.text,
                "speaker": seg.speaker.name if seg.speaker else "SPEAKER_00",
                "speaker_id": seg.speaker_id,
            }
            for seg in transcript_segments
        ]

        update_task_status(db, task_id, "in_progress", progress=0.2)

        # Download file from MinIO and prepare audio
        logger.info(f"Downloading file {storage_path} for speaker embedding extraction")
        file_data, _, _ = download_file(storage_path)
        file_ext = get_audio_file_extension(content_type, filename)

        with tempfile.TemporaryDirectory() as temp_dir:
            # Save downloaded file
            temp_file_path = os.path.join(temp_dir, f"input{file_ext}")
            with open(temp_file_path, "wb") as f:
                f.write(file_data.read())

            # Prepare audio for embedding extraction
            audio_file_path = prepare_audio_for_transcription(
                temp_file_path, content_type, temp_dir
            )

            update_task_status(db, task_id, "in_progress", progress=0.4)

            # Initialize embedding service and extract embeddings
            embedding_service = SpeakerEmbeddingService()
            logger.info(
                f"Using speaker embedding mode: {embedding_service.mode} ({embedding_service.model_name})"
            )

            try:
                matching_service = SpeakerMatchingService(db, embedding_service)
                logger.info(
                    f"Starting speaker matching for {len(speaker_mapping)} speakers in file {file_id}"
                )

                speaker_results = matching_service.process_speaker_segments(
                    audio_file_path, file_id, user_id, processed_segments, speaker_mapping
                )

                update_task_status(db, task_id, "in_progress", progress=0.9)
                logger.info(
                    f"Speaker matching completed: {len(speaker_results) if speaker_results else 0} results"
                )

            finally:
                # Clean up embedding service to free VRAM
                embedding_service.cleanup()
                hardware_config.optimize_memory_usage()

        update_task_status(db, task_id, "completed", progress=1.0, completed=True)

        return {
            "status": "success",
            "file_id": file_id,
            "speakers_processed": len(speaker_results) if speaker_results else 0,
        }

    except Exception as e:
        logger.error(f"Error in speaker embedding task for {file_uuid}: {str(e)}")
        logger.error("Full traceback:", exc_info=True)
        update_task_status(db, task_id, "failed", error_message=str(e), completed=True)
        return {"status": "error", "message": str(e)}

    finally:
        db.close()


@celery_app.task(bind=True, name="update_speaker_embedding_on_reassignment")
def update_speaker_embedding_on_reassignment(
    self,
    segment_uuid: str,
    media_file_uuid: str,
    target_speaker_uuid: str,
    source_speaker_uuid: str | None,
    user_id: int,
):
    """
    Update speaker embeddings after a segment is manually reassigned to a different speaker.

    Extracts the voice embedding from the reassigned segment's audio and incorporates
    it into the target speaker's embedding via weighted average. This enables iterative
    speaker profile refinement for difficult-to-match segments.

    Args:
        segment_uuid: UUID of the reassigned transcript segment
        media_file_uuid: UUID of the media file containing the segment
        target_speaker_uuid: UUID of the speaker that received the segment
        source_speaker_uuid: UUID of the speaker that lost the segment (or None if orphan-deleted)
        user_id: ID of the user who owns the data
    """
    # Gate: defer while speaker embedding migration holds the GPU
    from app.services.migration_lock_service import migration_lock

    if migration_lock.is_active():
        logger.info("Migration lock active — deferring speaker embedding update (retry in 60s)")
        raise self.retry(countdown=60, max_retries=120)

    import os
    import tempfile

    import numpy as np

    from app.services.minio_service import download_file
    from app.services.opensearch_service import add_speaker_embedding
    from app.services.opensearch_service import get_speaker_document
    from app.services.opensearch_service import update_speaker_segment_count
    from app.services.speaker_embedding_service import get_cached_embedding_service
    from app.tasks.transcription.audio_processor import get_audio_file_extension
    from app.tasks.transcription.audio_processor import prepare_audio_for_transcription
    from app.utils.uuid_helpers import get_by_uuid

    db = SessionLocal()

    try:
        # Look up the segment and verify it still belongs to the target speaker
        segment = get_by_uuid(db, TranscriptSegment, segment_uuid)
        if not segment:
            logger.warning(f"Segment {segment_uuid} not found, skipping embedding update")
            return {"status": "skipped", "reason": "segment_not_found"}

        target_speaker = get_by_uuid(db, Speaker, target_speaker_uuid)
        if not target_speaker:
            logger.warning(
                f"Target speaker {target_speaker_uuid} not found, skipping embedding update"
            )
            return {"status": "skipped", "reason": "target_speaker_not_found"}

        # Guard against race conditions: verify segment still belongs to target speaker
        if segment.speaker_id != target_speaker.id:
            logger.info(
                f"Segment {segment_uuid} no longer belongs to speaker {target_speaker_uuid} "
                f"(race condition), skipping"
            )
            return {"status": "skipped", "reason": "segment_reassigned"}

        # Skip segments shorter than 0.5s (unreliable embeddings)
        duration = float(segment.end_time) - float(segment.start_time)
        if duration < 0.5:
            logger.info(
                f"Segment {segment_uuid} too short ({duration:.2f}s), skipping embedding update"
            )
            return {"status": "skipped", "reason": "segment_too_short"}

        # Get the media file for audio download
        media_file = db.query(MediaFile).filter(MediaFile.id == segment.media_file_id).first()
        if not media_file:
            logger.error(f"Media file not found for segment {segment_uuid}")
            return {"status": "error", "reason": "media_file_not_found"}

        storage_path = str(media_file.storage_path)
        content_type = str(media_file.content_type)
        filename = str(media_file.filename)

        # Download audio from MinIO and extract embedding
        logger.info(
            f"Extracting embedding for segment {segment_uuid} "
            f"(speaker {target_speaker_uuid}, {duration:.1f}s)"
        )
        file_data, _, _ = download_file(storage_path)
        file_ext = get_audio_file_extension(content_type, filename)

        new_embedding = None
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_file_path = os.path.join(temp_dir, f"input{file_ext}")
            with open(temp_file_path, "wb") as f:
                f.write(file_data.read())

            audio_file_path = prepare_audio_for_transcription(
                temp_file_path, content_type, temp_dir
            )

            # Use cached embedding service for warm model reuse
            embedding_service = get_cached_embedding_service()

            embedding_result = embedding_service.extract_embedding_from_file(
                audio_file_path,
                {"start": float(segment.start_time), "end": float(segment.end_time)},
            )

            if embedding_result is not None:
                new_embedding = np.array(embedding_result)
            else:
                logger.warning(f"Failed to extract embedding for segment {segment_uuid}")
                return {"status": "error", "reason": "embedding_extraction_failed"}

        # Update target speaker embedding via weighted average
        existing_doc = get_speaker_document(target_speaker_uuid)

        if existing_doc is None:
            # New speaker with no existing embedding — store directly
            logger.info(
                f"Storing initial embedding for speaker {target_speaker_uuid} "
                f"from segment {segment_uuid}"
            )
            add_speaker_embedding(
                speaker_id=int(target_speaker.id),
                speaker_uuid=target_speaker_uuid,
                user_id=user_id,
                name=str(target_speaker.name),
                embedding=new_embedding.tolist(),
                profile_id=(int(target_speaker.profile_id) if target_speaker.profile_id else None),
                profile_uuid=(str(target_speaker.profile.uuid) if target_speaker.profile else None),
                media_file_id=int(target_speaker.media_file_id),
                segment_count=1,
                display_name=(
                    str(target_speaker.display_name) if target_speaker.display_name else None
                ),
            )
        else:
            # Weighted average: (old * count + new) / (count + 1), then L2 normalize
            old_embedding = np.array(existing_doc["embedding"])
            old_count = existing_doc["segment_count"]
            new_count = old_count + 1

            weighted = (old_embedding * old_count + new_embedding) / new_count
            norm = np.linalg.norm(weighted)
            if norm > 0:
                weighted = weighted / norm

            logger.info(
                f"Updating speaker {target_speaker_uuid} embedding: "
                f"segment_count {old_count} -> {new_count}"
            )
            add_speaker_embedding(
                speaker_id=int(target_speaker.id),
                speaker_uuid=target_speaker_uuid,
                user_id=user_id,
                name=str(target_speaker.name),
                embedding=weighted.tolist(),
                profile_id=(int(target_speaker.profile_id) if target_speaker.profile_id else None),
                profile_uuid=(str(target_speaker.profile.uuid) if target_speaker.profile else None),
                media_file_id=int(target_speaker.media_file_id),
                segment_count=new_count,
                display_name=(
                    str(target_speaker.display_name) if target_speaker.display_name else None
                ),
            )

        # Update source speaker segment_count (if it still exists)
        if source_speaker_uuid:
            source_speaker = get_by_uuid(db, Speaker, source_speaker_uuid)
            if source_speaker:
                source_doc = get_speaker_document(source_speaker_uuid)
                if source_doc and source_doc["segment_count"] > 1:
                    update_speaker_segment_count(
                        source_speaker_uuid, source_doc["segment_count"] - 1
                    )
                    logger.info(f"Decremented source speaker {source_speaker_uuid} segment_count")

        # Update profile embeddings if either speaker has a profile_id
        _update_affected_profiles(db, target_speaker, source_speaker_uuid)

        logger.info(
            f"Successfully updated embeddings after segment {segment_uuid} "
            f"reassignment to speaker {target_speaker_uuid}"
        )
        return {"status": "success", "target_speaker_uuid": target_speaker_uuid}

    except Exception as e:
        logger.error(f"Error updating speaker embedding on reassignment: {type(e).__name__}: {e}")
        logger.error("Full traceback:", exc_info=True)
        return {"status": "error", "message": str(e)}

    finally:
        db.close()


def _update_affected_profiles(
    db: Session, target_speaker: Speaker, source_speaker_uuid: str | None
) -> None:
    """Update profile embeddings for speakers affected by a segment reassignment."""
    from app.services.profile_embedding_service import ProfileEmbeddingService

    profile_ids_to_update: set[int] = set()

    if target_speaker.profile_id:
        profile_ids_to_update.add(int(target_speaker.profile_id))

    if source_speaker_uuid:
        from app.utils.uuid_helpers import get_by_uuid

        source_speaker = get_by_uuid(db, Speaker, source_speaker_uuid)
        if source_speaker and source_speaker.profile_id:
            profile_ids_to_update.add(int(source_speaker.profile_id))

    for profile_id in profile_ids_to_update:
        try:
            ProfileEmbeddingService.update_profile_embedding(db, profile_id)
            logger.info(f"Updated profile embedding for profile {profile_id}")
        except Exception as e:
            logger.warning(f"Failed to update profile embedding {profile_id}: {e}")
