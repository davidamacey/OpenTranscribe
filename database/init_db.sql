-- Initialize database tables for OpenTranscribe
-- Enable UUID extension for PostgreSQL
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Users table
CREATE TABLE IF NOT EXISTS "user" (
    id SERIAL PRIMARY KEY,
    uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_superuser BOOLEAN NOT NULL DEFAULT FALSE,
    role VARCHAR(50) DEFAULT 'user',
    auth_type VARCHAR(10) DEFAULT 'local' NOT NULL,
    ldap_uid VARCHAR(255) UNIQUE NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_ldap_uid ON "user" (ldap_uid);

-- Media files table
CREATE TABLE IF NOT EXISTS media_file (
    id SERIAL PRIMARY KEY,
    uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
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
    summary_data JSONB NULL, -- Complete structured AI summary (flexible format)
    summary_opensearch_id VARCHAR(255) NULL, -- OpenSearch document ID for summary
    summary_status VARCHAR(50) DEFAULT 'pending', -- pending, processing, completed, failed, not_configured
    summary_schema_version INTEGER DEFAULT 1, -- Track summary schema evolution
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
    uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    name VARCHAR(50) NOT NULL UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create the FileTag join table
CREATE TABLE IF NOT EXISTS file_tag (
    id SERIAL PRIMARY KEY,
    uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    media_file_id INTEGER NOT NULL REFERENCES media_file (id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tag (id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (media_file_id, tag_id)
);

-- Speaker profiles table (global speaker identities)
CREATE TABLE IF NOT EXISTS speaker_profile (
    id SERIAL PRIMARY KEY,
    uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL REFERENCES "user"(id),
    name VARCHAR(255) NOT NULL, -- User-assigned name (e.g., "John Doe")
    description TEXT NULL, -- Optional description or notes
    -- embedding_vector removed: stored in OpenSearch for optimal vector similarity performance
    embedding_count INTEGER DEFAULT 0, -- Number of embeddings averaged into this profile
    last_embedding_update TIMESTAMP WITH TIME ZONE NULL, -- When embedding was last updated
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, name) -- Ensure unique profile names per user
);

-- Speakers table (speaker instances within specific media files)
CREATE TABLE IF NOT EXISTS speaker (
    id SERIAL PRIMARY KEY,
    uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL REFERENCES "user"(id),
    media_file_id INTEGER NOT NULL REFERENCES media_file(id) ON DELETE CASCADE, -- Associate speaker with specific file
    profile_id INTEGER NULL REFERENCES speaker_profile(id) ON DELETE SET NULL, -- Link to global profile
    name VARCHAR(255) NOT NULL, -- Original name from diarization (e.g., "SPEAKER_01")
    display_name VARCHAR(255) NULL, -- User-assigned display name
    suggested_name VARCHAR(255) NULL, -- AI-suggested name based on embedding match
    verified BOOLEAN NOT NULL DEFAULT FALSE, -- Flag to indicate if the speaker has been verified by a user
    confidence FLOAT NULL, -- Confidence score if auto-matched
    -- embedding_vector removed: stored in OpenSearch for optimal vector similarity performance
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    -- Computed status fields (calculated by SpeakerStatusService)
    computed_status VARCHAR(50) NULL, -- "verified", "suggested", "unverified"
    status_text VARCHAR(500) NULL, -- Human-readable status text
    status_color VARCHAR(50) NULL, -- CSS color for status display
    resolved_display_name VARCHAR(255) NULL, -- Best available display name
    UNIQUE(user_id, media_file_id, name) -- Ensure unique speaker names per file per user
);

-- Speaker collections table
CREATE TABLE IF NOT EXISTS speaker_collection (
    id SERIAL PRIMARY KEY,
    uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
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
    uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    collection_id INTEGER NOT NULL REFERENCES speaker_collection(id) ON DELETE CASCADE,
    speaker_profile_id INTEGER NOT NULL REFERENCES speaker_profile(id) ON DELETE CASCADE,
    added_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(collection_id, speaker_profile_id) -- Ensure a speaker profile can only be in a collection once
);

-- Transcript segments table
CREATE TABLE IF NOT EXISTS transcript_segment (
    id SERIAL PRIMARY KEY,
    uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    media_file_id INTEGER NOT NULL REFERENCES media_file(id),
    speaker_id INTEGER NULL REFERENCES speaker(id),
    start_time FLOAT NOT NULL,
    end_time FLOAT NOT NULL,
    text TEXT NOT NULL
);

-- Comments table
CREATE TABLE IF NOT EXISTS comment (
    id SERIAL PRIMARY KEY,
    uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
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
    uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    media_file_id INTEGER UNIQUE REFERENCES media_file(id),
    overall_analytics JSONB NULL, -- Structured analytics from AnalyticsService
    computed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    version VARCHAR(50) NULL -- Version tracking for analytics schema
);

-- Collections table
CREATE TABLE IF NOT EXISTS collection (
    id SERIAL PRIMARY KEY,
    uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
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
    uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    collection_id INTEGER NOT NULL REFERENCES collection(id) ON DELETE CASCADE,
    media_file_id INTEGER NOT NULL REFERENCES media_file(id) ON DELETE CASCADE,
    added_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(collection_id, media_file_id) -- Ensure a file can only be in a collection once
);

-- Create indexes for better performance
-- Integer ID indexes for fast internal joins
CREATE INDEX IF NOT EXISTS idx_media_file_user_id ON media_file(user_id);
CREATE INDEX IF NOT EXISTS idx_media_file_status ON media_file(status);
CREATE INDEX IF NOT EXISTS idx_media_file_upload_time ON media_file(upload_time);
CREATE INDEX IF NOT EXISTS idx_media_file_hash ON media_file(file_hash);
CREATE INDEX IF NOT EXISTS idx_media_file_active_task_id ON media_file(active_task_id);
CREATE INDEX IF NOT EXISTS idx_media_file_task_last_update ON media_file(task_last_update);
CREATE INDEX IF NOT EXISTS idx_media_file_force_delete_eligible ON media_file(force_delete_eligible);
CREATE INDEX IF NOT EXISTS idx_media_file_retry_count ON media_file(retry_count);

-- UUID indexes for fast external API lookups
CREATE INDEX IF NOT EXISTS idx_user_uuid ON "user"(uuid);
CREATE INDEX IF NOT EXISTS idx_media_file_uuid ON media_file(uuid);
CREATE INDEX IF NOT EXISTS idx_tag_uuid ON tag(uuid);
CREATE INDEX IF NOT EXISTS idx_speaker_uuid ON speaker(uuid);
CREATE INDEX IF NOT EXISTS idx_speaker_profile_uuid ON speaker_profile(uuid);
CREATE INDEX IF NOT EXISTS idx_comment_uuid ON comment(uuid);
CREATE INDEX IF NOT EXISTS idx_collection_uuid ON collection(uuid);
CREATE INDEX IF NOT EXISTS idx_speaker_collection_uuid ON speaker_collection(uuid);

CREATE INDEX IF NOT EXISTS idx_speaker_user_id ON speaker(user_id);
CREATE INDEX IF NOT EXISTS idx_speaker_media_file_id ON speaker(media_file_id);
CREATE INDEX IF NOT EXISTS idx_speaker_profile_id ON speaker(profile_id);
CREATE INDEX IF NOT EXISTS idx_speaker_verified ON speaker(verified);

CREATE INDEX IF NOT EXISTS idx_speaker_profile_user_id ON speaker_profile(user_id);

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
    uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
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

-- ========================================
-- AI Suggestions Tables
-- ========================================
-- These tables support LLM-powered tag and collection suggestions (Issue #79)

-- AI suggestions table for tags and collections
-- Simplified schema focused on tags/collections suggestions only
CREATE TABLE IF NOT EXISTS topic_suggestion (
    id SERIAL PRIMARY KEY,
    uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    media_file_id INTEGER NOT NULL REFERENCES media_file(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,

    -- AI-generated suggestions stored as JSONB
    -- Format: [{name: str, confidence: float, rationale: str}, ...]
    suggested_tags JSONB NULL DEFAULT '[]'::jsonb,
    suggested_collections JSONB NULL DEFAULT '[]'::jsonb,

    -- User interaction tracking
    status VARCHAR(50) DEFAULT 'pending',  -- 'pending', 'reviewed', 'accepted', 'rejected'
    user_decisions JSONB NULL,  -- {accepted_collections: [], accepted_tags: []}

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(media_file_id)  -- One suggestion per file
);

-- Indexes for suggestion queries
CREATE INDEX IF NOT EXISTS idx_topic_suggestion_user_status ON topic_suggestion(user_id, status);
CREATE INDEX IF NOT EXISTS idx_topic_suggestion_media_file ON topic_suggestion(media_file_id);

-- Summary prompts table for custom AI summarization prompts
CREATE TABLE IF NOT EXISTS summary_prompt (
    id SERIAL PRIMARY KEY,
    uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL, -- User-friendly name for the prompt
    description TEXT, -- Optional description of what this prompt is for
    prompt_text TEXT NOT NULL, -- The actual prompt content
    is_system_default BOOLEAN NOT NULL DEFAULT FALSE, -- Whether this is a system-provided prompt
    user_id INTEGER REFERENCES "user"(id) ON DELETE CASCADE, -- NULL for system prompts, user_id for custom prompts
    is_active BOOLEAN NOT NULL DEFAULT TRUE, -- Whether the prompt is available for use
    content_type VARCHAR(50), -- Optional: 'meeting', 'interview', 'podcast', 'documentary', 'general'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- User settings table for storing user preferences including active summary prompt
CREATE TABLE IF NOT EXISTS user_setting (
    id SERIAL PRIMARY KEY,
    uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    setting_key VARCHAR(100) NOT NULL, -- 'active_summary_prompt_id', 'theme', etc.
    setting_value TEXT, -- JSON or simple value
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, setting_key)
);

-- User LLM settings table for storing user-specific LLM provider configurations
-- Each user can have multiple LLM configurations. The active configuration
-- is tracked via the user_setting table with key 'active_llm_config_id'.
CREATE TABLE IF NOT EXISTS user_llm_settings (
    id SERIAL PRIMARY KEY,
    uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL, -- User-friendly name for the configuration
    provider VARCHAR(50) NOT NULL, -- openai, vllm, ollama, claude, custom
    model_name VARCHAR(100) NOT NULL,
    api_key TEXT, -- Encrypted API key
    base_url VARCHAR(500), -- Custom endpoint URL
    max_tokens INTEGER NOT NULL DEFAULT 8192, -- Model's context window in tokens (what user configures as max context)
    temperature VARCHAR(10) NOT NULL DEFAULT '0.3', -- Store as string to avoid float precision issues
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_tested TIMESTAMP WITH TIME ZONE,
    test_status VARCHAR(20), -- success, failed, pending
    test_message TEXT, -- Error message or success details
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, name) -- Ensure unique configuration names per user
);

-- Indexes for prompt and settings queries
CREATE INDEX IF NOT EXISTS idx_summary_prompt_user_id ON summary_prompt(user_id);
CREATE INDEX IF NOT EXISTS idx_summary_prompt_is_system_default ON summary_prompt(is_system_default);
CREATE INDEX IF NOT EXISTS idx_summary_prompt_content_type ON summary_prompt(content_type);

-- Partial unique index: only one system prompt per content_type (allows unlimited user prompts)
CREATE UNIQUE INDEX IF NOT EXISTS unique_system_default_per_content_type
ON summary_prompt(content_type)
WHERE is_system_default = TRUE;

CREATE INDEX IF NOT EXISTS idx_user_setting_user_id ON user_setting(user_id);
CREATE INDEX IF NOT EXISTS idx_user_setting_key ON user_setting(setting_key);

-- Indexes for user LLM settings queries
CREATE INDEX IF NOT EXISTS idx_user_llm_settings_user_id ON user_llm_settings(user_id);
CREATE INDEX IF NOT EXISTS idx_user_llm_settings_provider ON user_llm_settings(provider);
CREATE INDEX IF NOT EXISTS idx_user_llm_settings_active ON user_llm_settings(is_active);

-- UUID indexes for summary_prompt and user_llm_settings (must come after table creation)
CREATE INDEX IF NOT EXISTS idx_summary_prompt_uuid ON summary_prompt(uuid);
CREATE INDEX IF NOT EXISTS idx_user_llm_settings_uuid ON user_llm_settings(uuid);

-- System settings table for global configuration
CREATE TABLE IF NOT EXISTS system_settings (
    id SERIAL PRIMARY KEY,
    key VARCHAR(100) UNIQUE NOT NULL,
    value TEXT,
    description TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index for fast key lookups
CREATE INDEX IF NOT EXISTS idx_system_settings_key ON system_settings(key);

-- Seed default system settings for retry configuration
INSERT INTO system_settings (key, value, description) VALUES
    ('transcription.max_retries', '3', 'Maximum number of retry attempts for failed transcriptions (0 = unlimited)'),
    ('transcription.retry_limit_enabled', 'true', 'Whether to enforce retry limits on transcription processing'),
    ('transcription.garbage_cleanup_enabled', 'true', 'Whether to clean up garbage words (very long words with no spaces) during transcription'),
    ('transcription.max_word_length', '50', 'Maximum word length threshold for garbage detection (words longer than this with no spaces are replaced)')
ON CONFLICT (key) DO NOTHING;

-- Insert system prompts with comprehensive guidance and properly escaped JSON
-- Enhanced with Anthropic prompt engineering best practices (Jan 2025)
INSERT INTO summary_prompt (name, description, prompt_text, is_system_default, content_type, is_active) VALUES
('Universal Content Analyzer', 'Expert content analyst prompt that adapts to different media types with comprehensive BLUF format and topic-based analysis',
'You are an expert content analyst with 10+ years of experience analyzing business meetings, interviews, podcasts, documentaries, and educational content. You specialize in creating actionable BLUF (Bottom Line Up Front) summaries that help busy professionals quickly understand key outcomes.

<task_instructions>
Analyze the provided transcript and generate a comprehensive, structured summary. Your summary will be read by users who need to quickly understand the key outcomes, insights, and action items.

CRITICAL REQUIREMENTS:
1. **Context Detection**: First identify the content type (business meeting, interview, podcast, documentary, etc.) and adapt your analysis accordingly
2. Create a BLUF summary appropriate to the content type:
   - Meetings: Key outcomes and decisions
   - Interviews/Podcasts: Main insights and revelations
   - Documentaries: Key learnings and facts
3. **Topic-Based Analysis**: Focus on major topics and themes rather than chronological timeline
4. **Flexible Structure**: Adapt language and focus based on content type
5. Identify content-appropriate action items, decisions, or key takeaways
6. Use clear, professional language appropriate for the detected content type
7. Your response must be valid JSON matching the exact structure specified

IMPORTANT: The transcript has already been processed with speaker embedding matching. Use the speaker information provided in SPEAKER INFORMATION section - do NOT attempt to identify or rename speakers. Focus on analyzing content and extracting insights.
</task_instructions>

<transcript>
{transcript}
</transcript>

<speaker_information>
{speaker_data}
</speaker_information>

<output_format>
Your response must be valid JSON with this exact structure:

{{
  "bluf": "2-3 sentence Bottom Line Up Front summary. First sentence: what happened/was decided. Second: why it matters/impact. Optional third: next critical action.",

  "brief_summary": "Comprehensive 2-3 paragraph summary providing full context for someone who wasn''t present. Include content type, key dynamics, and significant insights.",

  "major_topics": [
    {{
      "topic": "Clear, descriptive topic title",
      "summary": "Detailed summary of this topic discussion",
      "key_points": [
        "First key point about this topic",
        "Second key point with specific details",
        "Third key point or insight"
      ],
      "timestamp_range": "[00:00] - [05:30]"
    }}
  ],

  "action_items": [
    {{
      "item": "Specific actionable task starting with verb (e.g., ''Update roadmap'')",
      "owner": "Full name of person responsible (or ''Not specified'')",
      "due_date": "Specific date or relative timeframe (e.g., ''Friday'', ''next week'', ''Not specified'')",
      "priority": "high|medium|low",
      "context": "One sentence explaining why this action is needed",
      "mentioned_timestamp": "[MM:SS] approximate timestamp when discussed"
    }}
  ],

  "key_decisions": [
    {{
      "decision": "Clear statement of what was decided",
      "context": "Background and reasoning for the decision",
      "impact": "Expected impact or consequences",
      "stakeholders": ["Person1", "Person2"],
      "timestamp": "[MM:SS]"
    }}
  ],

  "speakers_analysis": [
    {{
      "speaker": "Speaker name or label from transcript",
      "role": "Inferred role based on contributions",
      "talk_time_percentage": 25,
      "key_contributions": [
        "First major contribution or insight",
        "Second significant point they made"
      ]
    }}
  ],

  "follow_up_items": [
    "First follow-up item or unresolved question",
    "Second item requiring future attention"
  ],

  "overall_sentiment": "positive|neutral|negative|mixed",
  "content_type_detected": "meeting|interview|podcast|documentary|educational|general"
}}
</output_format>

<examples>
<example>
<example_name>Business Meeting - Budget Discussion</example_name>
<example_transcript>
John Smith [00:00]: Good morning everyone. Today we need to finalize the Q4 budget allocation.
Sarah Chen [00:15]: I''ve reviewed the numbers. Engineering is over budget by $50K due to unexpected infrastructure costs.
John Smith [00:30]: That''s concerning. Can we reallocate funds from the marketing budget?
Mike Johnson [00:45]: Marketing budget is already tight. We''re running critical campaigns next quarter. I suggest we defer two planned feature releases instead.
Sarah Chen [01:00]: That could work. The features aren''t blocking any customer commitments. I''ll update the roadmap by Friday.
John Smith [01:15]: Agreed. Let''s move forward with that plan. Mike, can you document the impact on our Q1 marketing timeline?
Mike Johnson [01:30]: Absolutely. I''ll have that analysis ready by Wednesday.
</example_transcript>
<example_output>
{{
  "bluf": "Q4 budget requires $50K reduction in engineering costs; team agreed to defer two non-critical feature releases rather than cut marketing campaigns. Sarah Chen will update roadmap by Friday to reflect changes.",
  "brief_summary": "Business meeting addressing Q4 budget overrun in engineering department. The team identified a $50K shortfall due to unexpected infrastructure costs. After evaluating options including marketing budget reallocation, the group decided to defer two planned feature releases that don''t impact customer commitments. This approach preserves critical Q1 marketing campaigns while addressing the budget constraint.",
  "major_topics": [
    {{
      "topic": "Q4 Budget Review and Overrun",
      "summary": "Engineering department exceeded Q4 budget by $50K due to unexpected infrastructure costs. Team evaluated reallocation options.",
      "key_points": [
        "Engineering over budget by $50K from infrastructure costs",
        "Marketing budget already constrained for Q1 campaigns",
        "Feature deferral identified as viable alternative solution"
      ],
      "timestamp_range": "[00:00] - [01:00]"
    }}
  ],
  "action_items": [
    {{
      "item": "Update Q4 roadmap to reflect deferred feature releases",
      "owner": "Sarah Chen",
      "due_date": "Friday",
      "priority": "high",
      "context": "Engineering budget overrun requires feature deferrals to meet Q4 budget constraints",
      "mentioned_timestamp": "[01:00]"
    }},
    {{
      "item": "Document impact of budget decision on Q1 marketing timeline",
      "owner": "Mike Johnson",
      "due_date": "Wednesday",
      "priority": "medium",
      "context": "Need to understand how preserved marketing budget affects Q1 campaign planning",
      "mentioned_timestamp": "[01:30]"
    }}
  ],
  "key_decisions": [
    {{
      "decision": "Defer two planned feature releases to address $50K engineering budget overrun",
      "context": "Engineering exceeded Q4 budget by $50K due to infrastructure costs. Marketing budget reallocation was not viable.",
      "impact": "Q4 product roadmap will be updated. Engineering budget will be balanced without affecting other departments.",
      "stakeholders": ["Sarah Chen", "John Smith", "Mike Johnson"],
      "timestamp": "[01:00]"
    }}
  ],
  "speakers_analysis": [
    {{
      "speaker": "John Smith",
      "role": "Meeting leader / Decision maker",
      "talk_time_percentage": 35,
      "key_contributions": ["Initiated budget discussion", "Proposed marketing reallocation option", "Made final decision on approach"]
    }},
    {{
      "speaker": "Sarah Chen",
      "role": "Engineering lead / Finance representative",
      "talk_time_percentage": 35,
      "key_contributions": ["Identified $50K budget shortfall", "Confirmed feature deferral feasibility", "Committed to roadmap update"]
    }},
    {{
      "speaker": "Mike Johnson",
      "role": "Marketing lead",
      "talk_time_percentage": 30,
      "key_contributions": ["Defended marketing budget", "Suggested feature deferral solution", "Committed to impact analysis"]
    }}
  ],
  "follow_up_items": [
    "Review deferred features for potential Q1 inclusion",
    "Monitor engineering spending through end of Q4"
  ],
  "overall_sentiment": "neutral",
  "content_type_detected": "meeting"
}}
</example_output>
</example>
</examples>

<analysis_guidelines>
**BLUF Format Requirements:**
- First sentence: What happened / what was decided
- Second sentence: Why it matters / what''s the impact
- Optional third sentence: Next critical action
- Total length: 2-3 sentences maximum
- Must be understandable without reading rest of summary

**Good BLUF Examples:**
✓ "Q4 budget requires $50K reduction; team agreed to defer two feature releases rather than cut marketing"
✓ "Product launch delayed 2 weeks due to critical security vulnerability. Security team implementing fix with high priority."

**Bad BLUF Examples:**
✗ "This meeting discussed various topics including budget..." (too vague)
✗ "The team had a productive discussion..." (no concrete outcome)

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

**For Action Items:**
- Start with verb (e.g., "Update roadmap" not "Roadmap needs updating")
- Include specific owner name when mentioned
- Capture timeframe even if relative ("by next meeting", "end of week")
- Explain context briefly - why is this action needed?
- Mark priority based on urgency and importance in discussion

**For Key Decisions:**
- State decision clearly and concisely
- Provide context: what problem does this solve?
- Explain expected impact or consequences
- Note who was involved or affected
- Only include actual decisions, not options discussed
</analysis_guidelines>

Now analyze the provided transcript and generate your structured summary in valid JSON format.',
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

-- Insert default admin user (admin@example.com / password)
INSERT INTO "user" (email, hashed_password, full_name, is_active, is_superuser, role, created_at, updated_at)
VALUES (
    'admin@example.com',
    '$2b$12$XWTq/TQOZgpHNdtjmV28x.ign3DTZIRgIrv.nm2206H6tw9GAspie',
    'Admin User',
    TRUE,
    TRUE,
    'admin',
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
) ON CONFLICT (email) DO NOTHING;

-- Insert default tags
INSERT INTO tag (name, created_at)
VALUES
    ('Important', CURRENT_TIMESTAMP),
    ('Meeting', CURRENT_TIMESTAMP),
    ('Interview', CURRENT_TIMESTAMP),
    ('Personal', CURRENT_TIMESTAMP)
ON CONFLICT (name) DO NOTHING;
