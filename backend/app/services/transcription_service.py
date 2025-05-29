"""
Transcription service layer for centralized transcription operations.

This service provides a high-level interface for transcription-related operations,
abstracting away the complexity of task management and processing workflows.
"""

import logging
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.media import MediaFile, TranscriptSegment, Speaker, Task
from app.schemas.media import TranscriptSegmentUpdate
from app.utils.db_helpers import safe_get_by_id, get_or_create
from app.utils.auth_decorators import AuthorizationHelper
from app.utils.error_handlers import ErrorHandler
from app.tasks.transcription import transcribe_audio_task, analyze_transcript_task, summarize_transcript_task

logger = logging.getLogger(__name__)


class TranscriptionService:
    """Service class for transcription operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def start_transcription(self, file_id: int, user: User) -> Dict[str, Any]:
        """
        Start transcription for a file.
        
        Args:
            file_id: File ID
            user: Current user
            
        Returns:
            Dictionary with task information
        """
        try:
            # Verify user access to file
            file_obj = AuthorizationHelper.check_file_access(self.db, file_id, user)
            
            # Check if file is in a valid state for transcription
            if file_obj.status.value not in ['pending', 'error']:
                raise ErrorHandler.validation_error(
                    f"File is in {file_obj.status.value} status and cannot be transcribed"
                )
            
            # Start transcription task
            task = transcribe_audio_task.delay(file_id)
            
            return {
                "task_id": task.id,
                "file_id": file_id,
                "status": "started",
                "message": "Transcription task started"
            }
            
        except Exception as e:
            logger.error(f"Error starting transcription: {e}")
            raise ErrorHandler.file_processing_error("transcription start", e)
    
    def get_transcription_status(self, file_id: int, user: User) -> Dict[str, Any]:
        """
        Get transcription status for a file.
        
        Args:
            file_id: File ID
            user: Current user
            
        Returns:
            Dictionary with transcription status
        """
        try:
            # Verify user access
            file_obj = AuthorizationHelper.check_file_access(self.db, file_id, user)
            
            # Get latest task for this file
            latest_task = self.db.query(Task).filter(
                Task.media_file_id == file_id,
                Task.task_type == "transcription"
            ).order_by(Task.created_at.desc()).first()
            
            # Get transcript segment count
            segment_count = self.db.query(TranscriptSegment).filter(
                TranscriptSegment.media_file_id == file_id
            ).count()
            
            return {
                "file_id": file_id,
                "file_status": file_obj.status.value,
                "task_status": latest_task.status if latest_task else None,
                "task_progress": latest_task.progress if latest_task else 0.0,
                "error_message": latest_task.error_message if latest_task else None,
                "segment_count": segment_count,
                "duration": file_obj.duration,
                "language": file_obj.language
            }
            
        except Exception as e:
            logger.error(f"Error getting transcription status: {e}")
            raise ErrorHandler.database_error("status retrieval", e)
    
    def get_transcript_segments(self, file_id: int, user: User) -> List[TranscriptSegment]:
        """
        Get transcript segments for a file.
        
        Args:
            file_id: File ID
            user: Current user
            
        Returns:
            List of TranscriptSegment objects
        """
        try:
            # Verify user access
            AuthorizationHelper.check_file_access(self.db, file_id, user)
            
            return self.db.query(TranscriptSegment).filter(
                TranscriptSegment.media_file_id == file_id
            ).order_by(TranscriptSegment.start_time).all()
            
        except Exception as e:
            logger.error(f"Error getting transcript segments: {e}")
            raise ErrorHandler.database_error("segment retrieval", e)
    
    def update_transcript_segments(self, file_id: int, updates: List[TranscriptSegmentUpdate], 
                                 user: User) -> List[TranscriptSegment]:
        """
        Update transcript segments.
        
        Args:
            file_id: File ID
            updates: List of segment updates
            user: Current user
            
        Returns:
            Updated transcript segments
        """
        try:
            # Verify user access
            AuthorizationHelper.check_file_access(self.db, file_id, user)
            
            # Update segments
            for update in updates:
                segment = self.db.query(TranscriptSegment).filter(
                    TranscriptSegment.id == update.id,
                    TranscriptSegment.media_file_id == file_id
                ).first()
                
                if segment:
                    for field, value in update.model_dump(exclude_unset=True).items():
                        setattr(segment, field, value)
            
            self.db.commit()
            
            # Return updated segments
            return self.get_transcript_segments(file_id, user)
            
        except Exception as e:
            logger.error(f"Error updating transcript segments: {e}")
            self.db.rollback()
            raise ErrorHandler.database_error("segment update", e)
    
    def get_file_speakers(self, file_id: int, user: User) -> List[Speaker]:
        """
        Get speakers that appear in a file.
        
        Args:
            file_id: File ID
            user: Current user
            
        Returns:
            List of Speaker objects
        """
        try:
            # Verify user access
            AuthorizationHelper.check_file_access(self.db, file_id, user)
            
            return self.db.query(Speaker).join(TranscriptSegment).filter(
                TranscriptSegment.media_file_id == file_id
            ).distinct().all()
            
        except Exception as e:
            logger.error(f"Error getting file speakers: {e}")
            raise ErrorHandler.database_error("speaker retrieval", e)
    
    def update_speaker_info(self, speaker_id: int, display_name: str, user: User) -> Speaker:
        """
        Update speaker display name.
        
        Args:
            speaker_id: Speaker ID
            display_name: New display name
            user: Current user
            
        Returns:
            Updated Speaker object
        """
        try:
            speaker = self.db.query(Speaker).filter(
                Speaker.id == speaker_id,
                Speaker.user_id == user.id
            ).first()
            
            if not speaker:
                raise ErrorHandler.not_found_error("Speaker")
            
            speaker.display_name = display_name
            speaker.verified = True  # Mark as verified when user updates
            
            self.db.commit()
            self.db.refresh(speaker)
            
            return speaker
            
        except Exception as e:
            logger.error(f"Error updating speaker info: {e}")
            self.db.rollback()
            raise ErrorHandler.database_error("speaker update", e)
    
    def merge_speakers(self, primary_speaker_id: int, secondary_speaker_id: int, user: User) -> Speaker:
        """
        Merge two speakers by moving all segments from secondary to primary.
        
        Args:
            primary_speaker_id: ID of the speaker to keep
            secondary_speaker_id: ID of the speaker to remove
            user: Current user
            
        Returns:
            Primary speaker object
        """
        try:
            # Verify both speakers belong to user
            primary = self.db.query(Speaker).filter(
                Speaker.id == primary_speaker_id,
                Speaker.user_id == user.id
            ).first()
            
            secondary = self.db.query(Speaker).filter(
                Speaker.id == secondary_speaker_id,
                Speaker.user_id == user.id
            ).first()
            
            if not primary or not secondary:
                raise ErrorHandler.not_found_error("Speaker")
            
            # Move all segments from secondary to primary
            self.db.query(TranscriptSegment).filter(
                TranscriptSegment.speaker_id == secondary_speaker_id
            ).update({"speaker_id": primary_speaker_id})
            
            # Delete secondary speaker
            self.db.delete(secondary)
            self.db.commit()
            
            return primary
            
        except Exception as e:
            logger.error(f"Error merging speakers: {e}")
            self.db.rollback()
            raise ErrorHandler.database_error("speaker merge", e)
    
    def start_analysis(self, file_id: int, user: User) -> Dict[str, Any]:
        """
        Start transcript analysis for a file.
        
        Args:
            file_id: File ID
            user: Current user
            
        Returns:
            Dictionary with task information
        """
        try:
            # Verify user access and that file has transcript
            file_obj = AuthorizationHelper.check_file_access(self.db, file_id, user)
            
            segment_count = self.db.query(TranscriptSegment).filter(
                TranscriptSegment.media_file_id == file_id
            ).count()
            
            if segment_count == 0:
                raise ErrorHandler.validation_error("File has no transcript to analyze")
            
            # Start analysis task
            task = analyze_transcript_task.delay(file_id)
            
            return {
                "task_id": task.id,
                "file_id": file_id,
                "status": "started",
                "message": "Analysis task started"
            }
            
        except Exception as e:
            logger.error(f"Error starting analysis: {e}")
            raise ErrorHandler.file_processing_error("analysis start", e)
    
    def start_summarization(self, file_id: int, user: User) -> Dict[str, Any]:
        """
        Start transcript summarization for a file.
        
        Args:
            file_id: File ID
            user: Current user
            
        Returns:
            Dictionary with task information
        """
        try:
            # Verify user access and that file has transcript
            file_obj = AuthorizationHelper.check_file_access(self.db, file_id, user)
            
            segment_count = self.db.query(TranscriptSegment).filter(
                TranscriptSegment.media_file_id == file_id
            ).count()
            
            if segment_count == 0:
                raise ErrorHandler.validation_error("File has no transcript to summarize")
            
            # Start summarization task
            task = summarize_transcript_task.delay(file_id)
            
            return {
                "task_id": task.id,
                "file_id": file_id,
                "status": "started",
                "message": "Summarization task started"
            }
            
        except Exception as e:
            logger.error(f"Error starting summarization: {e}")
            raise ErrorHandler.file_processing_error("summarization start", e)
    
    def search_transcript(self, file_id: int, query: str, user: User) -> List[TranscriptSegment]:
        """
        Search within a transcript.
        
        Args:
            file_id: File ID
            query: Search query
            user: Current user
            
        Returns:
            List of matching TranscriptSegment objects
        """
        try:
            # Verify user access
            AuthorizationHelper.check_file_access(self.db, file_id, user)
            
            return self.db.query(TranscriptSegment).filter(
                TranscriptSegment.media_file_id == file_id,
                TranscriptSegment.text.ilike(f"%{query}%")
            ).order_by(TranscriptSegment.start_time).all()
            
        except Exception as e:
            logger.error(f"Error searching transcript: {e}")
            raise ErrorHandler.database_error("transcript search", e)