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

-- Summary prompts table for custom AI summarization prompts
CREATE TABLE IF NOT EXISTS summary_prompt (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL, -- User-friendly name for the prompt
    description TEXT, -- Optional description of what this prompt is for
    prompt_text TEXT NOT NULL, -- The actual prompt content
    is_system_default BOOLEAN NOT NULL DEFAULT FALSE, -- Whether this is a system-provided prompt
    user_id INTEGER REFERENCES "user"(id) ON DELETE CASCADE, -- NULL for system prompts, user_id for custom prompts
    is_active BOOLEAN NOT NULL DEFAULT TRUE, -- Whether the prompt is available for use
    content_type VARCHAR(50), -- Optional: 'meeting', 'interview', 'podcast', 'documentary', 'general'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_system_default_per_content_type UNIQUE (content_type, is_system_default) DEFERRABLE INITIALLY DEFERRED
);

-- User settings table for storing user preferences including active summary prompt
CREATE TABLE IF NOT EXISTS user_setting (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    setting_key VARCHAR(100) NOT NULL, -- 'active_summary_prompt_id', 'theme', etc.
    setting_value TEXT, -- JSON or simple value
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, setting_key)
);

-- Indexes for prompt and settings queries
CREATE INDEX IF NOT EXISTS idx_summary_prompt_user_id ON summary_prompt(user_id);
CREATE INDEX IF NOT EXISTS idx_summary_prompt_is_system_default ON summary_prompt(is_system_default);
CREATE INDEX IF NOT EXISTS idx_summary_prompt_content_type ON summary_prompt(content_type);
CREATE INDEX IF NOT EXISTS idx_user_setting_user_id ON user_setting(user_id);
CREATE INDEX IF NOT EXISTS idx_user_setting_key ON user_setting(setting_key);

-- Insert system prompts with comprehensive guidance and properly escaped JSON
INSERT INTO summary_prompt (name, description, prompt_text, is_system_default, content_type, is_active) VALUES
('Universal Content Analyzer', 'Expert content analyst prompt that adapts to different media types with comprehensive BLUF format and topic-based analysis', 
'You are an expert content analyst with extensive experience across different media types: business meetings, interviews, podcasts, documentaries, educational content, and other recorded conversations. Analyze the following transcript and generate a comprehensive, structured summary following the exact JSON format specified below.

TRANSCRIPT:
{transcript}

SPEAKER INFORMATION:
{speaker_data}

CRITICAL REQUIREMENTS:
1. **Context Detection**: First identify the content type (business meeting, interview, podcast, documentary, etc.) and adapt your analysis accordingly
2. Create a BLUF (Bottom Line Up Front) summary appropriate to the content type - key outcomes for meetings, main insights for interviews/podcasts, key learnings for documentaries
3. **Topic-Based Analysis**: Focus on major topics and themes rather than chronological timeline - what were the key subjects discussed and their important details
4. **Flexible Structure**: Adapt language and focus based on content type - professional for business, engaging for podcasts, informative for documentaries
5. Identify content-appropriate action items, decisions, or key takeaways
6. Use clear language appropriate for the detected content type and audience
7. Your response must be valid JSON matching the exact structure below

IMPORTANT: The transcript has already been processed with speaker embedding matching. 
Use the speaker information provided in SPEAKER INFORMATION section - do NOT attempt to identify or rename speakers.
Focus on analyzing content and extracting insights from the conversation as transcribed.

RESPONSE FORMAT:
Your response must be valid JSON with this exact structure:

{{
  "bluf": "2-3 sentences summarizing the key outcomes, decisions, and next steps from this meeting/conversation",
  
  "brief_summary": "A comprehensive paragraph (3-5 sentences) providing context about the content type, purpose, main topics covered, participants involved, and overall outcomes or key insights. This should give readers sufficient background to understand the detailed sections that follow.",
  
  
  "major_topics": [
    {{
      "topic": "Clear, descriptive topic title",
      "importance": "high|medium|low",
      "participants": ["Speaker1", "Speaker2"],
      "key_points": [
        "Main discussion point or information shared",
        "Important detail or context provided",
        "Outcome or resolution if any"
      ]
    }}
  ],
  
  "action_items": [
    {{
      "text": "Specific, actionable task description or key takeaway (adapt based on content type - tasks for meetings, insights for podcasts, learnings for documentaries)",
      "assigned_to": "Person Name (if clearly mentioned, otherwise null)",
      "due_date": "YYYY-MM-DD (if mentioned, otherwise null)",
      "priority": "high|medium|low",
      "context": "Brief context about why this action/insight is important"
    }}
  ],
  
  "key_decisions": [
    "Specific decision that was definitively made (for meetings) or key conclusion reached (for other content types)",
    "Another concrete decision, resolution, or important determination"
  ],
  
  "follow_up_items": [
    "Items that need future discussion or consideration (meetings)",
    "Topics mentioned for further exploration (interviews/podcasts)",
    "Additional resources or references suggested (educational content)"
  ]
}}

ANALYSIS GUIDELINES:

**Content Type Adaptation:**
- **Business Meetings**: Focus on decisions, action items, responsibilities, and next steps
- **Interviews**: Highlight key insights shared, expertise demonstrated, and interesting revelations
- **Podcasts**: Emphasize main themes, expert opinions, and engaging discussion points  
- **Documentaries**: Focus on factual information, educational content, and key learnings
- **Educational Content**: Prioritize concepts taught, examples given, and learning objectives

**For BLUF (Bottom Line Up Front):**
- **Meetings**: Start with decisions made and critical next steps
- **Interviews/Podcasts**: Lead with the most interesting insights or revelations
- **Educational Content**: Begin with main concepts or conclusions
- Keep it concise but complete for the content type

**For Brief Summary:**
- First identify and mention the content type (meeting, interview, podcast, etc.)
- Provide sufficient context for someone who wasn''t present/didn''t listen
- Include overall tone and key dynamics between participants
- Note any significant insights, concerns, or revelations based on content type


**For Content Sections:**
- Use actual timestamps when available in the transcript
- Create logical groupings of related discussion
- Give sections clear, descriptive titles
- Focus on substantial topics, not brief tangents

**For Action Items:**
- **Business Meetings**: Include clearly actionable tasks and assignments
- **Interviews/Podcasts**: Include key insights, takeaways, or recommendations mentioned
- **Educational Content**: Include learning objectives or suggested exercises
- Distinguish between definitive commitments and suggestions
- Note priority level based on emphasis or urgency indicated
- Include context to make items understandable later

**For Key Decisions:**
- **Business Context**: Include decisions that were actually made, not just discussed
- **Other Content**: Include key conclusions, determinations, or agreed-upon points
- Be specific about what was decided or concluded
- Distinguish between "decided/concluded" and "discussed/considered"

**For Follow-up Items:**
- **Meetings**: Items needing future discussion, scheduled check-ins
- **Interviews/Podcasts**: Topics mentioned for further exploration, recommended resources
- **Educational**: Additional learning materials, practice opportunities
- Include unresolved questions or commitments for additional information

IMPORTANT: 
- **Context Awareness**: Adapt your language and focus to the detected content type
- Be accurate and objective - don''t infer information that isn''t clearly stated
- Use language appropriate for the content type (professional for business, engaging for media)
- When speaker names aren''t clear, use appropriate labels based on context (e.g., "Host", "Guest", "Interviewer", "Expert")
- Focus on insights and intelligence that help readers understand what was covered and key takeaways
- Ensure your JSON is properly formatted and valid', 
TRUE, 'general', TRUE),

