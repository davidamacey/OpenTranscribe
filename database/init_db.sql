-- Initialize database tables for OpenTranscribe

-- Users table
CREATE TABLE IF NOT EXISTS "user" (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_superuser BOOLEAN NOT NULL DEFAULT FALSE,
    role VARCHAR(50) DEFAULT 'user',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Media files table
CREATE TABLE IF NOT EXISTS media_file (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    storage_path VARCHAR(500) NOT NULL,
    file_size BIGINT NOT NULL,
    duration FLOAT,
    upload_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE NULL,
    content_type VARCHAR(100) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    is_public BOOLEAN DEFAULT FALSE,
    language VARCHAR(10) NULL,
    summary TEXT NULL,
    summary_opensearch_id VARCHAR(255) NULL, -- OpenSearch document ID for summary
    summary_status VARCHAR(50) DEFAULT 'pending', -- pending, processing, completed, failed
    translated_text TEXT NULL,
    file_hash VARCHAR(255) NULL,
    thumbnail_path VARCHAR(500) NULL,
    -- Detailed metadata fields
    metadata_raw JSONB NULL,
    metadata_important JSONB NULL,
    -- Waveform visualization data
    waveform_data JSONB NULL,
    -- Media technical specs
    media_format VARCHAR(50) NULL,
    codec VARCHAR(50) NULL,
    frame_rate FLOAT NULL,
    frame_count INTEGER NULL,
    resolution_width INTEGER NULL,
    resolution_height INTEGER NULL,
    aspect_ratio VARCHAR(20) NULL,
    -- Audio specs
    audio_channels INTEGER NULL,
    audio_sample_rate INTEGER NULL,
    audio_bit_depth INTEGER NULL,
    -- Creation information
    creation_date TIMESTAMP WITH TIME ZONE NULL,
    last_modified_date TIMESTAMP WITH TIME ZONE NULL,
    -- Device information
    device_make VARCHAR(100) NULL,
    device_model VARCHAR(100) NULL,
    -- Content information
    title VARCHAR(255) NULL,
    author VARCHAR(255) NULL,
    description TEXT NULL,
    source_url VARCHAR(2048) NULL, -- Original source URL (e.g., YouTube URL)
    -- Task tracking and error handling fields
    active_task_id VARCHAR(255) NULL,
    task_started_at TIMESTAMP WITH TIME ZONE NULL,
    task_last_update TIMESTAMP WITH TIME ZONE NULL,
    cancellation_requested BOOLEAN DEFAULT FALSE,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    last_error_message TEXT NULL,
    force_delete_eligible BOOLEAN DEFAULT FALSE,
    recovery_attempts INTEGER DEFAULT 0,
    last_recovery_attempt TIMESTAMP WITH TIME ZONE NULL,
    user_id INTEGER NOT NULL REFERENCES "user" (id)
);

-- Create the Tag table
CREATE TABLE IF NOT EXISTS tag (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create the FileTag join table
CREATE TABLE IF NOT EXISTS file_tag (
    id SERIAL PRIMARY KEY,
    media_file_id INTEGER NOT NULL REFERENCES media_file (id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tag (id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (media_file_id, tag_id)
);

-- Speaker profiles table (global speaker identities)
CREATE TABLE IF NOT EXISTS speaker_profile (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES "user"(id),
    name VARCHAR(255) NOT NULL, -- User-assigned name (e.g., "John Doe")
    description TEXT NULL, -- Optional description or notes
    uuid VARCHAR(255) NOT NULL UNIQUE, -- Unique identifier
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, name) -- Ensure unique profile names per user
);

-- Speakers table (speaker instances within specific media files)
CREATE TABLE IF NOT EXISTS speaker (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES "user"(id),
    media_file_id INTEGER NOT NULL REFERENCES media_file(id) ON DELETE CASCADE, -- Associate speaker with specific file
    profile_id INTEGER NULL REFERENCES speaker_profile(id) ON DELETE SET NULL, -- Link to global profile
    name VARCHAR(255) NOT NULL, -- Original name from diarization (e.g., "SPEAKER_01")
    display_name VARCHAR(255) NULL, -- User-assigned display name
    suggested_name VARCHAR(255) NULL, -- AI-suggested name based on embedding match
    uuid VARCHAR(255) NOT NULL, -- Unique identifier for the speaker instance
    verified BOOLEAN NOT NULL DEFAULT FALSE, -- Flag to indicate if the speaker has been verified by a user
    confidence FLOAT NULL, -- Confidence score if auto-matched
    embedding_vector JSONB NULL, -- Speaker embedding as JSON array (deprecated - moved to OpenSearch)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, media_file_id, name) -- Ensure unique speaker names per file per user
);

-- Speaker collections table
CREATE TABLE IF NOT EXISTS speaker_collection (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT NULL,
    user_id INTEGER NOT NULL REFERENCES "user"(id),
    is_public BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, name) -- Ensure unique collection names per user
);

-- Speaker collection members join table
CREATE TABLE IF NOT EXISTS speaker_collection_member (
    id SERIAL PRIMARY KEY,
    collection_id INTEGER NOT NULL REFERENCES speaker_collection(id) ON DELETE CASCADE,
    speaker_profile_id INTEGER NOT NULL REFERENCES speaker_profile(id) ON DELETE CASCADE,
    added_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(collection_id, speaker_profile_id) -- Ensure a speaker profile can only be in a collection once
);

-- Transcript segments table
CREATE TABLE IF NOT EXISTS transcript_segment (
    id SERIAL PRIMARY KEY,
    media_file_id INTEGER NOT NULL REFERENCES media_file(id),
    speaker_id INTEGER NULL REFERENCES speaker(id),
    start_time FLOAT NOT NULL,
    end_time FLOAT NOT NULL,
    text TEXT NOT NULL
);

-- Comments table
CREATE TABLE IF NOT EXISTS comment (
    id SERIAL PRIMARY KEY,
    media_file_id INTEGER NOT NULL REFERENCES media_file(id),
    user_id INTEGER NOT NULL REFERENCES "user"(id),
    text TEXT NOT NULL,
    timestamp FLOAT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Tasks table
CREATE TABLE IF NOT EXISTS task (
    id VARCHAR(255) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES "user"(id),
    media_file_id INTEGER NULL REFERENCES media_file(id),
    task_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,
    progress FLOAT DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE NULL,
    error_message TEXT NULL
);

-- Analytics table
CREATE TABLE IF NOT EXISTS analytics (
    id SERIAL PRIMARY KEY,
    media_file_id INTEGER UNIQUE REFERENCES media_file(id),
    speaker_stats JSONB NULL,
    sentiment JSONB NULL,
    keywords JSONB NULL
);

-- Collections table
CREATE TABLE IF NOT EXISTS collection (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT NULL,
    user_id INTEGER NOT NULL REFERENCES "user"(id),
    is_public BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, name) -- Ensure unique collection names per user
);

-- Collection members join table
CREATE TABLE IF NOT EXISTS collection_member (
    id SERIAL PRIMARY KEY,
    collection_id INTEGER NOT NULL REFERENCES collection(id) ON DELETE CASCADE,
    media_file_id INTEGER NOT NULL REFERENCES media_file(id) ON DELETE CASCADE,
    added_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(collection_id, media_file_id) -- Ensure a file can only be in a collection once
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_media_file_user_id ON media_file(user_id);
CREATE INDEX IF NOT EXISTS idx_media_file_status ON media_file(status);
CREATE INDEX IF NOT EXISTS idx_media_file_upload_time ON media_file(upload_time);
CREATE INDEX IF NOT EXISTS idx_media_file_hash ON media_file(file_hash);
CREATE INDEX IF NOT EXISTS idx_media_file_active_task_id ON media_file(active_task_id);
CREATE INDEX IF NOT EXISTS idx_media_file_task_last_update ON media_file(task_last_update);
CREATE INDEX IF NOT EXISTS idx_media_file_force_delete_eligible ON media_file(force_delete_eligible);
CREATE INDEX IF NOT EXISTS idx_media_file_retry_count ON media_file(retry_count);

CREATE INDEX IF NOT EXISTS idx_speaker_user_id ON speaker(user_id);
CREATE INDEX IF NOT EXISTS idx_speaker_media_file_id ON speaker(media_file_id);
CREATE INDEX IF NOT EXISTS idx_speaker_profile_id ON speaker(profile_id);
CREATE INDEX IF NOT EXISTS idx_speaker_verified ON speaker(verified);

CREATE INDEX IF NOT EXISTS idx_speaker_profile_user_id ON speaker_profile(user_id);
CREATE INDEX IF NOT EXISTS idx_speaker_profile_uuid ON speaker_profile(uuid);

CREATE INDEX IF NOT EXISTS idx_transcript_segment_media_file_id ON transcript_segment(media_file_id);
CREATE INDEX IF NOT EXISTS idx_transcript_segment_speaker_id ON transcript_segment(speaker_id);

CREATE INDEX IF NOT EXISTS idx_task_user_id ON task(user_id);
CREATE INDEX IF NOT EXISTS idx_task_status ON task(status);
CREATE INDEX IF NOT EXISTS idx_task_media_file_id ON task(media_file_id);

CREATE INDEX IF NOT EXISTS idx_collection_user_id ON collection(user_id);
CREATE INDEX IF NOT EXISTS idx_collection_member_collection_id ON collection_member(collection_id);
CREATE INDEX IF NOT EXISTS idx_collection_member_media_file_id ON collection_member(media_file_id);

CREATE INDEX IF NOT EXISTS idx_speaker_collection_user_id ON speaker_collection(user_id);
CREATE INDEX IF NOT EXISTS idx_speaker_collection_member_collection_id ON speaker_collection_member(collection_id);
CREATE INDEX IF NOT EXISTS idx_speaker_collection_member_profile_id ON speaker_collection_member(speaker_profile_id);

-- Speaker match table to store cross-references between similar speakers
CREATE TABLE IF NOT EXISTS speaker_match (
    id SERIAL PRIMARY KEY,
    speaker1_id INTEGER NOT NULL REFERENCES speaker(id) ON DELETE CASCADE,
    speaker2_id INTEGER NOT NULL REFERENCES speaker(id) ON DELETE CASCADE,
    confidence FLOAT NOT NULL, -- Similarity score (0-1)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(speaker1_id, speaker2_id), -- Ensure unique pairs
    CHECK (speaker1_id < speaker2_id) -- Ensure consistent ordering to avoid duplicates
);

-- Indexes for speaker match queries
CREATE INDEX IF NOT EXISTS idx_speaker_match_speaker1 ON speaker_match(speaker1_id);
CREATE INDEX IF NOT EXISTS idx_speaker_match_speaker2 ON speaker_match(speaker2_id);
CREATE INDEX IF NOT EXISTS idx_speaker_match_confidence ON speaker_match(confidence);

-- Note: Default tags are now handled by the backend in app/initial_data.py