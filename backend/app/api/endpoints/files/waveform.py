"""
Audio waveform generation endpoints.

This module provides endpoints for generating waveform visualization data
from audio and video files for use in the frontend player interface.
"""

import logging
import os
import tempfile
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.user import User
from app.models.media import MediaFile
from app.api.endpoints.auth import get_current_active_user
from app.services.minio_service import download_file
from .crud import get_media_file_by_id
from app.tasks.waveform_generation import trigger_waveform_generation
from app.tasks.transcription.waveform_generator import WaveformGenerator

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{file_id}/waveform")
async def get_audio_waveform(
    file_id: int,
    samples: int = Query(1000, description="Number of samples to return", ge=100, le=10000),
    refresh_cache: bool = Query(False, description="Force refresh of cached waveform data"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Generate waveform visualization data for an audio or video file.
    Uses caching to improve performance for repeated requests.
    
    Args:
        file_id: ID of the media file
        samples: Number of waveform samples to return (100-10000)
        refresh_cache: Force refresh of cached waveform data
        
    Returns:
        JSON response with waveform data and metadata
    """
    try:
        # Get the media file and verify user access
        db_file = get_media_file_by_id(db, file_id, current_user.id)
        
        # Check if file has audio content
        if not db_file.content_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File content type unknown"
            )
        
        # Check if file is audio or video (both can have audio tracks)
        is_audio_video = (
            db_file.content_type.startswith('audio/') or 
            db_file.content_type.startswith('video/')
        )
        
        if not is_audio_video:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File must be audio or video format for waveform generation"
            )
        
        # Check if file processing is complete
        if db_file.status != "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File is not ready for waveform generation (status: {db_file.status})"
            )
        
        # Check for cached waveform data (prioritize cached data)
        cache_key = f"waveform_{samples}"
        if not refresh_cache and db_file.waveform_data and isinstance(db_file.waveform_data, dict):
            cached_data = db_file.waveform_data.get(cache_key)
            if cached_data and isinstance(cached_data, dict) and cached_data.get('waveform'):
                # Check if cached data was generated with old algorithm (missing new fields)
                if 'extracted_samples' not in cached_data or 'expected_duration' not in cached_data:
                    logger.info(f"Cached waveform data for file {file_id} is outdated, regenerating")
                    # Continue to regeneration below
                else:
                    # Return cached data with file_id
                    result = cached_data.copy()
                    result['file_id'] = file_id
                    result['cached'] = True
                    return result
        
        
        # Generate new waveform data
        with tempfile.NamedTemporaryFile(delete=False, suffix='.tmp') as temp_file:
            try:
                # Download file content
                file_content_io, _, _ = download_file(db_file.storage_path)
                
                # Write to temporary file
                while True:
                    chunk = file_content_io.read(8192)
                    if not chunk:
                        break
                    temp_file.write(chunk)
                
                temp_file_path = temp_file.name
                
                # Extract waveform data using the WaveformGenerator
                waveform_generator = WaveformGenerator()
                waveform_data = waveform_generator._extract_single_waveform(temp_file_path, samples)
                
                if not waveform_data:
                    raise ValueError("Failed to extract waveform data")
                
                # Cache the waveform data in database
                if not db_file.waveform_data:
                    db_file.waveform_data = {}
                db_file.waveform_data[cache_key] = waveform_data.copy()
                db.commit()
                
                # Add file ID to response
                waveform_data['file_id'] = file_id
                waveform_data['cached'] = False
                
                logger.info(f"Generated and cached waveform for file {file_id}: {len(waveform_data['waveform'])} samples")
                
                return waveform_data
                
            finally:
                # Clean up temporary file
                try:
                    if os.path.exists(temp_file_path):
                        os.unlink(temp_file_path)
                except Exception as cleanup_error:
                    logger.warning(f"Failed to cleanup temp file {temp_file_path}: {cleanup_error}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating waveform for file {file_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate waveform: {str(e)}"
        )


@router.get("/{file_id}/waveform/peaks")
async def get_audio_waveform_peaks(
    file_id: int,
    width: int = Query(1000, description="Target width in pixels", ge=100, le=10000),
    height: int = Query(100, description="Target height in pixels", ge=50, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Generate waveform peaks data optimized for a specific display size.
    This endpoint provides more detailed control over the waveform visualization.
    
    Args:
        file_id: ID of the media file
        width: Target display width in pixels
        height: Target display height in pixels
        
    Returns:
        JSON response with peaks data optimized for display
    """
    try:
        # Get the media file and verify user access
        db_file = get_media_file_by_id(db, file_id, current_user.id)
        
        # Check file type and status (same as main waveform endpoint)
        if not db_file.content_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File content type unknown"
            )
        
        is_audio_video = (
            db_file.content_type.startswith('audio/') or 
            db_file.content_type.startswith('video/')
        )
        
        if not is_audio_video:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File must be audio or video format"
            )
        
        if db_file.status != "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File is not ready (status: {db_file.status})"
            )
        
        # Calculate samples based on width (2 samples per pixel for better resolution)
        target_samples = min(width * 2, 4000)
        
        
        # Download and process file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.tmp') as temp_file:
            try:
                file_content_io, _, _ = download_file(db_file.storage_path)
                
                while True:
                    chunk = file_content_io.read(8192)
                    if not chunk:
                        break
                    temp_file.write(chunk)
                
                temp_file_path = temp_file.name
                
                # Extract waveform data using the WaveformGenerator
                waveform_generator = WaveformGenerator()
                waveform_data = waveform_generator._extract_single_waveform(temp_file_path, target_samples)
                
                if not waveform_data:
                    raise ValueError("Failed to extract waveform data")
                
                # Convert waveform data to height-based peaks
                peaks = []
                for sample in waveform_data['waveform']:
                    # Convert from 0-255 range to 0-height range
                    peak_height = int((sample / 255.0) * height)
                    peaks.append(peak_height)
                
                return {
                    "peaks": peaks,
                    "duration": waveform_data['duration'],
                    "width": width,
                    "height": height,
                    "samples": len(peaks),
                    "sample_rate": waveform_data['sample_rate'],
                    "file_id": file_id
                }
                
            finally:
                try:
                    if os.path.exists(temp_file_path):
                        os.unlink(temp_file_path)
                except Exception as cleanup_error:
                    logger.warning(f"Failed to cleanup temp file {temp_file_path}: {cleanup_error}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating waveform peaks for file {file_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate waveform peaks: {str(e)}"
        )


