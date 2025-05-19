import os
import tempfile
import numpy as np
from pathlib import Path
import torch
import datetime
from sqlalchemy.orm import Session
import ffmpeg
import logging
from typing import Dict, List, Any, Tuple, Optional
import json
import asyncio
import io

from app.core.celery import celery_app
from app.db.base import SessionLocal
from app.models.media import MediaFile, TranscriptSegment, Speaker, Task, Analytics, FileStatus
from app.services.minio_service import download_file
from app.services.opensearch_service import index_transcript, add_speaker_embedding
from app.core.config import settings
from app.api.websockets import send_notification
from app.db.session_utils import session_scope, get_refreshed_object

# Setup logging
logger = logging.getLogger(__name__)

def create_task_record(db: Session, celery_task_id: str, user_id: int, media_file_id: int, task_type: str) -> Task:
    """Create a new task record in the database"""
    task = Task(
        id=celery_task_id,
        user_id=user_id,
        media_file_id=media_file_id,
        task_type=task_type,
        status="pending",
        progress=0.0
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task

def update_task_status(db: Session, task_id: str, status: str, progress: float = None, 
                       error_message: str = None, completed: bool = False):
    """Update task status in the database"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return
    
    task.status = status
    if progress is not None:
        task.progress = progress
    if error_message:
        task.error_message = error_message
    if completed:
        task.completed_at = datetime.datetime.now()
    
    db.commit()

def update_media_file_status(db: Session, file_id: int, status: str):
    """Update media file status"""
    media_file = db.query(MediaFile).filter(MediaFile.id == file_id).first()
    if media_file:
        media_file.status = status
        db.commit()

@celery_app.task(bind=True, name="transcribe_audio")
def transcribe_audio_task(self, file_id: int):
    """
    Process an audio/video file with WhisperX for transcription and Pyannote for diarization
    
    Args:
        file_id: Database ID of the MediaFile to transcribe
    """
    task_id = self.request.id
    
    try:
        # Step 1: Update file status to processing and get user_id
        with session_scope() as db:
            # Get the media file
            media_file = get_refreshed_object(db, MediaFile, file_id)
            if not media_file:
                logger.error(f"Media file with ID {file_id} not found")
                return {"status": "error", "message": f"Media file with ID {file_id} not found"}
            
            # Get all needed data before the session is committed
            user_id = media_file.user_id
            file_path = media_file.storage_path
            file_name = media_file.filename
            
            # Update status
            media_file.status = FileStatus.PROCESSING
            # No need to explicitly commit - session_scope does it for us
            
        # Send WebSocket notification about status change
        try:
            asyncio.run(send_notification(
                user_id,
                "transcription_status", 
                {
                    "file_id": str(file_id),
                    "status": FileStatus.PROCESSING.value,
                    "message": "Transcription started",
                    "progress": 10
                }
            ))
        except Exception as e:
            logger.warning(f"Failed to send WebSocket notification: {e}")
            # Continue with processing even if notification fails
        
        # Step 2: Create task record with session_scope
        with session_scope() as db:
            create_task_record(db, task_id, user_id, file_id, "transcription")
        
        # Step 3: Update task status with session_scope
        with session_scope() as db:
            update_task_status(db, task_id, "in_progress", progress=0.1)
        
        # Download file from MinIO
        file_data, file_size, content_type = download_file(media_file.storage_path)
        
        # Create temporary file
        suffix = Path(media_file.filename).suffix
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
            temp_file.write(file_data.read())
            temp_path = temp_file.name
        
        try:
            # Extract audio if it's a video file
            is_video = content_type.startswith('video/')
            audio_path = temp_path
            
            if is_video:
                # Extract audio to a temporary WAV file
                audio_path = f"{temp_path}_audio.wav"
                ffmpeg.input(temp_path).output(audio_path, acodec='pcm_s16le', ac=1, ar='16k').run(quiet=True, overwrite_output=True)
            
            # Update task progress
            update_task_status(db, task_id, "in_progress", progress=0.2)
            
            # Load WhisperX model
            # This is a simplified placeholder - in a real implementation, we would:
            # 1. Import and use the actual WhisperX library
            # 2. Perform transcription with word-level timestamps
            # 3. Implement diarization with Pyannote
            # 4. Align the transcription with speaker information
            
            # Simulate transcription processing
            logger.info(f"Processing file {file_name} with WhisperX")
            with session_scope() as db:
                update_task_status(db, task_id, "in_progress", progress=0.5)
            
            # Get audio duration (placeholder - we would actually use ffprobe to get this)
            duration = 60.0  # Simulated 60-second duration
            
            # Use WhisperX for transcription
            import whisperx
            from whisperx.utils import get_device
            
            # Determine device for transcription
            device = get_device("cuda" if torch.cuda.is_available() else "cpu")
            logger.info(f"Using device: {device} for transcription")
            
            # Load the WhisperX model
            model = whisperx.load_model(settings.WHISPER_MODEL, device)
            
            # Transcribe the audio
            logger.info(f"Starting transcription for file {media_file.filename}")
            result = model.transcribe(audio_path, batch_size=16)
            segments = result["segments"]
            logger.info(f"Transcription completed with {len(segments)} segments")
            
            # Update task progress
            update_task_status(db, task_id, "in_progress", progress=0.7)
            
            # Use Pyannote for speaker diarization
            from pyannote.audio import Pipeline
            import torch
            from pyannote.audio.pipelines.speaker_verification import PretrainedSpeakerEmbedding
            
            logger.info(f"Starting speaker diarization for file {media_file.filename}")
            
            # Load the diarization pipeline
            diarization_pipeline = Pipeline.from_pretrained(
                settings.DIARIZATION_MODEL,
                use_auth_token=settings.HF_TOKEN
            )
            
            # Run diarization
            diarization = diarization_pipeline(audio_path)
            
            # Initialize speaker embedding model
            embedding_model = PretrainedSpeakerEmbedding(
                settings.SPEAKER_EMBEDDING_MODEL,
                use_auth_token=settings.HF_TOKEN,
                device=torch.device("cuda" if torch.cuda.is_available() else "cpu")
            )
            
            # Extract speaker embeddings
            speaker_embeddings = {}
            for speaker in diarization.speakers():
                # Get all segments for this speaker
                segments = [(s.start, s.end) for s in diarization.label_timeline(speaker).support()]
                
                # Get audio samples for each segment
                from pyannote.core import Segment
                import librosa
                
                speaker_samples = []
                audio_samples, sample_rate = librosa.load(audio_path, sr=16000)
                
                # Collect samples for all segments of this speaker
                for start, end in segments:
                    segment = Segment(start, end)
                    speaker_slice = diarization_pipeline.crop(audio_samples, segment, mode="loose")
                    speaker_samples.append(speaker_slice)
                
                if speaker_samples:
                    # Concatenate all samples
                    import numpy as np
                    all_samples = np.concatenate(speaker_samples)
                    
                    # Extract embedding
                    embedding = embedding_model(all_samples[None])
                    speaker_embeddings[speaker] = embedding[0].cpu().numpy()
            
            # Map diarization results to transcript segments
            logger.info(f"Aligning diarization with transcript for {len(segments)} segments")
            
            # Create a mapping from diarization speakers to database speakers
            speaker_mapping = {}
            
            # Process each segment from the transcript
            for i, segment in enumerate(segments):
                # Find the speaker for this segment based on the timestamp overlap
                best_speaker = None
                max_overlap = 0
                
                for speaker in diarization.labels():
                    # Get segments for this speaker
                    timeline = diarization.label_timeline(speaker)
                    
                    # Calculate overlap with current transcript segment
                    segment_start = segment['start']
                    segment_end = segment['end']
                    
                    for s in timeline.support():
                        overlap_start = max(segment_start, s.start)
                        overlap_end = min(segment_end, s.end)
                        overlap = max(0, overlap_end - overlap_start)
                        
                        if overlap > max_overlap:
                            max_overlap = overlap
                            best_speaker = speaker
                
                # Assign speaker to segment
                speaker_id = best_speaker if best_speaker else f"SPEAKER_{i % 2}"
                segment["speaker"] = speaker_id
                
                # Track unique speakers and ensure they exist in database
                if speaker_id not in speaker_mapping:
                    # Use session_scope for database operations
                    with session_scope() as db:
                        # Check if this speaker exists in the database for this user
                        speaker = db.query(Speaker).filter(
                            Speaker.user_id == user_id,
                            Speaker.name == speaker_id
                        ).first()
                        
                        if not speaker:
                            # Create new speaker with embeddings
                            embedding = speaker_embeddings.get(speaker_id)
                            embedding_json = json.dumps(embedding.tolist()) if embedding is not None else None
                            
                            speaker = Speaker(
                                user_id=user_id,
                                name=speaker_id,
                                embedding=embedding_json,
                                embedding_vector=json.dumps([float(i % 10) / 10.0 for i in range(10)])
                            )
                            db.add(speaker)
                            # commit handled by session_scope
                            
                            # In production, we would add to OpenSearch:
                            # add_speaker_embedding(speaker.id, speaker.name, embedding_vector)
                        
                        speaker_mapping[speaker_id] = speaker.id
            
            # Save transcript segments to database
            logger.info(f"Saving {len(segments)} transcript segments to database")
            with session_scope() as db:
                for segment in segments:
                    db_segment = TranscriptSegment(
                        media_file_id=file_id,
                        speaker_id=speaker_mapping.get(segment["speaker"]),
                        start_time=segment["start"],
                        end_time=segment["end"],
                        text=segment["text"]
                    )
                    db.add(db_segment)
            
            # Add speaker embeddings to OpenSearch for speaker identification
            for speaker_id, embedding in speaker_embeddings.items():
                if speaker_id in speaker_mapping:
                    add_speaker_embedding(
                        speaker_mapping[speaker_id],  # Database ID of speaker
                        speaker_id,  # Name of speaker
                        embedding.tolist()  # Speaker embedding vector
                    )
            
            # Update task progress
            update_task_status(db, task_id, "in_progress", progress=0.9)
            
            # Update media file with metadata
            media_file.duration = duration
            media_file.language = "en"  # In production, this would come from Whisper
            media_file.status = "completed"
            
            # In production, we would index in OpenSearch:
            # full_transcript = " ".join(segment["text"] for segment in simulated_segments)
            # index_transcript(media_file.id, media_file.user_id, full_transcript, 
            #                  list(speaker_mapping.keys()), media_file.filename)
            
            # Commit all changes
            db.commit()
            
            # Trigger summarization task
            from app.tasks.summarization import summarize_transcript_task
            summarize_transcript_task.delay(file_id)
            
            # Trigger analytics task
            from app.tasks.analytics import analyze_transcript_task
            analyze_transcript_task.delay(file_id)
            
            # Update task as completed
            update_task_status(db, task_id, "completed", progress=1.0, completed=True)
            
            logger.info(f"Successfully processed file {media_file.filename}")
            return {"status": "success", "file_id": file_id}
            
        finally:
            # Clean up temporary files
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                if is_video and os.path.exists(audio_path):
                    os.unlink(audio_path)
            except Exception as e:
                logger.error(f"Error cleaning up temporary files: {e}")
    
    except Exception as e:
        # Handle errors
        logger.error(f"Error processing file {file_id}: {str(e)}")
        
        # Update media file status with session_scope
        with session_scope() as db:
            try:
                update_media_file_status(db, file_id, "error")
            except Exception as update_err:
                logger.error(f"Error updating media file status: {update_err}")
        
        # Update task status with session_scope
        with session_scope() as db:
            try:
                update_task_status(db, task_id, "failed", error_message=str(e), completed=True)
            except Exception as update_err:
                logger.error(f"Error updating task status: {update_err}")
            
        return {"status": "error", "message": str(e)}


@celery_app.task(name="extract_audio")
def extract_audio_task(file_id: int, output_format: str = "wav"):
    """
    Extract audio from a video file
    
    Args:
        file_id: Database ID of the MediaFile
        output_format: Output audio format (default: wav)
    """
    try:
        # Use session_scope to manage DB session properly
        with session_scope() as db:
            # Get media file from database using get_refreshed_object for proper session binding
            media_file = get_refreshed_object(db, MediaFile, file_id)
            if not media_file:
                logger.error(f"Media file with ID {file_id} not found")
                return {"status": "error", "message": f"Media file with ID {file_id} not found"}
            
            # Store needed properties before session closes
            user_id = media_file.user_id
            storage_path = media_file.storage_path
            filename = media_file.filename
        
        # Download file from MinIO outside of DB session
        file_data, file_size, content_type = download_file(storage_path)
        
        # Check if it's a video file
        if not content_type.startswith('video/'):
            return {"status": "error", "message": "Not a video file"}
        
        # Create temporary file for video
        video_suffix = Path(filename).suffix
        with tempfile.NamedTemporaryFile(suffix=video_suffix, delete=False) as temp_video:
            temp_video.write(file_data.read())
            video_path = temp_video.name
        
        try:
            # Generate output audio filename
            audio_filename = f"{Path(filename).stem}.{output_format}"
            audio_storage_path = f"user_{user_id}/file_{file_id}/audio/{audio_filename}"
            
            # Create temporary file for audio
            with tempfile.NamedTemporaryFile(suffix=f".{output_format}", delete=False) as temp_audio:
                audio_path = temp_audio.name
            
            # Extract audio using ffmpeg
            ffmpeg.input(video_path).output(audio_path).run(quiet=True, overwrite_output=True)
            
            # Upload audio file to MinIO
            with open(audio_path, 'rb') as audio_file:
                audio_data = audio_file.read()
                
            from app.services.minio_service import upload_file
            upload_file(
                file_content=io.BytesIO(audio_data),
                file_size=os.path.getsize(audio_path),
                object_name=audio_storage_path,
                content_type=f"audio/{output_format}"
            )
            
            # Update task status with session_scope
            with session_scope() as db:
                # Update the media file to include the audio path
                media_file = get_refreshed_object(db, MediaFile, file_id)
                if media_file:
                    # Could store audio path if needed
                    # media_file.audio_path = audio_storage_path
                    logger.info(f"Audio extraction completed for file {file_id}")
            
            return {
                "status": "success", 
                "file_id": file_id,
                "audio_path": audio_storage_path
            }
            
        finally:
            # Clean up temporary files
            try:
                if os.path.exists(video_path):
                    os.unlink(video_path)
                if os.path.exists(audio_path):
                    os.unlink(audio_path)
            except Exception as e:
                logger.error(f"Error cleaning up temporary files: {e}")
    
    except Exception as e:
        # Handle errors
        logger.error(f"Error extracting audio from file {file_id}: {str(e)}")
        return {"status": "error", "message": str(e)}
