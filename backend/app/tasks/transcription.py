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
import subprocess
import sys
import uuid

# Try to import ExifTool - will be installed with pyexiftool
try:
    import exiftool
except ImportError:
    logging.warning("exiftool not found. Video metadata extraction will be limited.")

from app.core.celery import celery_app
from app.db.base import SessionLocal
from app.models.media import MediaFile, TranscriptSegment, Speaker, Task, Analytics, FileStatus
from app.services.minio_service import download_file, upload_file
from app.services.opensearch_service import index_transcript, add_speaker_embedding
from app.core.config import settings
from app.api.websockets import send_notification
from app.db.session_utils import session_scope, get_refreshed_object, refresh_session_object

# Setup logging
logger = logging.getLogger(__name__)

# Constants for models
MODELS_DIR = Path(settings.MODEL_BASE_DIR)

# Ensure models directory exists
if not os.path.exists(MODELS_DIR):
    os.makedirs(MODELS_DIR, exist_ok=True)

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
    user_id = None
    file_path = None
    file_name = None
    content_type = None
    
    try:
        # Step 1: Update file status to processing and get user_id
        with session_scope() as db:
            # Get the media file with a session-safe method that handles detached objects
            media_file = get_refreshed_object(db, MediaFile, file_id)
            if not media_file:
                logger.error(f"Media file with ID {file_id} not found")
                return {"status": "error", "message": f"Media file with ID {file_id} not found"}
            
            # Get all needed data before the session is committed
            user_id = media_file.user_id
            file_path = media_file.storage_path
            file_name = media_file.filename
            content_type = media_file.content_type
            
            # Update status
            media_file.status = FileStatus.PROCESSING
            db.commit()
            
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
            
        # Download file from MinIO to a temporary file
        logger.info(f"Downloading file {file_path}")
        file_data, file_size, content_type = download_file(file_path)
        
        # Determine file extension based on content type
        file_ext = os.path.splitext(file_name)[1]
        if not file_ext and content_type:
            # Map MIME types to extensions if needed
            mime_to_ext = {
                "audio/mpeg": ".mp3",
                "audio/mp3": ".mp3",
                "audio/wav": ".wav",
                "audio/wave": ".wav",
                "audio/x-wav": ".wav",
                "audio/webm": ".webm",
                "audio/ogg": ".ogg",
                "video/mp4": ".mp4",
                "video/webm": ".webm",
                "video/ogg": ".ogg"
            }
            file_ext = mime_to_ext.get(content_type, ".mp4")
            
        # Ensure WhisperX models directory exists
        whisper_model_name = "medium.en"
        whisperx_model_directory = os.path.join(MODELS_DIR, "whisperx")
        os.makedirs(whisperx_model_directory, exist_ok=True)
        
        # Log model information
        logger.info(f"Using WhisperX with model: {whisper_model_name}")
        logger.info(f"Model directory: {whisperx_model_directory}")
        
        # Create temporary directory for processing
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create temporary file path
            temp_file_path = os.path.join(temp_dir, f"input{file_ext}")
            temp_audio_path = os.path.join(temp_dir, "audio.wav")
            
            # Save the downloaded file to the temporary path
            with open(temp_file_path, "wb") as f:
                f.write(file_data.read())
            
            # Extract detailed metadata from the video file using ExifTool
            if content_type.startswith("video/"):
                try:
                    logger.info(f"Extracting metadata with ExifTool from {temp_file_path}")
                    video_metadata = {}
                    
                    # Try to use Python ExifTool library if available
                    if "exiftool" in sys.modules:
                        try:
                            with exiftool.ExifToolHelper() as et:
                                metadata_list = et.get_metadata(temp_file_path)
                                if metadata_list:
                                    video_metadata = metadata_list[0]
                                    
                                    # Extract important video properties
                                    with session_scope() as db:
                                        media_file = get_refreshed_object(db, MediaFile, file_id)
                                        if media_file:
                                            # Common ExifTool fields for video files
                                            media_file.width = video_metadata.get("File:ImageWidth") or video_metadata.get("QuickTime:ImageWidth")
                                            media_file.height = video_metadata.get("File:ImageHeight") or video_metadata.get("QuickTime:ImageHeight")
                                            media_file.frame_rate = video_metadata.get("QuickTime:VideoFrameRate")
                                            media_file.codec = video_metadata.get("QuickTime:CompressorID")
                                            media_file.bit_rate = video_metadata.get("QuickTime:BitRate")
                                            
                                            # Store full metadata as JSON
                                            media_file.metadata = video_metadata
                                            db.commit()
                                            
                                    logger.info(f"Metadata extracted: {video_metadata.get('File:FileName')} - "
                                             f"{video_metadata.get('File:ImageWidth')}x{video_metadata.get('File:ImageHeight')} "
                                             f"@ {video_metadata.get('QuickTime:VideoFrameRate')} fps")
                        except Exception as et_err:
                            logger.warning(f"Error using Python ExifTool: {et_err}")
                            
                    # Fallback to command-line ExifTool if the Python library fails
                    if not video_metadata:
                        try:
                            # Try to extract metadata using subprocess
                            exif_process = subprocess.run(
                                ["exiftool", "-json", "-n", temp_file_path],
                                capture_output=True,
                                text=True,
                                check=True
                            )
                            
                            if exif_process.stdout:
                                try:
                                    metadata_list = json.loads(exif_process.stdout)
                                    if metadata_list:
                                        video_metadata = metadata_list[0]
                                        
                                        # Extract important video properties
                                        with session_scope() as db:
                                            media_file = get_refreshed_object(db, MediaFile, file_id)
                                            if media_file:
                                                # Common exiftool fields for video files
                                                media_file.width = video_metadata.get("ImageWidth")
                                                media_file.height = video_metadata.get("ImageHeight")
                                                media_file.frame_rate = video_metadata.get("VideoFrameRate")
                                                media_file.codec = video_metadata.get("CompressorID")
                                                media_file.bit_rate = video_metadata.get("AvgBitrate")
                                                
                                                # Store full metadata as JSON
                                                media_file.metadata = video_metadata
                                                db.commit()
                                        
                                        logger.info(f"Metadata extracted via subprocess: {video_metadata.get('FileName')} - "
                                                 f"{video_metadata.get('ImageWidth')}x{video_metadata.get('ImageHeight')} "
                                                 f"@ {video_metadata.get('VideoFrameRate')} fps")
                                except json.JSONDecodeError as jde:
                                    logger.warning(f"Error decoding ExifTool JSON output: {jde}")
                        except (subprocess.SubprocessError, FileNotFoundError) as sp_err:
                            logger.warning(f"Error running ExifTool subprocess: {sp_err}")
                except Exception as e:
                    logger.warning(f"Error extracting video metadata: {e}")
                    # Continue processing even if metadata extraction fails
            
            try:
                # For video files, extract audio first
                if content_type.startswith("video/"):
                    logger.info(f"Extracting audio from video file {temp_file_path}")
                    # Use ffmpeg to extract audio
                    ffmpeg.input(temp_file_path).output(temp_audio_path, acodec="pcm_s16le", ar="16000", ac=1).run(quiet=True)
                    audio_file_path = temp_audio_path
                else:
                    # For audio files, convert to WAV format if needed
                    if not file_ext.lower() == ".wav":
                        logger.info(f"Converting audio to WAV format")
                        ffmpeg.input(temp_file_path).output(temp_audio_path, acodec="pcm_s16le", ar="16000", ac=1).run(quiet=True)
                        audio_file_path = temp_audio_path
                    else:
                        audio_file_path = temp_file_path
                
                # Update task status
                with session_scope() as db:
                    update_task_status(db, task_id, "in_progress", progress=0.3)
                
                # Import WhisperX for transcription, alignment, and diarization
                try:
                    import whisperx
                    import gc
                    import torch
                except ImportError:
                    logger.error("WhisperX is not installed. Please install it with 'pip install whisperx'.")
                    with session_scope() as db:
                        update_task_status(db, task_id, "failed", error_message="WhisperX not installed", completed=True)
                        media_file = get_refreshed_object(db, MediaFile, file_id)
                        if media_file:
                            media_file.status = FileStatus.ERROR
                    return {"status": "error", "message": "WhisperX not installed"}
                
                # Set device and compute type
                device = "cuda" if torch.cuda.is_available() else "cpu"
                compute_type = "float16" if device == "cuda" else "float32"
                download_root = os.path.join(MODELS_DIR, "whisperx")
                batch_size = 16  # Reduce if low on GPU memory
                
                # Step 1: Transcribe with WhisperX (utilizing faster-whisper under the hood)
                logger.info(f"Loading WhisperX model: {whisper_model_name}...")
                model = whisperx.load_model(
                    whisper_model_name,
                    device,
                    compute_type=compute_type,
                    download_root=download_root,
                    language="en"  # Always use English for consistent results
                )
                
                # Load audio
                logger.info(f"Transcribing audio file: {audio_file_path}")
                audio = whisperx.load_audio(audio_file_path)
                
                # Transcribe with batching for speed
                transcription_result = model.transcribe(
                    audio,
                    batch_size=batch_size,
                    task="translate"  # Always translate to English
                )
                
                logger.info(f"Initial transcription completed with {len(transcription_result['segments'])} segments")
                
                # Free GPU memory if needed
                if device == "cuda":
                    gc.collect()
                    torch.cuda.empty_cache()
                    del model
                
                # Update task progress
                with session_scope() as db:
                    update_task_status(db, task_id, "in_progress", progress=0.4)
                
                # Step 2: Align whisper output with WAV2VEC2 for accurate word-level timestamps
                logger.info("Loading alignment model...")
                align_model, align_metadata = whisperx.load_align_model(
                    language_code=transcription_result["language"],
                    device=device,
                    model_name=None  # Use default model for the language
                )
                
                logger.info("Aligning transcription for precise word timings...")
                aligned_result = whisperx.align(
                    transcription_result["segments"],
                    align_model,
                    align_metadata,
                    audio,
                    device,
                    return_char_alignments=False
                )
                
                # Free GPU memory if needed
                if device == "cuda":
                    gc.collect()
                    torch.cuda.empty_cache()
                    del align_model
                
                # Update task progress
                with session_scope() as db:
                    update_task_status(db, task_id, "in_progress", progress=0.6)
                
                # Step 3: Perform speaker diarization
                logger.info("Performing speaker diarization...")
                hf_token = settings.HUGGINGFACE_TOKEN or None
                
                # Set diarization parameters
                diarize_params = {}
                diarize_params["max_speakers"] = 10
                diarize_params["min_speakers"] = 1
                
                # Create diarization pipeline
                diarize_model = whisperx.DiarizationPipeline(
                    use_auth_token=hf_token,
                    device=device
                )
                
                # Run diarization
                diarize_segments = diarize_model(audio, **diarize_params)
                
                # Assign speakers to words in the aligned result
                logger.info("Assigning speaker labels to transcript...")
                result = whisperx.assign_word_speakers(diarize_segments, aligned_result)
                
                # Process the diarized result to store in database
                logger.info("Processing diarized result for database storage...")
                segments = []
                speaker_mapping = {}
                
                # First, create or get speakers in the database for each unique speaker ID
                unique_speakers = set()
                
                # Normalize speaker labels first to ensure consistent format (SPEAKER_XX)
                for segment in result["segments"]:
                    if "speaker" in segment and segment["speaker"] is not None:
                        # Ensure speaker labels follow the SPEAKER_XX format
                        if not segment["speaker"].startswith("SPEAKER_"):
                            segment["speaker"] = f"SPEAKER_{segment['speaker']}"
                        unique_speakers.add(segment["speaker"])
                
                # Store each unique speaker in the database
                for speaker_id in unique_speakers:
                    # Skip if already processed
                    if speaker_id in speaker_mapping:
                        continue
                        
                    with session_scope() as db:
                        # Check if speaker already exists for this user
                        speaker = db.query(Speaker).filter(
                            Speaker.user_id == user_id,
                            Speaker.name == speaker_id
                        ).first()
                        
                        # Create new speaker if needed
                        if not speaker:
                            speaker = Speaker(
                                user_id=user_id,
                                name=speaker_id,
                                uuid=str(uuid.uuid4())
                            )
                            db.add(speaker)
                            db.commit()
                            
                        # Store speaker ID mapping
                        speaker_mapping[speaker_id] = speaker.id
                
                # Process segments from WhisperX result
                logger.info(f"Converting {len(result['segments'])} segments to database format...")
                for i, segment in enumerate(result["segments"]):
                    # Get start and end time
                    segment_start = segment["start"]
                    segment_end = segment["end"]
                    segment_text = segment["text"]
                    
                    # Get speaker ID (WhisperX has already assigned speakers)
                    speaker_id = segment.get("speaker")
                    
                    # Ensure consistent speaker format
                    if speaker_id is None:
                        speaker_id = f"SPEAKER_{i % 2}" # Fallback if no speaker assigned
                    elif not speaker_id.startswith("SPEAKER_"):
                        speaker_id = f"SPEAKER_{speaker_id}"
                    
                    # Get database ID for this speaker
                    speaker_db_id = speaker_mapping.get(speaker_id)
                    if not speaker_db_id and speaker_id not in speaker_mapping:
                            # Create speaker if needed
                            with session_scope() as db:
                                speaker = Speaker(
                                    user_id=user_id,
                                    name=speaker_id,
                                    uuid=str(uuid.uuid4())
                                )
                                db.add(speaker)
                            db.commit()
                            speaker_mapping[speaker_id] = speaker.id
                            speaker_db_id = speaker.id
                    
                    # Get words with timestamps (important for highlighting during playback)
                    words_data = []
                    if "words" in segment:
                        for word in segment["words"]:
                            if "start" in word and "end" in word:
                                words_data.append({
                                    "word": word.get("word", ""),
                                    "start": word.get("start", 0.0),
                                    "end": word.get("end", 0.0),
                                    "score": word.get("score", 1.0)
                                })
                    
                    # Add segment to our processed list
                    segments.append({
                        "start": segment_start,
                        "end": segment_end,
                        "text": segment_text,
                        "speaker": speaker_id,
                        "speaker_id": speaker_db_id,
                        "words": words_data,
                        "confidence": segment.get("confidence", 1.0)
                    })
                
                # Calculate the total duration from the last segment end time
                duration = segments[-1]["end"] if segments else 0.0
                
                logger.info(f"Transcription completed with {len(segments)} segments and duration {duration}s")
                
                # Save transcription to database
                with session_scope() as db:
                    media_file = get_refreshed_object(db, MediaFile, file_id)
                    if not media_file:
                        logger.error(f"Media file with ID {file_id} not found when saving transcription")
                        return {"status": "error", "message": f"Media file not found"}
                    
                    # Add transcript segments to database
                    for i, segment in enumerate(segments):
                        # Check if speaker exists or create a new one
                        speaker_label = segment["speaker"]
                        
                        # Try to find an existing speaker with the same label
                        speaker = db.query(Speaker).filter_by(name=speaker_label, user_id=user_id).first()
                        
                        if not speaker:
                            try:
                                # Create a new speaker with a unique UUID
                                # This UUID will be used to track the same speaker across different videos
                                speaker_uuid = str(uuid.uuid4())
                                
                                # Extract numerical ID from speaker label (e.g., SPEAKER_01 -> 01)
                                # This helps with display in the UI
                                speaker_number = ''
                                if '_' in speaker_label:
                                    try:
                                        speaker_number = speaker_label.split('_')[1]
                                    except IndexError:
                                        speaker_number = speaker_label
                                
                                # Ensure the UUID is never null
                                if not speaker_uuid:
                                    speaker_uuid = str(uuid.uuid4())
                                    logger.warning(f"Generated fallback UUID for speaker {speaker_label}: {speaker_uuid}")
                                
                                speaker = Speaker(
                                    name=speaker_label,
                                    display_name=None,  # Will be set by user later
                                    uuid=speaker_uuid,
                                    user_id=user_id,
                                    verified=False
                                )
                                db.add(speaker)
                                db.flush()  # Get the ID without committing
                                logger.info(f"Created new speaker: {speaker_label} with UUID: {speaker_uuid}")
                            except Exception as e:
                                logger.error(f"Error creating speaker {speaker_label}: {str(e)}")
                                # Create a fallback speaker with guaranteed UUID
                                speaker_uuid = str(uuid.uuid4())
                                speaker = Speaker(
                                    name=speaker_label,
                                    display_name=None,
                                    uuid=speaker_uuid,
                                    user_id=user_id,
                                    verified=False
                                )
                                db.add(speaker)
                                db.flush()
                        db_segment = TranscriptSegment(
                            media_file_id=file_id,
                            start_time=segment["start"],
                            end_time=segment["end"],
                            text=segment["text"],
                            speaker_id=speaker.id,
                            # confidence=segment["confidence"],


                        )
                        db.add(db_segment)
                    
                    # Update media file with transcription metadata
                    media_file.duration = duration
                    media_file.language = result.get("language", "en")
                    media_file.status = FileStatus.COMPLETED
                    media_file.transcription_completed_at = datetime.datetime.now()
                    
                    logger.info(f"Saved {len(segments)} transcript segments to database")
                    
                    # Update task progress
                    update_task_status(db, task_id, "in_progress", progress=0.8)
                # Index transcript in OpenSearch for search functionality
                try:
                    logger.info("Indexing transcript in search database...")
                    # Create a clean version of segments for indexing
                    index_segments = []
                    for segment in segments:
                        index_segments.append({
                            "start": segment["start"],
                            "end": segment["end"],
                            "text": segment["text"],
                            "speaker": segment["speaker"]
                        })
                    
                    # Generate full transcript text for search indexing
                    full_transcript = " ".join([segment["text"] for segment in segments])
                    
                    # Get unique speakers
                    speaker_names = list(set([segment["speaker"] for segment in segments]))
                    
                    # Get the file title from the database
                    with session_scope() as db:
                        media_file = get_refreshed_object(db, MediaFile, file_id)
                        file_title = media_file.filename if media_file else f"File {file_id}"
                    
                    # Index in OpenSearch
                    index_transcript(file_id, user_id, full_transcript, speaker_names, file_title)
                    
                    # Complete task
                    with session_scope() as db:
                        update_task_status(db, task_id, "completed", progress=1.0, completed=True)
                        
                except Exception as e:
                    logger.warning(f"Error indexing transcript: {e}")
                    # Still mark as completed even if indexing fails
                    with session_scope() as db:
                        update_task_status(db, task_id, "completed", progress=1.0, completed=True)
                
                # Send WebSocket notification about completion with retry logic
                notification_success = False
                for retry in range(3):  # Try up to 3 times
                    try:
                        # Send the notification
                        asyncio.run(send_notification(
                            user_id, 
                            "transcription_status", 
                            {
                                "file_id": str(file_id),
                                "status": FileStatus.COMPLETED.value,
                                "message": "Transcription completed successfully",
                                "progress": 100
                            }
                        ))
                        notification_success = True
                        logger.info(f"Successfully sent completion notification for file {file_id} on try {retry+1}")
                        break  # Exit retry loop if successful
                    except Exception as e:
                        logger.warning(f"Failed to send completion notification (attempt {retry+1}/3): {e}")
                        if retry < 2:  # Don't sleep on the last attempt
                            import time
                            time.sleep(1)  # Short delay before retry
                
                # Even if notification failed, ensure the database is updated
                if not notification_success:
                    logger.warning("Websocket notification failed, ensuring database status is updated")
                    with session_scope() as db:
                        # Double-check media file status
                        media_file = get_refreshed_object(db, MediaFile, file_id)
                        if media_file and media_file.status != FileStatus.COMPLETED:
                            media_file.status = FileStatus.COMPLETED
                            media_file.transcription_completed_at = datetime.datetime.now()
                        # Double-check task status
                        task = db.query(Task).filter(Task.id == task_id).first()
                        if task and task.status != "completed":
                            task.status = "completed"
                            task.progress = 1.0
                            task.completed_at = datetime.datetime.now()
                
                # Return success result
                return {"status": "success", "file_id": file_id, "segments": len(segments)}
                
            except Exception as e:
                logger.error(f"Error processing audio: {str(e)}")
                with session_scope() as db:
                    update_task_status(db, task_id, "failed", error_message=f"Audio processing error: {str(e)}", completed=True)
                    media_file = get_refreshed_object(db, MediaFile, file_id)
                    if media_file:
                        media_file.status = FileStatus.ERROR
                return {"status": "error", "message": str(e)}
    
    except Exception as e:
        # Handle any errors
        logger.error(f"Error processing file {file_id}: {str(e)}")
        
        # Update status in database to indicate error
        try:
            with session_scope() as db:
                media_file = get_refreshed_object(db, MediaFile, file_id)
                if media_file:
                    media_file.status = FileStatus.ERROR
                
                update_task_status(db, task_id, "failed", error_message=str(e), completed=True)
                
            # Send error notification via WebSocket
            try:
                asyncio.run(send_notification(
                    user_id, 
                    "transcription_status", 
                    {
                        "file_id": str(file_id),
                        "status": FileStatus.ERROR.value,
                        "message": f"Transcription failed: {str(e)}",
                        "progress": 0
                    }
                ))
            except Exception as notif_err:
                logger.warning(f"Failed to send error notification: {notif_err}")
                
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
                
            # Upload the extracted audio file
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

