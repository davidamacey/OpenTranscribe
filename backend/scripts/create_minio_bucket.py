"""
Simple script to create a MinIO bucket for our application.
"""

import os

from dotenv import load_dotenv
from minio import Minio
from minio.error import S3Error

# Load environment variables
load_dotenv()

MINIO_SERVER = os.getenv("MINIO_SERVER", "localhost")
MINIO_PORT = os.getenv("MINIO_PORT", "9090")
MINIO_ROOT_USER = os.getenv("MINIO_ROOT_USER", "minioadmin")
MINIO_ROOT_PASSWORD = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")
MINIO_BUCKET_NAME = os.getenv("MINIO_BUCKET_NAME", "transcribe-app")
MINIO_SECURE = os.getenv("MINIO_SECURE", "False").lower() == "true"


def main():
    try:
        # Initialize MinIO client
        client = Minio(
            f"{MINIO_SERVER}:{MINIO_PORT}",
            access_key=MINIO_ROOT_USER,
            secret_key=MINIO_ROOT_PASSWORD,
            secure=MINIO_SECURE,
        )

        # Check if bucket exists, if not create it
        if not client.bucket_exists(MINIO_BUCKET_NAME):
            client.make_bucket(MINIO_BUCKET_NAME)
            print(f"Bucket '{MINIO_BUCKET_NAME}' created successfully")

            # Set public read policy for the bucket
            import json

            policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"AWS": "*"},
                        "Action": ["s3:GetObject"],
                        "Resource": [f"arn:aws:s3:::{MINIO_BUCKET_NAME}/*"],
                    }
                ],
            }

            # Convert policy dict to JSON string
            policy_str = json.dumps(policy)
            client.set_bucket_policy(MINIO_BUCKET_NAME, policy_str)
            print(f"Public read policy set for bucket '{MINIO_BUCKET_NAME}'")
        else:
            print(f"Bucket '{MINIO_BUCKET_NAME}' already exists")

    except S3Error as e:
        print(f"Error creating bucket: {e}")


if __name__ == "__main__":
    main()
