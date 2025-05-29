<div align="center">
  <img src="../../assets/logo-banner.png" alt="OpenTranscribe Logo" width="250">
  
  # Backend Utility Scripts
</div>

This directory contains utility scripts for OpenTranscribe backend operations.

## Scripts Overview

### Database & Development Scripts

- **`create_admin.py`** - Creates an admin user in the database
  - Usage: `python scripts/create_admin.py`
  - Alternative to `app/initial_data.py` for manual admin creation

- **`db_inspect.py`** - Database inspection utility for debugging
  - Usage: `python scripts/db_inspect.py`
  - Useful for debugging tag tables and database structure

- **`query_tags.py`** - Database query utility for tag debugging
  - Usage: `python scripts/query_tags.py`
  - Helps troubleshoot tag-related database issues

### Infrastructure Setup Scripts

- **`create_minio_bucket.py`** - Creates MinIO bucket for file storage
  - Usage: `python scripts/create_minio_bucket.py`
  - Creates the required bucket if not auto-created by the application
  - Configures bucket policies and settings for optimal file storage

- **`create_opensearch_indexes.py`** - Creates OpenSearch indexes for search functionality
  - Usage: `python scripts/create_opensearch_indexes.py`
  - Sets up required indexes for transcript and speaker search
  - Configures search mappings and analyzers for optimal text search

## Script Categories

### Development & Debugging
Scripts for development workflow and troubleshooting:
- `create_admin.py` - Manual admin user creation
- `db_inspect.py` - Database state inspection  
- `query_tags.py` - Tag system debugging

### Infrastructure Setup
Scripts for initial system setup and configuration:
- `create_minio_bucket.py` - Object storage bucket creation
- `create_opensearch_indexes.py` - Search index initialization

## Usage Notes

- All scripts should be run from the backend root directory or container
- Scripts use environment variables from `.env` file or container environment
- For Docker deployments, run scripts inside the backend container:
  ```bash
  ./opentr.sh shell backend
  python scripts/script_name.py
  ```

## Dependencies

- Scripts depend on the main application dependencies
- Ensure database, MinIO, and OpenSearch services are running before use
- Some scripts require specific environment variables to be set

## Environment Variables Required

### For MinIO Scripts
```bash
MINIO_SERVER=localhost
MINIO_PORT=9090
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
MINIO_BUCKET_NAME=transcribe-app
```

### For OpenSearch Scripts  
```bash
OPENSEARCH_HOST=localhost
OPENSEARCH_PORT=9200
OPENSEARCH_USER=admin
OPENSEARCH_PASSWORD=admin
```

### For Database Scripts
```bash
DATABASE_URL=postgresql://user:pass@host:5432/db
```