from minio import Minio
from minio.error import S3Error
from minio.commonconfig import ComposeSource
from typing import Tuple, BinaryIO, Optional, Union
import io
import os
import datetime
import urllib3

from app.core.config import settings

# Disable urllib3 warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Initialize the MinIO client
minio_client = Minio(
    f"{settings.MINIO_HOST}:{settings.MINIO_PORT}",
    access_key=settings.MINIO_ROOT_USER,
    secret_key=settings.MINIO_ROOT_PASSWORD,
    secure=settings.MINIO_SECURE
)


def ensure_bucket_exists():
    """
    Ensure the media bucket exists, creating it if necessary
    """
    try:
        if not minio_client.bucket_exists(settings.MEDIA_BUCKET_NAME):
            minio_client.make_bucket(settings.MEDIA_BUCKET_NAME)
    except S3Error as e:
        raise Exception(f"Error ensuring bucket exists: {e}")


def upload_file(file_content: BinaryIO, file_size: int, object_name: str, content_type: str) -> str:
    """
    Upload a file to MinIO
    
    Args:
        file_content: File content as a BytesIO object
        file_size: Size of the file in bytes
        object_name: Object name in MinIO (path/filename)
        content_type: MIME type of the file
        
    Returns:
        Object name
    """
    ensure_bucket_exists()
    
    try:
        minio_client.put_object(
            bucket_name=settings.MEDIA_BUCKET_NAME,
            object_name=object_name,
            data=file_content,
            length=file_size,
            content_type=content_type
        )
        return object_name
    except S3Error as e:
        raise Exception(f"Error uploading file: {e}")


def download_file(object_name: str) -> bytes:
    """
    Download a file from MinIO
    
    Args:
        object_name: Object name in MinIO
        
    Returns:
        File content as bytes
    """
    try:
        # Get the file from MinIO
        response = minio_client.get_object(settings.MEDIA_BUCKET_NAME, object_name)
        
        # Read the entire file into memory
        file_content = response.read()
        
        # Close the response to free up resources
        response.close()
        response.release_conn()
        
        return file_content
    except Exception as e:
        print(f"Error downloading file: {e}")
        raise Exception(f"Error downloading file: {e}")


def get_file_stream(object_name: str, range_header: str = None):
    """
    Get a file stream from MinIO for efficient streaming of large files
    
    Args:
        object_name: Object name in MinIO
        range_header: HTTP Range header for partial content requests
        
    Returns:
        Generator that yields chunks of the file
    """
    try:
        kwargs = {
            'bucket_name': settings.MEDIA_BUCKET_NAME,
            'object_name': object_name
        }
        
        # Parse range header if present
        if range_header and range_header.startswith('bytes='):
            try:
                # Parse range from format "bytes=start-end"
                range_value = range_header.replace('bytes=', '')
                parts = range_value.split('-')
                
                # Get start and end values
                start = int(parts[0]) if parts[0] else 0
                end = int(parts[1]) if len(parts) > 1 and parts[1] else None
                
                # Add offset and length parameters if we have a valid range
                kwargs['offset'] = start
                if end is not None:
                    kwargs['length'] = end - start + 1  # +1 because range is inclusive
                    
                print(f"Streaming with range: start={start}, end={end if end is not None else 'EOF'}")
            except Exception as e:
                print(f"Error parsing range header: {e}")
                # Continue without range if parsing fails
                pass
        
        # Get the file from MinIO
        response = minio_client.get_object(**kwargs)
        
        # Create a generator that yields chunks of the file
        chunk_size = 8192  # 8KB chunks
        
        # Yield chunks of the file
        while True:
            chunk = response.read(chunk_size)
            if not chunk:
                break
            yield chunk
            
        # Close the response when done
        response.close()
        response.release_conn()
    except Exception as e:
        print(f"Error streaming file: {e}")
        raise Exception(f"Error streaming file: {e}")


def get_file_url(object_name: str, expires: int = 86400) -> str:
    """
    Get a presigned URL for a file in MinIO
    
    Args:
        object_name: Object name in MinIO
        expires: URL expiration time in seconds (default: 24 hours)
        
    Returns:
        Presigned URL that directly accesses the media file
    """
    try:
        # Ensure expires is a positive integer
        if not isinstance(expires, int) or expires <= 0:
            expires = 86400  # Default to 24 hours
            
        # Debug logging
        print(f"Getting presigned URL for {object_name} with expires={expires} seconds")
        
        # Create a direct URL using the get_presigned_url method
        try:
            # Try using the presigned_get_object method with a timedelta
            delta = datetime.timedelta(seconds=expires)
            url = minio_client.presigned_get_object(
                bucket_name=settings.MEDIA_BUCKET_NAME,
                object_name=object_name,
                expires=delta
            )
        except Exception as inner_e:
            print(f"First attempt failed: {inner_e}, trying alternative method")
            # If that fails, try using the raw method with seconds
            url = minio_client.get_presigned_url(
                "GET",
                settings.MEDIA_BUCKET_NAME,
                object_name,
                expires=expires
            )
        
        # Verify the URL is valid
        if not url or not url.startswith('http'):
            raise ValueError(f"Invalid URL generated: {url}")
        
        # Replace the internal minio URL with the externally accessible URL
        # For development, use the host IP and port defined in env vars
        if 'MINIO_PUBLIC_HOST' in os.environ and 'MINIO_PUBLIC_PORT' in os.environ:
            # Extract the container host and port from the URL
            minio_server = f"{settings.MINIO_HOST}:{settings.MINIO_PORT}"
            if minio_server in url:
                # Replace with public host:port
                public_url = url.replace(
                    minio_server,
                    f"{os.environ.get('MINIO_PUBLIC_HOST')}:{os.environ.get('MINIO_PUBLIC_PORT')}"
                )
                print(f"Replaced internal {minio_server} with public host in URL")
                url = public_url
        
        # Log the generated URL (truncated for security)
        print(f"Generated presigned URL: {url[:50]}...")
        
        return url
    except Exception as e:
        # Catch all exceptions, not just S3Error
        print(f"Error in get_file_url: {e}, type(expires)={type(expires)}")
        raise Exception(f"Error getting file URL: {e}")


def delete_file(object_name: str):
    """
    Delete a file from MinIO
    
    Args:
        object_name: Object name in MinIO
    """
    try:
        minio_client.remove_object(
            bucket_name=settings.MEDIA_BUCKET_NAME,
            object_name=object_name
        )
    except S3Error as e:
        raise Exception(f"Error deleting file: {e}")
