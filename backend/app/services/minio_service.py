import datetime
import io
import logging
import os
from typing import BinaryIO

import urllib3
from minio import Minio
from minio.error import S3Error

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


def download_file(object_name: str) -> tuple[io.BytesIO, int, str]:
    """
    Download a file from MinIO

    Args:
        object_name: Object name in MinIO

    Returns:
        Tuple containing:
        - File content as BytesIO object
        - File size in bytes
        - Content type (MIME type)
    """
    logger = logging.getLogger(__name__)
    try:
        # Get the file from MinIO
        response = minio_client.get_object(settings.MEDIA_BUCKET_NAME, object_name)

        # Get content type
        content_type = response.headers.get('content-type', 'application/octet-stream')

        # Get content length
        content_length = int(response.headers.get('content-length', 0))

        # Read the entire file into memory
        file_content = response.read()

        # Close the response to free up resources
        response.close()
        response.release_conn()

        # Return tuple with file data as BytesIO, size, and content type
        return io.BytesIO(file_content), content_length, content_type
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        raise Exception(f"Error downloading file: {e}")


def get_file_stream(object_name: str, range_header: str = None):
    """
    Get a file stream from MinIO for efficient streaming of large files with adaptive chunking.
    Implements robust range request handling for YouTube-like video streaming experience.

    Args:
        object_name: Object name in MinIO
        range_header: HTTP Range header for partial content requests

    Returns:
        Tuple of (Generator that yields chunks of the file, start_byte, end_byte, total_length)
    """
    import logging
    logger = logging.getLogger(__name__)

    # Default values
    start_byte = 0
    end_byte = None
    total_length = None

    try:
        # Get object stats first to know the total size
        try:
            stats = minio_client.stat_object(settings.MEDIA_BUCKET_NAME, object_name)
            total_length = stats.size
            logger.info(f"File size for {object_name}: {total_length} bytes")
        except Exception as e:
            logger.error(f"Error getting object stats: {e}")
            # Continue without total size - less optimal but still functional

        kwargs = {
            'bucket_name': settings.MEDIA_BUCKET_NAME,
            'object_name': object_name
        }

        # Parse range header if present - implement robust range parsing
        if range_header and range_header.startswith('bytes='):
            try:
                # Parse range from format "bytes=start-end"
                range_value = range_header.replace('bytes=', '')
                parts = range_value.split('-')

                # Handle different range request formats
                if parts[0] and parts[1]:  # Format: bytes=start-end
                    start_byte = int(parts[0])
                    end_byte = min(int(parts[1]), total_length - 1) if total_length else int(parts[1])
                elif parts[0]:  # Format: bytes=start-
                    start_byte = int(parts[0])
                    end_byte = total_length - 1 if total_length else None
                elif parts[1]:  # Format: bytes=-end (last N bytes)
                    requested_length = int(parts[1])
                    if total_length:
                        start_byte = max(0, total_length - requested_length)
                        end_byte = total_length - 1

                # Validate range is within bounds
                if total_length and start_byte >= total_length:
                    logger.warning(f"Range start {start_byte} exceeds file size {total_length}")
                    start_byte = 0
                    end_byte = total_length - 1

                # Add offset and length parameters for MinIO
                kwargs['offset'] = start_byte
                if end_byte is not None:
                    kwargs['length'] = end_byte - start_byte + 1  # +1 because range is inclusive

                logger.info(f"Streaming with range: start={start_byte}, end={end_byte if end_byte is not None else 'EOF'}, total={total_length}")
            except Exception as e:
                logger.error(f"Error parsing range header '{range_header}': {e}")
                # Continue without range if parsing fails
                start_byte = 0
                end_byte = total_length - 1 if total_length else None
        elif total_length:  # No range but we know the size
            end_byte = total_length - 1

        # Get the file from MinIO
        response = minio_client.get_object(**kwargs)

        # Choose optimal chunk size based on file size and range
        # - Smaller chunks for small files or small ranges (reduces latency for small files)
        # - Larger chunks for big files (improves throughput)
        if total_length:
            if total_length < 1024 * 1024:  # < 1MB
                chunk_size = 4096  # 4KB chunks
            elif total_length < 10 * 1024 * 1024:  # < 10MB
                chunk_size = 16384  # 16KB chunks
            elif total_length < 100 * 1024 * 1024:  # < 100MB
                chunk_size = 65536  # 64KB chunks
            else:  # Very large files
                chunk_size = 131072  # 128KB chunks
        else:
            # Default if we don't know the size
            chunk_size = 32768  # 32KB chunks

        # Function to yield chunks with proper resource cleanup
        def generate_chunks():
            try:
                bytes_read = 0
                max_bytes = kwargs.get('length')

                while True:
                    # Adjust final chunk size if we're at the end of requested range
                    if max_bytes is not None and bytes_read + chunk_size > max_bytes:
                        final_chunk_size = max_bytes - bytes_read
                        if final_chunk_size <= 0:
                            break
                        chunk = response.read(final_chunk_size)
                    else:
                        chunk = response.read(chunk_size)

                    if not chunk:
                        break

                    bytes_read += len(chunk)
                    yield chunk
            finally:
                # Ensure resources are properly cleaned up
                try:
                    response.close()
                    response.release_conn()
                except Exception as e:
                    logger.error(f"Error closing MinIO response: {e}")

        # Return the generator along with range information
        return generate_chunks(), start_byte, end_byte, total_length

    except Exception as e:
        logger.error(f"Error setting up file stream for {object_name}: {e}")
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
        logger = logging.getLogger(__name__)
        logger.info(f"Getting presigned URL for {object_name} with expires={expires} seconds")

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
            logger.info(f"First attempt failed: {inner_e}, trying alternative method")
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
                logger.info(f"Replaced internal {minio_server} with public host in URL")
                url = public_url

        # Log the generated URL (truncated for security)
        logger.info(f"Generated presigned URL: {url[:50]}...")

        return url
    except Exception as e:
        # Catch all exceptions, not just S3Error
        logger.error(f"Error in get_file_url: {e}, type(expires)={type(expires)}")
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