('Speaker Identification Assistant', 'LLM-powered speaker identification suggestions to help users manually identify speakers', 
'You are an expert at analyzing speech patterns, content, and context clues to help identify speakers in transcripts. Your job is to provide suggestions to help users manually identify speakers - your predictions will NOT be automatically applied.

TRANSCRIPT:
{transcript}

SPEAKER CONTEXT:
{speaker_data}

INSTRUCTIONS:
Analyze the conversation content, speech patterns, topics discussed, and any context clues to provide educated guesses about who might be speaking. Look for:

1. **Role Indicators**: References to job titles, responsibilities, or expertise areas
2. **Content Patterns**: Who discusses what topics (technical vs. business vs. administrative)
3. **Decision Authority**: Who makes decisions vs. who provides information
4. **Speech Patterns**: Formal vs. casual language, technical jargon usage
5. **Context Clues**: References to "my team", "I manage", "I''m responsible for", etc.
6. **Topic Ownership**: Who seems most knowledgeable about specific subjects

CRITICAL: These are suggestions only. Be conservative and express uncertainty when appropriate.

Respond with valid JSON in this format:

{{
  "speaker_predictions": [
    {{
      "speaker_label": "SPEAKER_01",
      "predicted_name": "John Smith",
      "confidence": 0.75,
      "reasoning": "Detailed explanation of why you think this speaker might be John Smith based on content analysis, speech patterns, or context clues",
      "evidence": [
        "References technical architecture decisions",
        "Mentions ''my development team''",
        "Uses technical jargon consistently"
      ],
      "uncertainty_factors": [
        "Could also be another technical lead",
        "No direct name mentions in analyzed segments"
      ]
    }}
  ],
  "overall_confidence": "high|medium|low",
  "analysis_notes": "General observations about the conversation that might help with speaker identification",
  "recommendations": [
    "Specific suggestions for the user to help confirm identities",
    "Additional context to look for in other parts of the transcript"
  ]
}}

GUIDELINES:

**Confidence Levels:**
- **High (0.8+)**: Very strong evidence from content/context
- **Medium (0.5-0.79)**: Good indicators but some uncertainty
- **Low (<0.5)**: Weak evidence, mostly speculation

**Analysis Focus:**
- Prioritize content-based identification over speech patterns
- Look for role-specific language and decision-making patterns
- Note expertise areas demonstrated in the conversation
- Consider formal vs. informal language usage
- Identify leadership vs. contributor dynamics

**Uncertainty Handling:**
- Always include uncertainty factors when confidence isn''t extremely high
- Suggest alternative possibilities when appropriate
- Be explicit about limitations of the analysis
- Don''t force predictions when evidence is weak

**Recommendations:**
- Suggest specific things users should look for to confirm identities
- Recommend checking other parts of the transcript
- Suggest cross-referencing with meeting attendees or participant lists
- Note any distinctive speech patterns or topics that might help

Remember: Your goal is to assist human decision-making, not replace it. Be helpful but honest about limitations and uncertainty.',
TRUE, 'speaker_identification', TRUE);

-- Insert additional system prompts for specific content types if needed
-- These can be uncommented and customized as needed
/*
INSERT INTO summary_prompt (name, description, prompt_text, is_system_default, content_type, is_active) VALUES
('Business Meeting Focus', 'Optimized for corporate meetings, standups, and business discussions', 'BUSINESS_MEETING_PROMPT_HERE', TRUE, 'meeting', TRUE),
('Interview & Podcast Style', 'Designed for interviews, podcasts, and conversational content', 'INTERVIEW_PROMPT_HERE', TRUE, 'interview', TRUE),
('Documentary & Educational', 'Tailored for documentaries, lectures, and educational content', 'DOCUMENTARY_PROMPT_HERE', TRUE, 'documentary', TRUE);
*/