@celery_app.task(name="analyze_transcript")
def analyze_transcript_task(file_id: int):
    """
    Analyze a transcript for additional metadata and insights
    
    Args:
        file_id: Database ID of the MediaFile to analyze
    """
    try:
        with session_scope() as db:
            # Get the media file
            media_file = get_refreshed_object(db, MediaFile, file_id)
            if not media_file:
                logger.error(f"Media file with ID {file_id} not found")
                return {"status": "error", "message": f"Media file with ID {file_id} not found"}
            
            # Get all transcript segments for this file
            segments = db.query(TranscriptSegment).filter(
                TranscriptSegment.media_file_id == file_id
            ).order_by(TranscriptSegment.segment_index).all()
            
            if not segments:
                logger.warning(f"No transcript segments found for file {file_id}")
                return {"status": "error", "message": "No transcript segments found"}
            
            # Combine all text for analysis
            full_text = " ".join([segment.text for segment in segments])
            
            # Create or update analytics record
            analytics = db.query(Analytics).filter(Analytics.media_file_id == file_id).first()
            if not analytics:
                analytics = Analytics(media_file_id=file_id)
                db.add(analytics)
            
            # Count words, speakers, and segments
            word_count = len(full_text.split())
            unique_speakers = len(set([segment.speaker_id for segment in segments]))
            
            # Update analytics record with results
            analytics.word_count = word_count
            analytics.speaker_count = unique_speakers
            analytics.segment_count = len(segments)
            
            db.commit()
            
            logger.info(f"Analytics completed for file {file_id}")
            return {"status": "success", "file_id": file_id}
            
    except Exception as e:
        logger.error(f"Error analyzing transcript for file {file_id}: {str(e)}")
        return {"status": "error", "message": str(e)}

