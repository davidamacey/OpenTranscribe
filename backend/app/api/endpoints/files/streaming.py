import io
import logging
import os

from fastapi import HTTPException
from fastapi import status
from fastapi.responses import StreamingResponse

from app.models.media import MediaFile
from app.services.minio_service import download_file
from app.services.minio_service import get_file_stream

logger = logging.getLogger(__name__)


def create_mock_response(db_file: MediaFile) -> dict:
    """
    Create a mock response for test environment.

    Args:
        db_file: MediaFile object

    Returns:
        Mock response dictionary
    """
    return {"content": "Mock video content", "content_type": db_file.content_type}


def get_content_streaming_response(db_file: MediaFile) -> StreamingResponse:
    """
    Get streaming response for file content download.

    Args:
        db_file: MediaFile object

    Returns:
        StreamingResponse for file download
    """
    if os.environ.get("SKIP_S3", "False").lower() == "true":
        return StreamingResponse(
            content=io.BytesIO(b"Mock file content"), media_type=db_file.content_type
        )

    try:
        file_content_io, content_length, content_type = download_file(
            db_file.storage_path
        )
        return StreamingResponse(
            content=file_content_io,
            media_type=content_type or db_file.content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{db_file.filename}"',
                "Content-Length": str(content_length),
            },
        )
    except Exception as e:
        logger.error(f"Error retrieving file content: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving file content: {e}",
        )


def get_video_streaming_response(
    db_file: MediaFile, range_header: str = None
) -> StreamingResponse:
    """
    Get streaming response for video playback with range support.

    Args:
        db_file: MediaFile object
        range_header: HTTP Range header value

    Returns:
        StreamingResponse for video streaming
    """
    if os.environ.get("SKIP_S3", "False").lower() == "true":
        return create_mock_response(db_file)

    try:
        if range_header:
            logger.info(f"Range header received: {range_header}")

        # Get the file from MinIO with range handling
        file_stream = get_file_stream(db_file.storage_path, range_header)

        # Set appropriate headers for video streaming with proper CORS support
        headers = {
            "Content-Disposition": f'inline; filename="{db_file.filename}"',
            "Accept-Ranges": "bytes",
            "Cache-Control": "max-age=3600",  # Allow caching for 1 hour
            "Access-Control-Allow-Origin": "*",  # Allow access from any origin
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Range, Content-Type, Accept",
            "Content-Type": db_file.content_type,
        }

        # Determine status code based on range request
        status_code = (
            status.HTTP_206_PARTIAL_CONTENT if range_header else status.HTTP_200_OK
        )

        # Return the video as a streaming response
        return StreamingResponse(
            content=file_stream,
            media_type=db_file.content_type,
            headers=headers,
            status_code=status_code,
        )
    except Exception as e:
        logger.error(f"Error serving video file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error serving video: {e}",
        )


def get_enhanced_video_streaming_response(
    db_file: MediaFile, range_header: str = None
) -> StreamingResponse:
    """
    Get enhanced streaming response with YouTube-like streaming capabilities.

    Features:
    - Precise range request handling for seeking
    - Adaptive chunk sizes based on file size
    - Proper content-length headers for progress indication
    - Efficient memory usage for large files
    - Browser caching support

    Args:
        db_file: MediaFile object
        range_header: HTTP Range header value

    Returns:
        StreamingResponse for enhanced video streaming
    """
    if os.environ.get("SKIP_S3", "False").lower() == "true":
        return create_mock_response(db_file)

    try:
        if range_header:
            logger.info(f"Range request: {range_header} for file {db_file.id}")

        # Set media type based on file content type with fallback to mp4
        media_type = db_file.content_type or "video/mp4"

        # Get file content as a stream with range information
        logger.info(f"Streaming file: id={db_file.id}, path={db_file.storage_path}")
        file_stream, start_byte, end_byte, total_length = get_file_stream(
            db_file.storage_path, range_header
        )

        # Determine response status code (206 Partial Content for range requests)
        status_code = (
            status.HTTP_206_PARTIAL_CONTENT if range_header else status.HTTP_200_OK
        )

        # Set comprehensive response headers for optimal streaming
        headers = {
            "Content-Disposition": f'inline; filename="{db_file.filename}"',
            "Content-Type": media_type,
            "Accept-Ranges": "bytes",  # Inform client we support range requests
            "Access-Control-Allow-Origin": "*",  # Allow any origin for development
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Range, Origin, Content-Type, Accept",
        }

        # Add Content-Range header for range requests (required for 206 responses)
        if range_header and total_length is not None:
            content_range = f"bytes {start_byte}-{end_byte}/{total_length}"
            headers["Content-Range"] = content_range

            # For range requests, content length is the actual bytes being sent
            content_length = (
                end_byte - start_byte + 1
                if end_byte is not None
                else total_length - start_byte
            )
            headers["Content-Length"] = str(content_length)

            logger.info(f"Serving range: {content_range}, length: {content_length}")
        elif total_length is not None:
            # For full file requests, content length is the total file size
            headers["Content-Length"] = str(total_length)

        # Add caching headers based on content type
        if media_type.startswith(("video/", "audio/")):
            headers["Cache-Control"] = (
                "public, max-age=86400, stale-while-revalidate=604800"  # 1 day cache, 7 day stale
            )
            # Add ETag if available to support conditional requests
            if hasattr(db_file, "md5_hash") and db_file.md5_hash:
                headers["ETag"] = f'"{db_file.md5_hash}"'
        else:
            # Other media types get shorter cache times
            headers["Cache-Control"] = "public, max-age=3600"  # 1 hour cache

        # Return a streaming response that doesn't load the entire file into memory
        return StreamingResponse(
            content=file_stream,
            status_code=status_code,
            media_type=media_type,
            headers=headers,
        )
    except Exception as e:
        logger.error(f"Error streaming video: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error streaming video: {e}",
        )


def validate_file_exists(db_file: MediaFile) -> None:
    """
    Validate that a file exists and has storage path.

    Args:
        db_file: MediaFile object

    Raises:
        HTTPException: If file doesn't exist or isn't available
    """
    if not db_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
        )

    if not db_file.storage_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not available"
        )


def get_thumbnail_streaming_response(db_file: MediaFile) -> StreamingResponse:
    """
    Get streaming response for a thumbnail image.

    Args:
        db_file: MediaFile object

    Returns:
        StreamingResponse for thumbnail image

    Raises:
        HTTPException: If thumbnail doesn't exist or can't be retrieved
    """
    if not db_file.thumbnail_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thumbnail not available for this file",
        )

    if os.environ.get("SKIP_S3", "False").lower() == "true":
        return StreamingResponse(
            content=io.BytesIO(b"Mock thumbnail content"), media_type="image/jpeg"
        )

    try:
        # download_file returns a tuple of (BytesIO, content_length, content_type)
        thumbnail_io, content_length, _ = download_file(db_file.thumbnail_path)

        return StreamingResponse(
            content=thumbnail_io,
            media_type="image/jpeg",  # Thumbnails are generated as JPEG
            headers={
                "Content-Disposition": f'inline; filename="{os.path.basename(db_file.thumbnail_path)}"',
                "Cache-Control": "public, max-age=86400",  # Cache thumbnails for 1 day
                "Content-Length": str(content_length),
            },
        )
    except Exception as e:
        logger.error(f"Error retrieving thumbnail: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving thumbnail: {str(e)}",
        )
