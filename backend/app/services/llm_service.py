"""
LLM Service for OpenTranscribe

Provides unified interface for multiple LLM providers using synchronous HTTP requests.
Designed specifically for Celery tasks - no asyncio conflicts.
"""

import json
import logging
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMProvider(str, Enum):
    OPENAI = "openai"
    VLLM = "vllm"
    OLLAMA = "ollama"
    CLAUDE = "claude"
    ANTHROPIC = "anthropic"
    OPENROUTER = "openrouter"
    CUSTOM = "custom"


@dataclass
class LLMResponse:
    """Standardized response from LLM"""

    content: str
    usage_tokens: Optional[int] = None
    finish_reason: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None


@dataclass
class LLMConfig:
    """Configuration for LLM provider"""

    provider: LLMProvider
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    max_tokens: int = 8192  # User-configured context window
    temperature: float = 0.3
    response_tokens: int = 4000  # Max tokens for response


class LLMService:
    """
    Synchronous LLM service for Celery tasks - no asyncio conflicts
    """

    def __init__(self, config: LLMConfig):
        self.config = config
        self.user_context_window = config.max_tokens  # Store user's context window setting

        # Create session with retry strategy for reliability
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # Provider-specific endpoint mappings
        def build_endpoint(base_url: str) -> str:
            """Build chat completions endpoint"""
            clean_url = base_url.strip().rstrip("/")
            if clean_url.endswith("/v1"):
                return f"{clean_url}/chat/completions"
            else:
                return f"{clean_url}/v1/chat/completions"

        def build_ollama_endpoint(base_url: str) -> str:
            """Build Ollama chat endpoint using native API"""
            clean_url = base_url.strip().rstrip("/")
            # Remove /v1 suffix if present since we're using native API
            if clean_url.endswith("/v1"):
                clean_url = clean_url[:-3]
            return f"{clean_url}/api/chat"

        self.endpoints = {
            LLMProvider.OPENAI: "https://api.openai.com/v1/chat/completions",
            LLMProvider.VLLM: build_endpoint(config.base_url) if config.base_url else None,
            LLMProvider.OLLAMA: build_ollama_endpoint(config.base_url)
            if config.base_url
            else "http://localhost:11434/api/chat",
            LLMProvider.CLAUDE: "https://api.anthropic.com/v1/messages",
            LLMProvider.ANTHROPIC: "https://api.anthropic.com/v1/messages",
            LLMProvider.OPENROUTER: "https://openrouter.ai/api/v1/chat/completions",
            LLMProvider.CUSTOM: build_endpoint(config.base_url) if config.base_url else None,
        }

        if not self.endpoints.get(config.provider):
            raise ValueError(f"Invalid provider configuration for {config.provider}")

        logger.info(
            f"Initialized LLMService: {config.provider}/{config.model}, context_window={self.user_context_window}"
        )

    def _get_headers(self) -> dict[str, str]:
        """
        Get headers for API request based on provider.

        Constructs the appropriate HTTP headers for API requests, including
        authentication headers specific to each LLM provider.

        Returns:
            Dictionary containing HTTP headers for the request

        Note:
            - OpenAI: Uses Bearer token authorization
            - Claude/Anthropic: Uses x-api-key header with anthropic-version
            - OpenRouter: Uses Bearer token with referrer headers
            - vLLM/Ollama: May or may not require authentication
        """
        headers = {"Content-Type": "application/json"}

        if self.config.provider == LLMProvider.OPENAI and self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        elif self.config.provider == LLMProvider.VLLM:
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"
        elif self.config.provider == LLMProvider.OLLAMA:
            pass  # Ollama typically doesn't require auth
        elif self.config.provider in [LLMProvider.CLAUDE, LLMProvider.ANTHROPIC]:
            if self.config.api_key:
                headers["x-api-key"] = self.config.api_key
                headers["anthropic-version"] = "2023-06-01"
        elif self.config.provider == LLMProvider.OPENROUTER and self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
            headers["HTTP-Referer"] = "https://opentranscribe.ai"
            headers["X-Title"] = "OpenTranscribe"
        elif self.config.provider == LLMProvider.CUSTOM and self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        return headers

    def _prepare_payload(self, messages: list[dict[str, str]], **kwargs) -> dict[str, Any]:
        """
        Prepare request payload for the API based on provider requirements.

        Converts standard OpenAI-format messages to provider-specific formats
        and adds appropriate parameters for each LLM provider.

        Args:
            messages: List of message dictionaries in OpenAI format
            **kwargs: Additional parameters to override defaults
                - prefill_json: If True, adds JSON prefill to force structured output

        Returns:
            Dictionary containing the API request payload

        Note:
            - Claude/Anthropic: Separates system messages from user/assistant messages
            - Ollama: Uses native /api/chat format with messages array
            - Other providers: Use standard OpenAI format with provider-specific params
            - Response prefilling: For Claude, adds assistant message with "{" to force JSON
        """

        if self.config.provider in [LLMProvider.CLAUDE, LLMProvider.ANTHROPIC]:
            # Convert OpenAI format messages to Claude format
            system_message = ""
            user_messages = []

            for msg in messages:
                if msg.get("role") == "system":
                    system_message = msg.get("content", "")
                elif msg.get("role") in ["user", "assistant"]:
                    user_messages.append({"role": msg["role"], "content": msg["content"]})

            # Add response prefilling for JSON output if requested
            # This forces Claude to start response with "{" (bypasses preamble)
            if kwargs.get("prefill_json", False):
                # Ensure last message is from user (required for Claude API)
                if user_messages and user_messages[-1]["role"] == "user":
                    user_messages.append({"role": "assistant", "content": "{"})

            payload = {
                "model": self.config.model,
                "messages": user_messages,
                "max_tokens": kwargs.get("max_tokens", self.config.response_tokens),
                "temperature": kwargs.get("temperature", self.config.temperature),
            }

            if system_message:
                payload["system"] = system_message

            return payload

        elif self.config.provider == LLMProvider.OLLAMA:
            # Ollama native /api/chat format
            payload = {
                "model": self.config.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": kwargs.get("temperature", self.config.temperature),
                    "num_predict": kwargs.get("max_tokens", self.config.response_tokens),
                },
            }
            # Add format parameter for structured output if provided
            if "format" in kwargs:
                payload["format"] = kwargs["format"]
            return payload

        # Standard OpenAI-compatible format
        payload = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.config.response_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
            "stream": False,
        }

        # Provider-specific adjustments
        if self.config.provider == LLMProvider.VLLM:
            payload.update(
                {
                    "top_p": kwargs.get("top_p", 0.9),
                    "frequency_penalty": kwargs.get("frequency_penalty", 0.0),
                    "presence_penalty": kwargs.get("presence_penalty", 0.0),
                }
            )

        return payload

    def chat_completion(self, messages: list[dict[str, str]], **kwargs) -> LLMResponse:
        """
        Send chat completion request to LLM provider
        """
        try:
            url = self.endpoints[self.config.provider]
            headers = self._get_headers()
            payload = self._prepare_payload(messages, **kwargs)

            # Log request details for debugging
            total_content_length = sum(len(msg.get("content", "")) for msg in messages)
            logger.info(f"Sending request to {self.config.provider} ({url})")
            logger.info(f"Total request content length: {total_content_length} characters")
            logger.debug(f"Request payload keys: {list(payload.keys())}")

            start_time = time.time()

            # Use appropriate timeout based on content length
            timeout = min(
                1200, max(300, total_content_length // 1000)
            )  # 5-20 minutes based on content
            logger.info(
                f"Using timeout: {timeout} seconds for content length: {total_content_length}"
            )

            response = self.session.post(url, json=payload, headers=headers, timeout=timeout)
            request_time = time.time() - start_time

            logger.info(
                f"LLM request completed in {request_time:.2f}s with status {response.status_code}"
            )

            if response.status_code != 200:
                error_detail = f"LLM API error ({response.status_code}): {response.text[:500]}{'...' if len(response.text) > 500 else ''}"
                logger.error(error_detail)
                raise Exception(f"LLM API error: {response.status_code} - {response.text}")

            try:
                data = response.json()
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM response: {response.text}")
                raise Exception(f"Invalid JSON response: {e}") from e

            # Extract content from response based on provider
            content = ""
            usage_tokens = None
            finish_reason = None

            if self.config.provider in [LLMProvider.CLAUDE, LLMProvider.ANTHROPIC]:
                if "content" not in data or not data["content"]:
                    raise Exception("No content in Claude response")

                content_blocks = data["content"]
                if isinstance(content_blocks, list) and content_blocks:
                    content = content_blocks[0].get("text", "")
                else:
                    content = str(content_blocks)

                if "usage" in data:
                    usage_tokens = data["usage"].get("output_tokens", 0) + data["usage"].get(
                        "input_tokens", 0
                    )

                finish_reason = data.get("stop_reason")
            elif self.config.provider == LLMProvider.OLLAMA:
                # Ollama native response format
                if "message" not in data:
                    logger.error(
                        f"Ollama response missing 'message' field. Response keys: {list(data.keys())}"
                    )
                    logger.debug(f"Full Ollama response: {json.dumps(data, indent=2)}")
                    raise Exception("No message in Ollama response")

                content = data["message"].get("content", "")
                finish_reason = data.get("done_reason", "stop")

                # Debug logging for Ollama responses
                if not content:
                    logger.error(
                        f"Ollama message field exists but content is empty. Message: {data.get('message')}"
                    )
                    logger.debug(f"Full Ollama response: {json.dumps(data, indent=2)}")

                # Ollama provides token counts in separate fields
                if "prompt_eval_count" in data and "eval_count" in data:
                    usage_tokens = data.get("prompt_eval_count", 0) + data.get("eval_count", 0)
            else:
                if "choices" not in data or not data["choices"]:
                    raise Exception("No choices in LLM response")

                choice = data["choices"][0]
                content = choice.get("message", {}).get("content", "")
                finish_reason = choice.get("finish_reason")

                if "usage" in data:
                    usage_tokens = data["usage"].get("total_tokens")

            if not content:
                raise Exception("Empty content in LLM response")

            logger.info(f"LLM request successful, tokens: {usage_tokens}")

            return LLMResponse(
                content=content,
                usage_tokens=usage_tokens,
                finish_reason=finish_reason,
                model=self.config.model,
                provider=self.config.provider.value,
            )

        except requests.exceptions.Timeout as e:
            logger.error(f"Request timed out after {timeout}s for {self.config.provider}: {e}")
            raise Exception(
                f"Request timed out after {timeout} seconds. Content may be too long for processing."
            ) from e
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error to {self.config.provider}: {e}")
            raise Exception(f"Connection error: {e}") from e
        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP error in LLM request: {type(e).__name__}: {e}")
            raise Exception(f"Network error: {e}") from e
        except Exception as e:
            logger.error(
                f"Unexpected error in LLM request to {self.config.provider}: {type(e).__name__}: {e}"
            )
            raise

    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate token count using more accurate heuristics.

        This method provides a reasonable approximation for OpenAI-style tokenization
        without requiring the tiktoken library. The estimation is conservative to
        prevent context window overflow.

        Args:
            text: Input text to tokenize

        Returns:
            Estimated token count

        Note:
            - Uses word-based and character-based heuristics
            - Accounts for common punctuation and formatting
            - Returns slightly higher estimates to be safe
        """
        if not text:
            return 0

        # Basic word count
        words = text.split()
        word_count = len(words)

        # Character-based estimation for better accuracy
        char_count = len(text)

        # Combine both methods:
        # - English averages ~4.7 characters per token
        # - But also consider word boundaries and punctuation
        from app.core.constants import CHARS_PER_TOKEN_ESTIMATE
        from app.core.constants import SUBWORD_TOKENIZATION_FACTOR
        from app.core.constants import TOKEN_ESTIMATION_BUFFER

        char_based_estimate = char_count / CHARS_PER_TOKEN_ESTIMATE
        word_based_estimate = word_count * SUBWORD_TOKENIZATION_FACTOR

        # Use the higher estimate to be conservative
        estimated_tokens = max(char_based_estimate, word_based_estimate)

        # Add buffer for safety
        return int(estimated_tokens * TOKEN_ESTIMATION_BUFFER)

    def _chunk_transcript_intelligently(
        self, transcript: str, chunk_overlap: int = 200
    ) -> list[str]:
        """
        Split transcript into intelligent chunks using ONLY user's max_tokens setting
        """
        # Use user's configured context window - reserve space for prompt and response
        available_tokens = self.user_context_window - 2000  # Reserve for prompt + response
        estimated_tokens = self._estimate_tokens(transcript)

        logger.info(
            f"Chunking transcript: {len(transcript)} chars, estimated {estimated_tokens} tokens"
        )
        logger.info(
            f"Using user context window: {self.user_context_window}, available for content: {available_tokens}"
        )

        if estimated_tokens <= available_tokens:
            logger.info("Transcript fits in single chunk")
            return [transcript]

        # Calculate target size per chunk (conservative)
        target_chars_per_chunk = int(available_tokens * 2.5)
        logger.info(f"Target chars per chunk: {target_chars_per_chunk}")

        chunks = []
        # Split by speaker changes for natural boundaries
        speaker_segments = re.split(r"(\n[A-Z_][A-Z0-9_]*:\s*\[\d+:\d+\])", transcript)

        current_chunk = ""
        current_size = 0

        for segment in speaker_segments:
            segment_size = self._estimate_tokens(segment)

            if current_size + segment_size > available_tokens and current_chunk:
                chunks.append(current_chunk.strip())
                logger.debug(f"Created chunk {len(chunks)}: {len(current_chunk)} chars")
                current_chunk = segment
                current_size = segment_size
            else:
                current_chunk += segment
                current_size += segment_size

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        # Handle oversized chunks by splitting on sentences
        final_chunks = []
        for chunk in chunks:
            if self._estimate_tokens(chunk) <= available_tokens:
                final_chunks.append(chunk)
            else:
                logger.warning("Chunk too large, splitting by sentences")
                sentences = re.split(r"(?<=[.!?])\s+", chunk)
                sub_chunk = ""

                for sentence in sentences:
                    test_chunk = sub_chunk + sentence + " "
                    if self._estimate_tokens(test_chunk) <= available_tokens:
                        sub_chunk = test_chunk
                    else:
                        if sub_chunk.strip():
                            final_chunks.append(sub_chunk.strip())
                        sub_chunk = sentence + " "

                if sub_chunk.strip():
                    final_chunks.append(sub_chunk.strip())

        if not final_chunks and transcript:
            logger.warning("No chunks created, truncating original transcript")
            final_chunks = [transcript[:target_chars_per_chunk]]

        logger.info(
            f"Split transcript into {len(final_chunks)} chunks using user context window: {self.user_context_window}"
        )
        return final_chunks

    def generate_summary(
        self,
        transcript: str,
        speaker_data: Optional[dict[str, Any]] = None,
        user_id: Optional[int] = None,
    ) -> dict[str, Any]:
        """Generate structured summary from transcript"""
        from app.utils.prompt_manager import get_user_active_prompt

        prompt_template = get_user_active_prompt(user_id)

        # Chunk transcript using ONLY user's context window setting
        transcript_chunks = self._chunk_transcript_intelligently(transcript)

        if len(transcript_chunks) == 1:
            # Single chunk processing
            logger.info(f"Processing transcript as single section ({len(transcript)} chars)")
            return self._process_single_chunk(transcript_chunks[0], speaker_data, prompt_template)
        else:
            # Multi-chunk processing
            logger.info(f"Processing transcript in {len(transcript_chunks)} sections")
            return self._process_multiple_chunks(transcript_chunks, speaker_data, prompt_template)

    def _process_single_chunk(
        self, transcript: str, speaker_data: dict, prompt_template: str
    ) -> dict[str, Any]:
        """Process single transcript chunk"""
        formatted_prompt = prompt_template.format(
            transcript=transcript,
            speaker_data=json.dumps(speaker_data or {}, indent=2),
        )

        messages = [
            {
                "role": "system",
                "content": "You are an expert meeting analyst. Analyze transcripts and generate structured summaries in the exact JSON format specified.",
            },
            {"role": "user", "content": formatted_prompt},
        ]

        # Use response prefilling to force JSON output (bypasses preamble)
        response = self.chat_completion(messages, temperature=0.1, prefill_json=True)
        return self._parse_summary_response(response, len(transcript))

    def _process_multiple_chunks(
        self, chunks: list[str], speaker_data: dict, prompt_template: str
    ) -> dict[str, Any]:
        """Process multiple transcript chunks"""
        section_summaries = []

        for i, chunk in enumerate(chunks, 1):
            logger.info(f"Processing section {i}/{len(chunks)} ({len(chunk)} chars)")
            try:
                section_summary = self._summarize_section(
                    chunk, i, len(chunks), speaker_data, prompt_template
                )
                section_summaries.append(section_summary)
                logger.info(f"Section {i} processing completed successfully")
            except Exception as e:
                logger.error(f"Failed to process section {i}: {type(e).__name__}: {e}")
                section_summaries.append(
                    {
                        "key_points": [f"Section {i}: Processing failed - {str(e)[:100]}..."],
                        "speakers_in_section": [],
                        "decisions": [],
                        "action_items": [],
                        "topics_discussed": [],
                    }
                )

        # Combine sections into final summary
        logger.info("Combining section summaries into final comprehensive summary")
        return self._combine_sections(section_summaries, speaker_data, prompt_template, len(chunks))

    def _summarize_section(
        self,
        chunk: str,
        section_num: int,
        total_sections: int,
        speaker_data: dict,
        prompt_template: str,
    ) -> dict[str, Any]:
        """Summarize a single section"""
        formatted_prompt = prompt_template.format(
            transcript=chunk,
            speaker_data=json.dumps(speaker_data or {}, indent=2),
        )

        messages = [
            {
                "role": "system",
                "content": f"You are analyzing section {section_num} of {total_sections}. Provide a structured summary of this section.",
            },
            {"role": "user", "content": formatted_prompt},
        ]

        # Use response prefilling for consistent JSON output
        response = self.chat_completion(
            messages, max_tokens=2000, temperature=0.1, prefill_json=True
        )

        try:
            content = response.content.strip()
            if content.startswith("```json") and content.endswith("```"):
                content = content[7:-3].strip()
            elif content.startswith("```") and content.endswith("```"):
                content = content[3:-3].strip()

            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse section {section_num} JSON: {e}")
            return {
                "key_points": [f"Section {section_num}: Failed to parse structured summary"],
                "speakers_in_section": [],
                "decisions": [],
                "action_items": [],
                "topics_discussed": [],
            }

    def _combine_sections(
        self, sections: list[dict], speaker_data: dict, prompt_template: str, total_sections: int
    ) -> dict[str, Any]:
        """Combine multiple section summaries into final summary"""
        combined_content = f"SECTION SUMMARIES TO COMBINE:\n{json.dumps(sections, indent=2)}"

        formatted_prompt = prompt_template.format(
            transcript=combined_content,
            speaker_data=json.dumps(speaker_data or {}, indent=2),
        )

        messages = [
            {
                "role": "system",
                "content": "You are combining multiple section summaries into a comprehensive BLUF format summary.",
            },
            {"role": "user", "content": formatted_prompt},
        ]

        try:
            # Use response prefilling for final combined summary
            response = self.chat_completion(
                messages, max_tokens=4000, temperature=0.1, prefill_json=True
            )
            return self._parse_summary_response(
                response,
                0,
                {"sections_processed": total_sections, "processing_method": "multi-section"},
            )
        except Exception as e:
            logger.error(f"Failed to combine sections: {e}")
            return {
                "bluf": "Multi-section summary generation completed with partial results.",
                "brief_summary": f"Summary generated from {len(sections)} sections.",
                "major_topics": [],
                "action_items": [],
                "key_decisions": [],
                "follow_up_items": [],
                "metadata": {
                    "provider": self.config.provider.value,
                    "model": self.config.model,
                    "sections_processed": len(sections),
                    "error": f"Section combining failed: {str(e)}",
                },
            }

    def _parse_summary_response(
        self, response: LLMResponse, transcript_length: int, extra_metadata: dict = None
    ) -> dict[str, Any]:
        """
        Parse LLM response into flexible structured summary.

        IMPORTANT: This method accepts ANY valid JSON structure from custom AI prompts.
        No field validation is performed - we trust the LLM to follow the prompt format.
        """
        try:
            content = response.content.strip()

            # Handle response prefilling: if content starts with partial JSON due to prefill,
            # prepend the opening brace that was used in prefilling
            if not content.startswith("{") and not content.startswith("```"):
                content = "{" + content

            # Extract JSON from code blocks
            if content.startswith("```json") and content.endswith("```"):
                content = content[7:-3].strip()
            elif content.startswith("```") and content.endswith("```"):
                content = content[3:-3].strip()

            # Parse JSON - accept ANY structure
            summary_data = json.loads(content)

            # NO FIELD VALIDATION - accept any structure from custom prompts

            # Add metadata
            metadata = {
                "provider": self.config.provider.value,
                "model": self.config.model,
                "usage_tokens": response.usage_tokens,
                "transcript_length": transcript_length,
                "user_context_window": self.user_context_window,
            }

            if extra_metadata:
                metadata.update(extra_metadata)

            summary_data["metadata"] = metadata

            logger.info(
                f"Successfully parsed flexible summary with fields: {list(summary_data.keys())}"
            )
            return summary_data

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse summary JSON: {e}")
            logger.error(f"Response content: {response.content[:500]}...")

            # Return minimal error structure
            return {
                "error": "JSON parsing failed",
                "error_detail": str(e),
                "raw_response_preview": response.content[:500],
                "metadata": {
                    "provider": self.config.provider.value,
                    "model": self.config.model,
                    "error": f"JSON parsing failed: {str(e)}",
                    "user_context_window": self.user_context_window,
                },
            }

    def validate_connection(self) -> tuple[bool, str]:
        """
        Validate connection to LLM provider

        Returns:
            Tuple of (success, message)
        """
        try:
            headers = self._get_headers()

            # Claude/Anthropic providers don't have a models endpoint, test with a simple request
            if self.config.provider in [LLMProvider.CLAUDE, LLMProvider.ANTHROPIC]:
                # Test with a simple message
                test_messages = [{"role": "user", "content": "Hi"}]
                response = self.chat_completion(test_messages, max_tokens=5)
                if response and response.content and response.content.strip():
                    return (
                        True,
                        f"Connection successful - Model responded: '{response.content[:50]}'",
                    )
                else:
                    return False, "Connection established but model returned empty response"

            else:
                # For other providers, test with models endpoint
                base_url = (
                    self.config.base_url.strip().rstrip("/") if self.config.base_url else None
                )
                if not base_url:
                    return False, "No base URL configured"

                if base_url.endswith("/v1"):
                    models_url = f"{base_url}/models"
                else:
                    models_url = f"{base_url}/v1/models"

                response = self.session.get(models_url, headers=headers, timeout=10)

                if response.status_code == 200:
                    return True, "Connection successful (models endpoint responded)"
                else:
                    return False, f"Models endpoint failed with status {response.status_code}"

        except Exception as e:
            return False, f"Connection failed: {str(e)}"

    def close(self):
        """
        Close the session and clean up resources.

        Properly closes the HTTP session and releases any held connections.
        Should be called when the LLMService instance is no longer needed.
        """
        if hasattr(self, "session"):
            try:
                self.session.close()
                logger.debug(f"Closed session for {self.config.provider}")
            except Exception as e:
                logger.warning(f"Error closing session: {e}")

    def identify_speakers(
        self, transcript: str, speaker_segments: list, known_speakers: list
    ) -> dict:
        """
        Use LLM to suggest speaker identifications based on contextual analysis of speech patterns,
        conversation content, and known speaker profiles.

        Args:
            transcript: Full transcript text with speaker labels
            speaker_segments: List of speaker segments with metadata including timestamps and text
            known_speakers: List of known speaker profiles with names and descriptions

        Returns:
            Dictionary containing speaker predictions with confidence scores and reasoning
        """
        try:
            # Build comprehensive system prompt for speaker identification
            system_prompt = """You are an expert linguist and conversation analyst specializing in speaker identification. Your task is to analyze transcripts and identify speakers based on multiple contextual clues.

ANALYSIS METHODOLOGY:
1. Speech Patterns & Style:
   - Vocabulary complexity and professional terminology
   - Sentence structure and communication style
   - Use of technical jargon, industry-specific language
   - Formal vs. informal speech patterns

2. Content Analysis:
   - Topics of expertise and knowledge domains
   - Professional roles and responsibilities mentioned
   - Personal anecdotes or experiences shared
   - Areas where speakers demonstrate authority or deep knowledge

3. Conversational Dynamics:
   - Who asks questions vs. provides answers
   - Leadership patterns and decision-making roles
   - Deference patterns between speakers
   - Introduction patterns and name mentions

4. Context Clues:
   - Direct name mentions in conversation
   - Role references ("as the CEO", "from engineering", etc.)
   - Historical context from previous conversations
   - Cross-references to known speaker profiles

CONFIDENCE SCORING:
- 0.9-1.0: Multiple strong indicators align (name mentioned + role + speech pattern match)
- 0.7-0.89: Strong contextual match with known profile (expertise area + communication style)
- 0.5-0.69: Moderate confidence based on partial indicators
- Below 0.5: Insufficient evidence for reliable identification

Only provide predictions with confidence >= 0.5. Explain your reasoning clearly for each identification."""

            # Prepare known speakers context with rich descriptions
            known_speakers_context = ""
            if known_speakers and len(known_speakers) > 0:
                known_speakers_context = "\n\nKNOWN SPEAKER PROFILES:\n"
                for i, speaker in enumerate(known_speakers[:15]):  # Limit to prevent token overflow
                    description = speaker.get("description", "No description available")
                    known_speakers_context += f"{i + 1}. {speaker['name']}: {description}\n"
            else:
                known_speakers_context = "\n\nNo known speaker profiles provided for comparison.\n"

            # Extract unique speaker labels from segments
            speaker_labels = list(
                set(
                    seg.get("speaker_label", "Unknown")
                    for seg in speaker_segments
                    if seg.get("speaker_label")
                )
            )

            # Calculate available tokens for transcript content
            # Reserve tokens for system prompt, known speakers, response, and formatting
            reserved_tokens = (
                len(system_prompt) // 3 + len(known_speakers_context) // 3 + 2000 + 500
            )  # Rough token estimation
            available_tokens = max(1000, self.user_context_window - reserved_tokens)

            # Truncate transcript if needed, trying to preserve important context
            transcript_content = transcript
            if len(transcript) > available_tokens * 3:  # Rough char to token ratio
                # Try to keep beginning and end of transcript for context
                target_length = available_tokens * 3
                half_length = target_length // 2
                transcript_content = (
                    transcript[:half_length]
                    + "\n\n[... middle content truncated ...]\n\n"
                    + transcript[-half_length:]
                )

            # Build comprehensive user prompt
            user_prompt = f"""TRANSCRIPT TO ANALYZE:
{transcript_content}

CURRENT SPEAKER LABELS: {", ".join(speaker_labels)}
{known_speakers_context}

TASK:
Analyze this conversation transcript and identify each speaker label based on the methodology described. Look for patterns in:
- Speech complexity and professional vocabulary usage
- Areas of expertise demonstrated through conversation content
- Leadership and authority patterns in the discussion
- Any direct or indirect name mentions or role references
- Communication styles and interpersonal dynamics

For each speaker you can identify with reasonable confidence (≥0.5), provide a detailed analysis.

RESPONSE FORMAT (JSON):
{{
    "speaker_predictions": [
        {{
            "speaker_label": "SPEAKER_1",
            "predicted_name": "John Smith",
            "confidence": 0.85,
            "reasoning": "Detailed explanation of evidence including speech patterns, expertise areas, and specific quotes or behaviors that led to this identification",
            "evidence_types": ["speech_pattern", "expertise", "role_reference", "name_mention"]
        }}
    ],
    "overall_confidence": "high",
    "analysis_notes": "Brief summary of the identification process and any challenges encountered"
}}

IMPORTANT: Only include predictions with confidence ≥ 0.5. If you cannot confidently identify any speakers, return an empty predictions array."""

            # Generate response with user's configured token limit
            # Use quote extraction technique (improves recall from ~27% to ~98%)
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
                # Prefill response to force quote extraction first
                {
                    "role": "assistant",
                    "content": "Let me identify the most relevant evidence for each speaker:\n\nRELEVANT QUOTES AND EVIDENCE:\n",
                },
            ]

            # Use conservative response token limit based on user's context window
            response_tokens = min(self.config.response_tokens, self.user_context_window // 4)

            response = self.chat_completion(
                messages=messages,
                max_tokens=response_tokens,
                temperature=0.2,  # Lower temperature for more consistent and reliable identification
            )

            if not response or not response.content:
                logger.warning("LLM returned empty response for speaker identification")
                return {"speaker_predictions": [], "error": "No response from LLM"}

            # Parse and validate JSON response
            try:
                # Clean up response content - remove markdown code blocks if present
                content = response.content.strip()

                # Strip markdown code fences first
                if content.startswith("```json") and "```" in content[7:]:
                    # Find closing fence and extract content between them
                    fence_end = content.find("```", 7)
                    content = content[7:fence_end].strip()
                elif content.startswith("```") and "```" in content[3:]:
                    # Find closing fence and extract content between them
                    fence_end = content.find("```", 3)
                    content = content[3:fence_end].strip()
                    # Remove language identifier if present (e.g., "json\n")
                    if content.startswith(("json", "JSON")):
                        content = content[4:].lstrip()

                # Extract JSON from response (may include quote section first due to prefilling)
                # Look for JSON object starting with { after any prefilled quote section
                json_start = content.find("{")
                if json_start > 0:
                    content = content[json_start:]

                # Find the matching closing brace for the JSON object
                # This handles cases where there's extra text after the JSON
                if content.startswith("{"):
                    brace_count = 0
                    json_end = 0
                    for i, char in enumerate(content):
                        if char == "{":
                            brace_count += 1
                        elif char == "}":
                            brace_count -= 1
                            if brace_count == 0:
                                json_end = i + 1
                                break
                    if json_end > 0:
                        content = content[:json_end]

                result = json.loads(content)

                # Validate response structure
                if not isinstance(result, dict):
                    logger.error("LLM response is not a valid JSON object")
                    return {
                        "speaker_predictions": [],
                        "error": "Invalid response format - not a JSON object",
                    }

                if "speaker_predictions" not in result:
                    logger.error("LLM response missing required 'speaker_predictions' field")
                    return {
                        "speaker_predictions": [],
                        "error": "Invalid response format - missing speaker_predictions",
                    }

                # Validate prediction structure
                predictions = result["speaker_predictions"]
                if not isinstance(predictions, list):
                    logger.error("speaker_predictions is not a list")
                    return {
                        "speaker_predictions": [],
                        "error": "Invalid response format - speaker_predictions must be a list",
                    }

                # Filter predictions by confidence threshold and validate structure
                valid_predictions = []
                for pred in predictions:
                    if not isinstance(pred, dict):
                        continue

                    required_fields = ["speaker_label", "predicted_name", "confidence"]
                    if not all(field in pred for field in required_fields):
                        logger.warning(f"Skipping prediction with missing fields: {pred}")
                        continue

                    confidence = pred.get("confidence", 0.0)
                    if not isinstance(confidence, (int, float)) or confidence < 0.5:
                        continue

                    valid_predictions.append(pred)

                logger.info(
                    f"Speaker identification completed: {len(valid_predictions)} valid predictions from {len(predictions)} total"
                )

                return {
                    "speaker_predictions": valid_predictions,
                    "overall_confidence": result.get("overall_confidence", "unknown"),
                    "analysis_notes": result.get("analysis_notes", "No additional notes provided"),
                }

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM identification response as JSON: {e}")
                logger.error(f"Raw response content: {response.content[:500]}...")
                return {"speaker_predictions": [], "error": f"Invalid JSON response: {str(e)}"}

        except Exception as e:
            logger.error(f"Speaker identification failed with error: {e}", exc_info=True)
            return {"speaker_predictions": [], "error": f"Identification process failed: {str(e)}"}

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with automatic cleanup."""
        self.close()

    def health_check(self) -> bool:
        """
        Quick health check using the models endpoint

        Returns:
            True if LLM is available, False otherwise
        """
        try:
            headers = self._get_headers()

            # Build models endpoint URL
            base_url = self.config.base_url.strip().rstrip("/") if self.config.base_url else None
            if not base_url:
                logger.info("Health check failed: No base URL configured")
                return False

            if base_url.endswith("/v1"):
                models_url = f"{base_url}/models"
            else:
                models_url = f"{base_url}/v1/models"

            logger.info(f"Health check using models endpoint: {models_url}")

            response = self.session.get(models_url, headers=headers, timeout=10)
            logger.info(f"Health check response status: {response.status_code}")

            if response.status_code == 200:
                # Optionally verify our model is in the list
                try:
                    data = response.json()
                    if "data" in data:
                        model_ids = [model.get("id") for model in data["data"]]
                        if self.config.model in model_ids:
                            logger.info(f"Model {self.config.model} found in available models")
                            return True
                        else:
                            logger.warning(
                                f"Model {self.config.model} not found in available models: {model_ids}"
                            )
                            return False  # Model not available
                    return True
                except Exception as e:
                    logger.debug(f"Could not parse models response, but got 200: {e}")
                    return True  # Service is up even if we can't parse response
            else:
                logger.info(f"Models endpoint returned status {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Health check failed for {self.config.provider}: {e}", exc_info=True)
            return False

    @staticmethod
    def create_from_settings(user_id: Optional[int] = None) -> Optional["LLMService"]:
        """
        Create LLMService from user-specific settings only

        Args:
            user_id: If provided, attempts to load user-specific settings

        Returns:
            LLMService configured with user settings, or None if no user LLM is configured
        """
        # Try to load user-specific settings
        if user_id:
            try:
                user_service = LLMService.create_from_user_settings(user_id)
                if user_service:
                    return user_service
            except Exception as e:
                logger.warning(f"Failed to load user LLM settings for user {user_id}: {e}")

        # No fallback - users must explicitly configure LLM settings
        logger.info(f"No active LLM configuration found for user {user_id}")
        return None

    @staticmethod
    def create_from_user_settings(user_id: int) -> Optional["LLMService"]:
        """Create LLMService from user-specific database settings"""
        from app import models
        from app.db.base import SessionLocal
        from app.models.user_llm_settings import UserLLMSettings
        from app.utils.encryption import decrypt_api_key

        db = SessionLocal()
        try:
            # Get user's active LLM configuration
            active_config_setting = (
                db.query(models.UserSetting)
                .filter(
                    models.UserSetting.user_id == user_id,
                    models.UserSetting.setting_key == "active_llm_config_id",
                )
                .first()
            )

            if not active_config_setting or not active_config_setting.setting_value:
                logger.info(
                    f"No active LLM configuration for user {user_id}, checking system settings"
                )
                return LLMService.create_from_system_settings()

            # Get the active LLM configuration
            active_config_id = int(active_config_setting.setting_value)
            user_settings = (
                db.query(UserLLMSettings)
                .filter(
                    UserLLMSettings.user_id == user_id,
                    UserLLMSettings.id == active_config_id,
                )
                .first()
            )

            if not user_settings:
                logger.warning(
                    f"Active LLM config {active_config_id} not found for user {user_id}, checking system settings"
                )
                return LLMService.create_from_system_settings()

            # Decrypt API key if present
            api_key = None
            if user_settings.api_key:
                api_key = decrypt_api_key(user_settings.api_key)
                if not api_key and user_settings.api_key:
                    logger.error(f"Failed to decrypt API key for user {user_id}")
                    return LLMService.create_from_system_settings()

            # Create config from user settings - USE ONLY USER'S MAX_TOKENS
            provider = LLMProvider(user_settings.provider)
            temperature_float = float(user_settings.temperature)

            config = LLMConfig(
                provider=provider,
                model=user_settings.model_name,
                api_key=api_key,
                base_url=user_settings.base_url,
                max_tokens=user_settings.max_tokens,  # USER'S CONTEXT WINDOW - NO INFERENCE
                temperature=temperature_float,
            )

            logger.info(
                f"Created LLMService for user {user_id}: {provider}/{user_settings.model_name}, user_context_window={user_settings.max_tokens}"
            )
            return LLMService(config)

        except (ValueError, KeyError) as e:
            logger.error(f"Configuration error for user {user_id}: {e}")
            return LLMService.create_from_system_settings()
        except Exception as e:
            logger.error(
                f"Unexpected error creating LLMService from user settings for user {user_id}: {e}"
            )
            return LLMService.create_from_system_settings()
        finally:
            db.close()

    @staticmethod
    def create_from_system_settings() -> Optional["LLMService"]:
        """Create LLMService from system settings"""
        if not settings.LLM_PROVIDER or settings.LLM_PROVIDER.strip() == "":
            logger.info("No LLM provider configured (LLM_PROVIDER not set)")
            return None

        try:
            provider = LLMProvider(settings.LLM_PROVIDER)
        except ValueError as e:
            logger.warning(f"Invalid LLM provider '{settings.LLM_PROVIDER}': {e}")
            return None

        # Provider-specific configuration with validation
        if provider == LLMProvider.VLLM:
            model = settings.VLLM_MODEL_NAME
            api_key = settings.VLLM_API_KEY or None
            base_url = settings.VLLM_BASE_URL
            # Validate required settings for vLLM
            if not model or model.strip() == "gpt-oss":  # Invalid default model name
                logger.info("vLLM provider configured but no valid model name set")
                return None
            if (
                not base_url or base_url == "http://localhost:8012/v1"
            ):  # Default that likely won't work
                logger.info(
                    "vLLM provider configured but using default localhost endpoint (likely not available)"
                )
                return None
        elif provider == LLMProvider.OPENAI:
            model = settings.OPENAI_MODEL_NAME
            api_key = settings.OPENAI_API_KEY or None
            base_url = settings.OPENAI_BASE_URL
            # Validate required settings for OpenAI
            if not model or not model.strip():
                logger.info("OpenAI provider configured but no model name set")
                return None
            if not api_key or not api_key.strip():
                logger.info("OpenAI provider configured but no API key set")
                return None
        elif provider == LLMProvider.OLLAMA:
            model = settings.OLLAMA_MODEL_NAME
            api_key = None
            base_url = settings.OLLAMA_BASE_URL
            # Validate required settings for Ollama
            if not model or not model.strip():
                logger.info("Ollama provider configured but no model name set")
                return None
        elif provider == LLMProvider.CLAUDE:
            model = settings.ANTHROPIC_MODEL_NAME
            api_key = settings.ANTHROPIC_API_KEY or None
            base_url = settings.ANTHROPIC_BASE_URL
            # Validate required settings for Claude/Anthropic
            if not model or not model.strip():
                logger.info("Claude/Anthropic provider configured but no model name set")
                return None
            if not api_key or not api_key.strip():
                logger.info("Claude/Anthropic provider configured but no API key set")
                return None
        else:
            logger.warning(f"Unsupported LLM provider: {provider}")
            return None

        try:
            config = LLMConfig(
                provider=provider,
                model=model,
                api_key=api_key,
                base_url=base_url,
                max_tokens=32768,  # Conservative system default
                temperature=0.3,
            )

            logger.info(
                f"Created LLMService from system settings: {provider}/{model}, context_window={config.max_tokens}"
            )
            return LLMService(config)
        except Exception as e:
            logger.error(f"Failed to create LLMService from system settings: {e}")
            return None


# Context manager for proper cleanup
class LLMServiceContext:
    """Context manager for LLM service with proper cleanup"""

    def __init__(self, service: Optional[LLMService] = None, user_id: Optional[int] = None):
        self.service = service
        self.user_id = user_id
        self._created_service = service is None

    def __enter__(self) -> Optional["LLMService"]:
        if self.service is None:
            self.service = (
                LLMService.create_from_user_settings(self.user_id)
                if self.user_id
                else LLMService.create_from_system_settings()
            )
            if self.service is None:
                logger.info("LLM service is not available - no provider configured")
                return None
        return self.service

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.service and self._created_service:
            self.service.close()


# Utility function for quick LLM availability check
async def is_llm_available(user_id: Optional[int] = None) -> bool:
    """
    Quick check to see if any LLM provider is available

    Args:
        user_id: Optional user ID to check user-specific LLM settings

    Returns:
        True if at least one LLM provider is available, False otherwise
    """
    try:
        logger.info(f"Checking LLM availability for user {user_id}")
        # First check if we can even create an LLM service
        llm_service = LLMService.create_from_settings(user_id=user_id)
        if llm_service is None:
            logger.info("No LLM service configured")
            return False

        logger.info(
            f"LLM service created successfully: {llm_service.config.provider}/{llm_service.config.model}"
        )
        # Then check if it's actually working
        health_ok = llm_service.health_check()
        logger.info(f"Health check result: {health_ok}")
        llm_service.close()
        return health_ok
    except Exception as e:
        logger.error(f"LLM availability check failed: {e}", exc_info=True)
        return False