@celery_app.task(name="summarize_transcript")
def summarize_transcript_task(file_id: int):
    """
    Generate a summary of a transcript
    
    Args:
        file_id: Database ID of the MediaFile to summarize
    """
    try:
        with session_scope() as db:
            # Get the media file
            media_file = get_refreshed_object(db, MediaFile, file_id)
            if not media_file:
                logger.error(f"Media file with ID {file_id} not found")
                return {"status": "error", "message": f"Media file with ID {file_id} not found"}
            
            # Get all transcript segments for this file
            segments = db.query(TranscriptSegment).filter(
                TranscriptSegment.media_file_id == file_id
            ).order_by(TranscriptSegment.segment_index).all()
            
            if not segments:
                logger.warning(f"No transcript segments found for file {file_id}")
                return {"status": "error", "message": "No transcript segments found"}
            
            # Combine all text for summarization
            full_text = " ".join([segment.text for segment in segments])
            
            # Implement text summarization
            # In a production environment, this would use a language model API
            # For now, use a simple extractive summarization approach
            from nltk.tokenize import sent_tokenize
            from nltk.corpus import stopwords
            from nltk.probability import FreqDist
            import nltk
            
            # Download necessary NLTK resources if they're not already available
            try:
                nltk.data.find('tokenizers/punkt')
            except LookupError:
                nltk.download('punkt')
            try:
                nltk.data.find('corpora/stopwords')
            except LookupError:
                nltk.download('stopwords')
                
            # Tokenize into sentences
            sentences = sent_tokenize(full_text)
            
            # Remove stop words and punctuation
            stop_words = set(stopwords.words('english'))
            words = [word.lower() for sentence in sentences 
                    for word in nltk.word_tokenize(sentence) 
                    if word.isalnum() and word.lower() not in stop_words]
            
            # Calculate word frequency
            word_frequencies = FreqDist(words)
            
            # Calculate sentence scores based on word frequency
            sentence_scores = {}
            for i, sentence in enumerate(sentences):
                for word in nltk.word_tokenize(sentence.lower()):
                    if word in word_frequencies:
                        if i in sentence_scores:
                            sentence_scores[i] += word_frequencies[word]
                        else:
                            sentence_scores[i] = word_frequencies[word]
            
            # Get top 3 sentences or fewer if there aren't enough
            num_summary_sentences = min(3, len(sentences))
            top_sentences = sorted(sentence_scores.items(), key=lambda x: x[1], reverse=True)[:num_summary_sentences]
            top_sentences = sorted(top_sentences, key=lambda x: x[0])  # Sort by position in text
            
            # Generate the summary
            summary = ' '.join([sentences[i] for i, _ in top_sentences])
            
            # If summary is empty (possible if processing failed), provide a simple summary
            if not summary.strip():
                summary = f"Transcript with {len(segments)} segments and approximately {len(full_text.split())} words."
            
            # Update the media file with the summary
            media_file.summary = summary
            db.commit()
            
            logger.info(f"Summarization completed for file {file_id}")
            return {"status": "success", "file_id": file_id, "summary": summary}
            
    except Exception as e:
        logger.error(f"Error summarizing transcript for file {file_id}: {str(e)}")
        return {"status": "error", "message": str(e)}
# Translation task is no longer needed as faster-whisper automatically translates to English
# The transcribe_audio_task uses the task="translate" parameter to ensure all transcripts are in English
