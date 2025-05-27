-- Initialize database tables for OpenTranscribe
-- This replaces the need for Alembic migrations

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
    translated_text TEXT NULL,
    -- Detailed metadata fields
    metadata_raw JSONB NULL,
    metadata_important JSONB NULL,
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

-- Speakers table
CREATE TABLE IF NOT EXISTS speaker (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES "user"(id),
    name VARCHAR(255) NOT NULL, -- Original name from diarization (e.g., "SPEAKER_01")
    display_name VARCHAR(255) NULL, -- User-assigned name (e.g., "John Doe")
    uuid VARCHAR(255) NOT NULL UNIQUE, -- Unique identifier for the speaker
    verified BOOLEAN NOT NULL DEFAULT FALSE, -- Flag to indicate if the speaker has been verified by a user
    embedding_vector JSONB NULL, -- Speaker embedding as JSON array
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
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

-- These tables are already defined above, so we're removing the duplicate definitions

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

-- Insert default tag values if needed
INSERT INTO tag (name) VALUES
    ('Important'),
    ('Meeting'),
    ('Interview'),
    ('Personal')
ON CONFLICT (name) DO NOTHING;

-- Alembic version tracking (to maintain compatibility)
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL,
    PRIMARY KEY (version_num)
);
-- Update to include video metadata fields migration
INSERT INTO alembic_version (version_num) VALUES ('74093bff36e6') ON CONFLICT DO NOTHING;

-- Add completed_at column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'media_file' AND column_name = 'completed_at') THEN
        ALTER TABLE media_file ADD COLUMN completed_at TIMESTAMP WITH TIME ZONE NULL;
    END IF;
END$$;