class MinIOService:
    """
    Class-based wrapper for MinIO operations.
    Provides an object-oriented interface to the existing functional API.
    """

    def __init__(self):
        self.client = minio_client

    def upload_file(self, file_path: str, bucket_name: str, object_name: str, content_type: str = None):
        """Upload a file to MinIO bucket."""
        try:
            with open(file_path, 'rb') as file_data:
                file_size = os.path.getsize(file_path)
                self.client.put_object(
                    bucket_name=bucket_name,
                    object_name=object_name,
                    data=file_data,
                    length=file_size,
                    content_type=content_type
                )
        except Exception as e:
            raise Exception(f"Error uploading file: {e}")

    def download_file(self, object_name: str, file_path: str, bucket_name: str = None):
        """Download a file from MinIO to local path."""
        bucket = bucket_name or settings.MEDIA_BUCKET_NAME
        try:
            self.client.fget_object(bucket, object_name, file_path)
        except Exception as e:
            raise Exception(f"Error downloading file: {e}")

    def get_presigned_url(self, bucket_name: str, object_name: str, expires: int = 3600):
        """Get a presigned URL for object access."""
        try:
            url = self.client.presigned_get_object(
                bucket_name=bucket_name,
                object_name=object_name,
                expires=datetime.timedelta(seconds=expires)
            )
            # Fix hostname for external access
            if url.startswith("http://minio:9000"):
                from app.core.config import settings
                if settings.ENVIRONMENT == "development":
                    url = url.replace("http://minio:9000", "http://localhost:5178")
                else:
                    # For production, use environment variable for external MinIO URL
                    external_url = os.getenv("EXTERNAL_MINIO_URL", "http://localhost:5178")
                    url = url.replace("http://minio:9000", external_url)
            return url
        except Exception as e:
            raise Exception(f"Error getting presigned URL: {e}")

    def delete_object(self, bucket_name: str, object_name: str):
        """Delete an object from MinIO."""
        try:
            self.client.remove_object(bucket_name, object_name)
        except Exception as e:
            raise Exception(f"Error deleting object: {e}")

    def list_objects(self, bucket_name: str, prefix: str = None, recursive: bool = False):
        """List objects in a bucket."""
        try:
            return self.client.list_objects(bucket_name, prefix=prefix, recursive=recursive)
        except Exception as e:
            raise Exception(f"Error listing objects: {e}")

    def stat_object(self, bucket_name: str, object_name: str):
        """Get object statistics."""
        try:
            return self.client.stat_object(bucket_name, object_name)
        except Exception as e:
            raise Exception(f"Error getting object stats: {e}")

    def get_object(self, bucket_name: str, object_name: str):
        """Get object from MinIO."""
        try:
            return self.client.get_object(bucket_name, object_name)
        except Exception as e:
            raise Exception(f"Error getting object: {e}")

    def bucket_exists(self, bucket_name: str) -> bool:
        """Check if bucket exists."""
        try:
            return self.client.bucket_exists(bucket_name)
        except Exception as e:
            raise Exception(f"Error checking bucket existence: {e}")

    def make_bucket(self, bucket_name: str):
        """Create a new bucket."""
        try:
            self.client.make_bucket(bucket_name)
        except Exception as e:
            raise Exception(f"Error creating bucket: {e}")
