"""
AI Suggestion Service for Tags and Collections

This service uses LLM to analyze transcripts and suggest relevant tags and
collections to help users organize their media library. It follows prompt
engineering best practices from PROMPT_ENGINEERING_GUIDE.md.

Key Features:
    - Extracts 3-10 searchable tags per transcript
    - Suggests 1-3 collections for grouping related content
    - Provides confidence scores for each suggestion
    - Stores suggestions in PostgreSQL JSONB for easy access
    - Tracks user decisions for future analytics
"""

import json
import logging
import re
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.models.media import MediaFile
from app.models.topic import TopicSuggestion
from app.schemas.topic import LLMSuggestionResponse
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)


class TopicExtractionService:
    """
    Service for extracting tag and collection suggestions from transcripts using LLM

    Simplified workflow:
    1. Build XML-structured prompt following best practices
    2. Call LLM with low temperature for consistency
    3. Parse and validate JSON response
    4. Store suggestions in PostgreSQL
    """

    # System prompt for suggestion extraction
    SYSTEM_PROMPT = """You are an expert content analyst specializing in media organization and categorization.

YOUR TASK:
Analyze transcripts and suggest tags and collections to help users organize their media library.

TAGS:
- Short, searchable keywords (1-3 words, lowercase)
- Focus on substantive topics discussed
- Help users find content through search

COLLECTIONS:
- User-friendly group names for related content
- Help users organize their library naturally
- Descriptive but concise

YOUR APPROACH:
- Focus on content that matters (ignore small talk, logistics)
- Be specific enough to be useful, broad enough to group similar content
- Provide clear confidence scores (0.0-1.0)
- Consider what users would search for

OUTPUT STANDARD:
- Always return valid JSON matching the specified schema
- Be conservative with confidence scores (only 0.8+ for very clear suggestions)
- Suggest 3-10 tags and 1-3 collections per transcript"""

    # Main extraction prompt template (XML-structured)
    EXTRACTION_PROMPT_TEMPLATE = """<documents>
<document index="1">
  <source>transcript</source>
  <metadata>
    <file_id>{file_id}</file_id>
    <duration_seconds>{duration}</duration_seconds>
  </metadata>
  <document_content>
{transcript}
  </document_content>
</document>
</documents>

<task_instructions>
Analyze this transcript and suggest tags and collections for organizing this media file.

ANALYSIS PROCESS (use <thinking> tags to show your reasoning):
1. Read through the transcript and identify main topics
2. Ignore logistics, small talk, and formalities
3. Extract searchable tags (specific topics, keywords)
4. Suggest 1-3 collections that would group similar content
5. Provide confidence scores based on clarity

<thinking>
[Your step-by-step analysis here:
- What are the main subjects discussed?
- What tags would help someone find this content?
- What collections would naturally group this with related content?
- How confident am I in each suggestion?]
</thinking>

<answer>
Provide your response as valid JSON matching this exact schema:

{{
  "suggested_collections": [
    {{
      "name": "Collection Name",
      "confidence": 0.85,
      "rationale": "Brief explanation why this groups related content"
    }}
  ],
  "suggested_tags": [
    {{
      "name": "tag-name",
      "confidence": 0.90,
      "rationale": "Brief explanation why this tag fits"
    }}
  ]
}}
</answer>

IMPORTANT GUIDELINES:
- Extract 3-10 tags (specific topics, not generic)
- Suggest 1-3 collections maximum
- Tags should be lowercase, short (1-3 words), searchable
- Collections should be user-friendly and descriptive
- Focus on substantive content, not meeting logistics
- Confidence scores: 0.8+ for clear, 0.5-0.8 for moderate, <0.5 for uncertain
- Do NOT suggest generic tags like "discussion", "meeting", "conversation"
</task_instructions>
"""

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def create_from_settings(user_id: int, db: Session) -> Optional["TopicExtractionService"]:
        """
        Create AI suggestion service if LLM is configured for the user.

        Args:
            user_id: User ID for LLM configuration
            db: Database session

        Returns:
            TopicExtractionService instance if LLM configured, None otherwise
        """
        try:
            # Try to create LLM service to check if configured
            llm_service = LLMService.create_from_settings(user_id=user_id)
            if llm_service:
                return TopicExtractionService(db)
            else:
                logger.info(f"LLM not configured for user {user_id}, skipping topic extraction")
                return None
        except Exception as e:
            logger.warning(f"Could not create topic extraction service: {e}")
            return None

    def extract_topics(
        self,
        media_file_id: int,
        force_regenerate: bool = False,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Optional[TopicSuggestion]:
        """
        Extract tag and collection suggestions from a transcript using LLM

        Args:
            media_file_id: Media file ID
            force_regenerate: Force re-extraction even if exists
            progress_callback: Optional callback function for progress updates

        Returns:
            TopicSuggestion instance or None
        """
        # Get media file
        media_file = self.db.query(MediaFile).filter(MediaFile.id == media_file_id).first()
        if not media_file:
            logger.error(f"Media file {media_file_id} not found")
            return None

        # Check if suggestion already exists
        existing = (
            self.db.query(TopicSuggestion)
            .filter(TopicSuggestion.media_file_id == media_file_id)
            .first()
        )

        if existing and not force_regenerate:
            logger.info(
                f"Topic suggestion already exists for file {media_file_id}, use force_regenerate to re-extract"
            )
            return existing

        # Notify: Reading transcript
        if progress_callback:
            progress_callback("Reading transcript from database...")

        # Get transcript text
        transcript = self._get_transcript_text(media_file)
        if not transcript:
            logger.error(f"No transcript available for file {media_file_id}")
            return None

        # Create LLM service
        llm_service = LLMService.create_from_settings(user_id=media_file.user_id)
        if not llm_service:
            logger.warning(f"LLM not configured for user {media_file.user_id}")
            return None

        # Notify: Building AI prompt
        if progress_callback:
            progress_callback("Building AI prompt...")

        # Extract suggestions using LLM
        logger.info(
            f"Extracting suggestions for file {media_file_id} using {llm_service.config.provider}"
        )

        # Notify: Calling LLM
        if progress_callback:
            progress_callback("Calling AI model (this may take a moment)...")

        llm_response = self._call_llm_for_extraction(
            llm_service=llm_service,
            transcript=transcript,
            file_id=media_file_id,
            duration=media_file.duration or 0,
        )

        # Notify: Processing response
        if progress_callback:
            progress_callback("Processing AI response...")

        if not llm_response:
            logger.error(f"Failed to extract suggestions for file {media_file_id}")
            return None

        # Store suggestions in PostgreSQL
        suggestion = self._store_suggestion(
            media_file=media_file,
            llm_response=llm_response,
        )

        return suggestion

    def apply_suggestions(
        self,
        suggestion_id: int,
        accepted_collections: list[str],
        accepted_tags: list[str],
    ) -> bool:
        """
        Apply user-approved tag and collection suggestions

        Args:
            suggestion_id: TopicSuggestion ID
            accepted_collections: Collection names to create/add to
            accepted_tags: Tag names to apply

        Returns:
            True if successful
        """
        # Get suggestion
        suggestion = (
            self.db.query(TopicSuggestion).filter(TopicSuggestion.id == suggestion_id).first()
        )
        if not suggestion:
            logger.error(f"Topic suggestion {suggestion_id} not found")
            return False

        try:
            # Keep status as "pending" so suggestions remain available
            # Track what user has accepted in user_decisions for analytics
            existing_decisions = suggestion.user_decisions or {}
            existing_decisions.setdefault("accepted_collections", []).extend(accepted_collections)
            existing_decisions.setdefault("accepted_tags", []).extend(accepted_tags)

            # Remove duplicates
            existing_decisions["accepted_collections"] = list(
                set(existing_decisions["accepted_collections"])
            )
            existing_decisions["accepted_tags"] = list(set(existing_decisions["accepted_tags"]))

            suggestion.user_decisions = existing_decisions

            self.db.commit()

            logger.info(f"Applied suggestions for file {suggestion.media_file_id}")
            return True

        except Exception as e:
            logger.error(f"Error applying suggestions: {e}")
            self.db.rollback()
            return False

    def _get_transcript_text(self, media_file: MediaFile) -> Optional[str]:
        """Extract transcript text from media file"""
        from app.models.media import TranscriptSegment

        segments = (
            self.db.query(TranscriptSegment)
            .filter(TranscriptSegment.media_file_id == media_file.id)
            .order_by(TranscriptSegment.start_time)
            .all()
        )

        if not segments:
            return None

        # Combine segments into full transcript
        transcript_parts = []
        for segment in segments:
            speaker_name = segment.speaker.display_name if segment.speaker else "Unknown"
            transcript_parts.append(f"{speaker_name}: {segment.text}")

        return "\n".join(transcript_parts)

    def _call_llm_for_extraction(
        self, llm_service: LLMService, transcript: str, file_id: int, duration: float
    ) -> Optional[LLMSuggestionResponse]:
        """
        Call LLM to extract suggestions from transcript with provider-specific optimizations

        Args:
            llm_service: LLM service instance
            transcript: Full transcript text
            file_id: Media file ID
            duration: Duration in seconds

        Returns:
            Parsed LLM response or None
        """
        from app.services.llm_service import LLMProvider

        # Build prompt
        prompt = self.EXTRACTION_PROMPT_TEMPLATE.format(
            file_id=file_id,
            duration=duration,
            transcript=transcript[:50000],  # Limit to first 50k chars to avoid token limits
        )

        # Prepare messages with provider-specific optimizations
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        # Provider-specific optimizations
        kwargs = {"temperature": 0.1}

        if llm_service.config.provider in [LLMProvider.CLAUDE, LLMProvider.ANTHROPIC]:
            # Claude: Use response prefilling to force structured output
            messages.append({"role": "assistant", "content": "<thinking>\n"})
        elif llm_service.config.provider == LLMProvider.OLLAMA:
            # Ollama: Don't use format parameter - some models (like gpt-oss) don't support it well
            # Instead rely on prompt engineering and normal JSON extraction
            # The prompt already instructs the model to return JSON in <answer> tags
            pass

        try:
            # Call LLM with provider-specific parameters
            response = llm_service.chat_completion(messages, **kwargs)

            # Parse response
            return self._parse_llm_response(response.content, llm_service.config.provider)

        except Exception as e:
            logger.error(f"Error calling LLM for suggestion extraction: {e}")
            return None

    def _parse_llm_response(
        self, response_text: str, provider: "LLMProvider"
    ) -> Optional[LLMSuggestionResponse]:
        """
        Parse LLM response and extract JSON with provider-specific handling

        Args:
            response_text: Raw LLM response
            provider: LLM provider type

        Returns:
            Parsed response or None
        """
        from app.services.llm_service import LLMProvider

        try:
            json_str = None

            # For all providers, try to extract JSON from <answer> tags first
            json_match = re.search(
                r"<answer>\s*(\{.*?\})\s*</answer>", response_text, re.DOTALL
            )
            if json_match:
                json_str = json_match.group(1)
            else:
                # Try to find JSON object directly (greedy match to get full object)
                json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)

            if not json_str:
                logger.error("Could not find JSON in LLM response")
                logger.error(f"Response text (first 1000 chars): {response_text[:1000]}")
                return None

            # Parse JSON
            data = json.loads(json_str)

            # Validate and convert to Pydantic model
            return LLMSuggestionResponse(**data)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from LLM response: {e}")
            logger.error(f"Attempted to parse: {json_str[:500] if json_str else 'None'}")
            logger.error(f"Full response text (first 1000 chars): {response_text[:1000]}")
            return None
        except Exception as e:
            logger.error(f"Error parsing LLM response: {e}")
            logger.error(f"Response text (first 1000 chars): {response_text[:1000]}")
            return None

    def _store_suggestion(
        self,
        media_file: MediaFile,
        llm_response: LLMSuggestionResponse,
    ) -> Optional[TopicSuggestion]:
        """
        Store suggestion in PostgreSQL

        Args:
            media_file: Media file instance
            llm_response: Parsed LLM response

        Returns:
            TopicSuggestion instance or None
        """
        try:
            # Convert Pydantic models to dicts for JSONB storage
            suggested_tags = [tag.dict() for tag in llm_response.suggested_tags]
            suggested_collections = [coll.dict() for coll in llm_response.suggested_collections]

            # Check if suggestion already exists
            existing = (
                self.db.query(TopicSuggestion)
                .filter(TopicSuggestion.media_file_id == media_file.id)
                .first()
            )

            if existing:
                # Update existing
                existing.suggested_tags = suggested_tags
                existing.suggested_collections = suggested_collections
                existing.status = "pending"
                suggestion = existing
            else:
                # Create new suggestion
                suggestion = TopicSuggestion(
                    media_file_id=media_file.id,
                    user_id=media_file.user_id,
                    suggested_tags=suggested_tags,
                    suggested_collections=suggested_collections,
                    status="pending",
                )
                self.db.add(suggestion)

            self.db.commit()
            self.db.refresh(suggestion)

            logger.info(
                f"Stored {len(suggested_tags)} tags and {len(suggested_collections)} collections for file {media_file.id}"
            )

            return suggestion

        except Exception as e:
            logger.error(f"Error storing suggestion: {e}")
            self.db.rollback()
            return None