@router.post("/{file_id}/waveform/generate")
async def generate_waveform_for_file(
    file_id: int,
    force_regenerate: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Generate waveform data for a specific file.
    Can be used to create missing waveform data or force regeneration.
    """
    try:
        # Verify user access to the file
        db_file = get_media_file_by_id(db, file_id, current_user.id)
        
        # Check if file is audio/video
        is_audio_video = (
            db_file.content_type.startswith('audio/') or 
            db_file.content_type.startswith('video/')
        )
        
        if not is_audio_video:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File must be audio or video format"
            )
        
        # Trigger waveform generation task for this specific file
        task_id = trigger_waveform_generation(file_id=file_id, skip_existing=not force_regenerate)
        
        action = "regeneration" if force_regenerate else "generation"
        return {
            "success": True,
            "message": f"Waveform {action} started for file {file_id}",
            "task_id": task_id,
            "file_id": file_id,
            "force_regenerate": force_regenerate
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering waveform generation for file {file_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start waveform generation: {str(e)}"
        )


@router.post("/waveforms/generate")
async def generate_waveforms_for_files(
    force_regenerate: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Generate waveform data for all eligible files that don't have it.
    Only admin users can trigger this operation.
    """
    # Check if user is admin
    if current_user.role not in ["admin", "superuser"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin users can trigger bulk waveform generation"
        )
    
    try:
        from app.models.media import FileStatus
        
        # Get count of files that would be processed
        query = db.query(MediaFile).filter(
            MediaFile.status == FileStatus.COMPLETED
        ).filter(
            MediaFile.content_type.like('audio/%') | 
            MediaFile.content_type.like('video/%')
        )
        
        if not force_regenerate:
            query = query.filter(MediaFile.waveform_data.is_(None))
        
        files_to_process = query.all()
        
        if not files_to_process:
            return {
                "success": True,
                "message": "No files need waveform generation",
                "files_to_process": 0,
                "task_id": None
            }
        
        # Trigger the background task
        task_id = trigger_waveform_generation(
            file_id=None, 
            skip_existing=not force_regenerate
        )
        
        logger.info(f"User {current_user.id} triggered waveform generation for {len(files_to_process)} files")
        
        return {
            "success": True,
            "message": f"Waveform generation started for {len(files_to_process)} files",
            "files_to_process": len(files_to_process),
            "task_id": task_id,
            "force_regenerate": force_regenerate
        }
        
    except Exception as e:
        logger.error(f"Error triggering waveform generation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start waveform generation: {str(e)}"
        )


@router.get("/waveforms/status")
def get_waveform_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get status of waveform data across all files.
    Shows how many files have/don't have waveform data.
    """
    # Check if user is admin
    if current_user.role not in ["admin", "superuser"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin users can view waveform status"
        )
    
    try:
        from app.models.media import FileStatus
        
        # Get counts for audio/video files
        total_media_files = db.query(MediaFile).filter(
            MediaFile.content_type.like('audio/%') | 
            MediaFile.content_type.like('video/%')
        ).count()
        
        completed_media_files = db.query(MediaFile).filter(
            MediaFile.status == FileStatus.COMPLETED
        ).filter(
            MediaFile.content_type.like('audio/%') | 
            MediaFile.content_type.like('video/%')
        ).count()
        
        files_with_waveforms = db.query(MediaFile).filter(
            MediaFile.status == FileStatus.COMPLETED
        ).filter(
            MediaFile.content_type.like('audio/%') | 
            MediaFile.content_type.like('video/%')
        ).filter(
            MediaFile.waveform_data.isnot(None)
        ).count()
        
        files_without_waveforms = completed_media_files - files_with_waveforms
        
        return {
            "total_media_files": total_media_files,
            "completed_media_files": completed_media_files,
            "files_with_waveforms": files_with_waveforms,
            "files_without_waveforms": files_without_waveforms,
            "waveform_coverage_percentage": round(
                (files_with_waveforms / completed_media_files * 100) if completed_media_files > 0 else 0,
                1
            )
        }
        
    except Exception as e:
        logger.error(f"Error getting waveform status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get waveform status: {str(e)}"
        )