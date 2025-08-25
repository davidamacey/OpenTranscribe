"""
LLM Service for OpenTranscribe

Provides unified interface for multiple LLM providers including OpenAI-compatible APIs
like vLLM, Ollama, Claude, and others.
"""

import logging
import json
import aiohttp
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import time
import re

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMProvider(str, Enum):
    OPENAI = "openai"
    VLLM = "vllm"
    OLLAMA = "ollama"
    CLAUDE = "claude"
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
    max_tokens: int = 2000
    temperature: float = 0.3
    timeout: int = 60


class LLMService:
    """
    Unified LLM service supporting multiple providers with OpenAI-compatible APIs
    """
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self.session = None
        
        # Provider-specific endpoint mappings
        def build_endpoint(base_url: str) -> str:
            """Build chat completions endpoint, avoiding duplicate /v1 paths"""
            if base_url.endswith('/v1'):
                return f"{base_url}/chat/completions"
            else:
                return f"{base_url}/v1/chat/completions"
        
        self.endpoints = {
            LLMProvider.OPENAI: "https://api.openai.com/v1/chat/completions",
            LLMProvider.VLLM: build_endpoint(config.base_url) if config.base_url else None,
            LLMProvider.OLLAMA: build_endpoint(config.base_url) if config.base_url else "http://localhost:11434/v1/chat/completions",
            LLMProvider.CUSTOM: build_endpoint(config.base_url) if config.base_url else None,
        }
        
        # Validate configuration
        if not self.endpoints.get(config.provider):
            raise ValueError(f"Invalid provider configuration for {config.provider}")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session
    
    async def close(self):
        """Close HTTP session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for API request"""
        headers = {
            "Content-Type": "application/json",
        }
        
        if self.config.provider == LLMProvider.OPENAI and self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        elif self.config.provider == LLMProvider.VLLM:
            # vLLM typically doesn't require auth in local setups
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"
        elif self.config.provider == LLMProvider.OLLAMA:
            # Ollama typically doesn't require auth
            pass
        elif self.config.provider == LLMProvider.CUSTOM and self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
            
        return headers
    
    def _prepare_payload(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        """Prepare request payload for the API"""
        payload = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
            "stream": False,
        }
        
        # Provider-specific adjustments
        if self.config.provider == LLMProvider.VLLM:
            # vLLM supports additional parameters
            payload.update({
                "top_p": kwargs.get("top_p", 0.9),
                "frequency_penalty": kwargs.get("frequency_penalty", 0.0),
                "presence_penalty": kwargs.get("presence_penalty", 0.0),
            })
        
        return payload
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> LLMResponse:
        """
        Send chat completion request to LLM provider
        
        Args:
            messages: List of message dicts with 'role' and 'content' keys
            **kwargs: Additional parameters (max_tokens, temperature, etc.)
            
        Returns:
            LLMResponse with content and metadata
        """
        session = await self._get_session()
        
        try:
            url = self.endpoints[self.config.provider]
            headers = self._get_headers()
            payload = self._prepare_payload(messages, **kwargs)
            
            logger.info(f"Sending request to {self.config.provider} ({url})")
            logger.debug(f"Payload: {payload}")
            
            start_time = time.time()
            
            async with session.post(url, json=payload, headers=headers) as response:
                response_text = await response.text()
                request_time = time.time() - start_time
                
                if response.status != 200:
                    logger.error(f"LLM API error ({response.status}): {response_text}")
                    raise Exception(f"LLM API error: {response.status} - {response_text}")
                
                try:
                    data = json.loads(response_text)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse LLM response: {response_text}")
                    raise Exception(f"Invalid JSON response: {e}")
                
                # Extract content from response
                if "choices" not in data or not data["choices"]:
                    raise Exception("No choices in LLM response")
                
                choice = data["choices"][0]
                content = choice.get("message", {}).get("content", "")
                
                if not content:
                    raise Exception("Empty content in LLM response")
                
                # Extract usage information if available
                usage_tokens = None
                if "usage" in data:
                    usage_tokens = data["usage"].get("total_tokens")
                
                logger.info(f"LLM request completed in {request_time:.2f}s, tokens: {usage_tokens}")
                
                return LLMResponse(
                    content=content,
                    usage_tokens=usage_tokens,
                    finish_reason=choice.get("finish_reason"),
                    model=self.config.model,
                    provider=self.config.provider.value
                )
                
        except aiohttp.ClientError as e:
            logger.error(f"HTTP error in LLM request: {e}")
            raise Exception(f"Network error: {e}")
        except Exception as e:
            logger.error(f"Error in LLM request: {e}")
            raise
    
    async def get_model_context_length(self) -> Optional[int]:
        """
        Get the context length for the current model by querying the models endpoint
        
        Returns:
            Context length in tokens, or None if unavailable
        """
        try:
            # Try to get model info from models endpoint
            models_url = self.base_url.replace('/chat/completions', '/models')
            
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(models_url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Look for our specific model in the list
                        if "data" in data:
                            for model in data["data"]:
                                if model.get("id") == self.model_name:
                                    # Extract context length from various possible fields
                                    context_length = (
                                        model.get("context_length") or 
                                        model.get("max_context_length") or
                                        model.get("context_window") or
                                        model.get("max_tokens")
                                    )
                                    if context_length:
                                        logger.info(f"Retrieved context length for {self.model_name}: {context_length}")
                                        return int(context_length)
                        
                        # If model not found specifically, try to infer from model name
                        return self._infer_context_from_model_name()
                        
        except Exception as e:
            logger.debug(f"Could not retrieve model context length: {e}")
            return self._infer_context_from_model_name()
    
    def _infer_context_from_model_name(self) -> int:
        """
        Infer reasonable context length limits based on model name patterns
        
        Returns:
            Conservative context length estimate
        """
        model_lower = self.model_name.lower()
        
        # Common Ollama models with known limits
        if any(size in model_lower for size in ["3b", "7b"]):
            return 4096  # Most small models
        elif any(size in model_lower for size in ["13b", "34b"]):
            return 8192  # Medium models
        elif "llama3.2" in model_lower:
            return 128000 if "11b" in model_lower else 4096
        elif "qwen" in model_lower or "codellama" in model_lower:
            return 16384
        elif "gpt-oss" in model_lower or "gpt-4" in model_lower:
            return 128000  # Large context models
        elif "claude" in model_lower:
            return 200000  # Claude has very large context
        elif "mistral" in model_lower or "mixtral" in model_lower:
            return 32768
        else:
            # Conservative default for unknown models
            return 4096
    
    def _estimate_tokens(self, text: str) -> int:
        """
        Rough token estimation using simple heuristics
        
        Args:
            text: Text to estimate
            
        Returns:
            Estimated token count
        """
        # Rough approximation: ~4 characters per token for English text
        # This is conservative to avoid exceeding context limits
        return len(text) // 3
    
    def _chunk_transcript_intelligently(self, transcript: str, max_tokens: int, prompt_overhead: int = 1500) -> List[str]:
        """
        Split transcript into intelligent chunks that respect context limits
        
        Args:
            transcript: Full transcript to chunk
            max_tokens: Maximum tokens available per chunk
            prompt_overhead: Estimated tokens needed for prompt formatting
            
        Returns:
            List of transcript chunks
        """
        available_tokens = max_tokens - prompt_overhead
        estimated_tokens = self._estimate_tokens(transcript)
        
        # If it fits in one chunk, return as single item
        if estimated_tokens <= available_tokens:
            return [transcript]
        
        # Calculate target size per chunk
        target_chars_per_chunk = int(available_tokens * 3)  # Conservative estimate
        chunks = []
        
        # Split by speaker changes and timestamps first for natural boundaries
        speaker_segments = re.split(r'(\n[A-Z_][A-Z0-9_]*:\s*\[\d+:\d+\])', transcript)
        
        current_chunk = ""
        current_size = 0
        
        for segment in speaker_segments:
            segment_size = self._estimate_tokens(segment)
            
            # If adding this segment would exceed limit, finalize current chunk
            if current_size + segment_size > available_tokens and current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = segment
                current_size = segment_size
            else:
                current_chunk += segment
                current_size += segment_size
        
        # Add the final chunk
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        # If we still have chunks that are too large, split by sentences
        final_chunks = []
        for chunk in chunks:
            if self._estimate_tokens(chunk) <= available_tokens:
                final_chunks.append(chunk)
            else:
                # Split large chunks by sentences
                sentences = re.split(r'(?<=[.!?])\s+', chunk)
                sub_chunk = ""
                
                for sentence in sentences:
                    if self._estimate_tokens(sub_chunk + sentence) <= available_tokens:
                        sub_chunk += sentence + " "
                    else:
                        if sub_chunk.strip():
                            final_chunks.append(sub_chunk.strip())
                        sub_chunk = sentence + " "
                
                if sub_chunk.strip():
                    final_chunks.append(sub_chunk.strip())
        
        return final_chunks if final_chunks else [transcript[:target_chars_per_chunk]]
    
    async def _summarize_transcript_section(self, transcript_chunk: str, section_number: int, total_sections: int, speaker_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Generate a section summary for a transcript chunk
        
        Args:
            transcript_chunk: Portion of transcript to summarize
            section_number: Current section number (1-based)
            total_sections: Total number of sections
            speaker_data: Speaker information for this section
            
        Returns:
            Section summary data
        """
        from app.utils.summary_prompts import get_section_summary_prompt
        
        section_prompt = get_section_summary_prompt()
        
        formatted_prompt = section_prompt.format(
            transcript_chunk=transcript_chunk,
            section_number=section_number,
            total_sections=total_sections,
            speaker_data=json.dumps(speaker_data or {}, indent=2)
        )
        
        messages = [
            {
                "role": "system",
                "content": "You are an expert meeting analyst. Analyze this transcript section and provide a structured summary that will be combined with other sections."
            },
            {
                "role": "user", 
                "content": formatted_prompt
            }
        ]
        
        # Context length already handled by chunking
        response_tokens = min(2000, 4000)  # Reasonable response size for sections
        response = await self.chat_completion(messages, max_tokens=response_tokens, temperature=0.1)
        
        try:
            return json.loads(response.content)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse section summary JSON: {response.content}")
            return {
                "key_points": [f"Section {section_number}: Failed to parse structured summary"],
                "speakers_in_section": [],
                "decisions": [],
                "action_items": [],
                "topics_discussed": []
            }
    
    async def _stitch_section_summaries(self, section_summaries: List[Dict[str, Any]], full_speaker_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Combine multiple section summaries into a final comprehensive BLUF summary
        
        Args:
            section_summaries: List of section summary data
            full_speaker_data: Complete speaker information across all sections
            
        Returns:
            Final comprehensive summary
        """
        from app.utils.summary_prompts import get_final_summary_prompt
        
        final_prompt = get_final_summary_prompt()
        
        formatted_prompt = final_prompt.format(
            section_summaries=json.dumps(section_summaries, indent=2),
            total_sections=len(section_summaries),
            speaker_data=json.dumps(full_speaker_data or {}, indent=2)
        )
        
        messages = [
            {
                "role": "system",
                "content": "You are an expert meeting analyst. Synthesize multiple section summaries into a comprehensive BLUF format summary."
            },
            {
                "role": "user",
                "content": formatted_prompt
            }
        ]
        
        response_tokens = min(4000, 6000)  # Larger response for final summary
        response = await self.chat_completion(messages, max_tokens=response_tokens, temperature=0.1)
        
        try:
            return json.loads(response.content)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse final summary JSON: {response.content}")
            # Return fallback structure
            return {
                "bluf": "Multi-section summary generation completed with partial results.",
                "brief_summary": f"Summary generated from {len(section_summaries)} sections. JSON parsing failed: {str(e)}",
                "speakers": [],
                "content_sections": [],
                "action_items": [],
                "key_decisions": [],
                "follow_up_items": [],
                "metadata": {
                    "provider": self.config.provider.value,
                    "model": self.config.model,
                    "sections_processed": len(section_summaries),
                    "error": f"Final summary JSON parsing failed: {str(e)}"
                }
            }
    
    async def generate_summary(
        self,
        transcript: str,
        speaker_data: Optional[Dict[str, Any]] = None,
        prompt_template: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate structured summary from transcript
        
        Args:
            transcript: Full transcript text
            speaker_data: Optional speaker information
            prompt_template: Optional custom prompt template
            **kwargs: Additional LLM parameters
            
        Returns:
            Structured summary dict
        """
        from app.utils.summary_prompts import get_summary_prompt
        
        # Use custom prompt or default
        if prompt_template is None:
            prompt_template = get_summary_prompt()
        
        # Get model context length and handle transcript sectioning
        context_length = await self.get_model_context_length() or 4096
        transcript_chunks = self._chunk_transcript_intelligently(transcript, context_length)
        
        if len(transcript_chunks) == 1:
            # Single chunk - use original direct approach
            logger.info(f"Transcript fits in single section for model {self.model_name}")
            
            formatted_prompt = prompt_template.format(
                transcript=transcript_chunks[0],
                speaker_data=json.dumps(speaker_data or {}, indent=2)
            )
            
            messages = [
                {
                    "role": "system",
                    "content": "You are an expert meeting analyst. Analyze transcripts and generate structured summaries in the exact JSON format specified."
                },
                {
                    "role": "user",
                    "content": formatted_prompt
                }
            ]
            
            response_tokens = min(4000, context_length // 4)
            kwargs.setdefault("max_tokens", response_tokens)
            kwargs.setdefault("temperature", 0.1)
            
            response = await self.chat_completion(messages, **kwargs)
        else:
            # Multi-section approach for long transcripts
            logger.info(f"Processing transcript in {len(transcript_chunks)} sections for model {self.model_name}")
            
            section_summaries = []
            for i, chunk in enumerate(transcript_chunks, 1):
                logger.info(f"Processing section {i}/{len(transcript_chunks)}")
                section_summary = await self._summarize_transcript_section(
                    chunk, i, len(transcript_chunks), speaker_data
                )
                section_summaries.append(section_summary)
            
            # Stitch sections together into final summary
            logger.info("Stitching section summaries into final comprehensive summary")
            final_summary = await self._stitch_section_summaries(section_summaries, speaker_data)
            
            # Add processing metadata
            final_summary["metadata"]["sections_processed"] = len(transcript_chunks)
            final_summary["metadata"]["transcript_length"] = len(transcript)
            final_summary["metadata"]["processing_method"] = "multi-section"
            
            # Return early for multi-section processing
            return final_summary
        
        # Parse the JSON response
        try:
            # Extract JSON from markdown code blocks if present
            content = response.content.strip()
            
            # Handle ```json format
            if content.startswith('```json') and content.endswith('```'):
                content = content[7:-3].strip()  # Remove ```json and ```
            # Handle generic ``` format
            elif content.startswith('```') and content.endswith('```'):
                content = content[3:-3].strip()  # Remove ``` and ```
            # Handle multiline code blocks
            if content.startswith('```'):
                lines = content.split('\n')
                if len(lines) > 2:
                    # Check if first line has language specifier
                    first_line = lines[0].strip()
                    if first_line in ['```', '```json', '```JSON']:
                        # Remove first and last lines
                        content = '\n'.join(lines[1:-1]).strip()
                    else:
                        # First line might contain both ``` and content
                        if first_line.startswith('```'):
                            # Remove ``` from first line and last line
                            first_content = first_line[3:]
                            middle_lines = lines[1:-1] if len(lines) > 2 else []
                            last_line = lines[-1].strip()
                            if last_line == '```':
                                content = '\n'.join([first_content] + middle_lines).strip()
                            else:
                                content = '\n'.join([first_content] + middle_lines + [last_line.replace('```', '')]).strip()
            
            summary_data = json.loads(content)
            
            # Validate required fields
            required_fields = ["bluf", "brief_summary", "speakers", "content_sections", "action_items", "key_decisions", "follow_up_items"]
            for field in required_fields:
                if field not in summary_data:
                    logger.warning(f"Missing required field in summary: {field}")
                    summary_data[field] = [] if field in ["speakers", "content_sections", "action_items", "key_decisions", "follow_up_items"] else ""
            
            # Add metadata
            summary_data["metadata"] = {
                "provider": self.config.provider.value,
                "model": self.config.model,
                "usage_tokens": response.usage_tokens,
                "transcript_length": len(transcript),
                "processing_time_ms": None  # Will be set by caller
            }
            
            return summary_data
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse summary JSON: {response.content}")
            # Return fallback structure
            return {
                "bluf": "Failed to generate structured summary.",
                "brief_summary": f"Summary generation failed due to JSON parsing error: {str(e)}",
                "speakers": [],
                "content_sections": [],
                "action_items": [],
                "key_decisions": [],
                "follow_up_items": [],
                "metadata": {
                    "provider": self.config.provider.value,
                    "model": self.config.model,
                    "usage_tokens": None,
                    "transcript_length": len(transcript),
                    "processing_time_ms": None,
                    "error": f"JSON parsing failed: {str(e)}"
                }
            }
    
    async def identify_speakers(
        self,
        transcript: str,
        speaker_segments: List[Dict[str, Any]],
        known_speakers: List[Dict[str, Any]],
        **kwargs
    ) -> Dict[str, Any]:
        """
        Use LLM to identify speakers in transcript
        
        Args:
            transcript: Full transcript text
            speaker_segments: Segments with speaker labels
            known_speakers: List of known speakers with names and descriptions
            **kwargs: Additional LLM parameters
            
        Returns:
            Speaker identification results
        """
        from app.utils.summary_prompts import get_speaker_identification_prompt
        
        prompt = get_speaker_identification_prompt()
        
        # Get context length and truncate transcript if needed
        context_length = await self.get_model_context_length() or 4096
        transcript_processed, was_truncated = self._truncate_transcript_intelligently(
            transcript, context_length, prompt_overhead=2000  # More overhead for speaker data
        )
        
        if was_truncated:
            logger.warning(f"Transcript truncated for speaker identification with {self.model_name}")
        
        # Format the prompt
        formatted_prompt = prompt.format(
            transcript=transcript_processed,
            speaker_segments=json.dumps(speaker_segments, indent=2),
            known_speakers=json.dumps(known_speakers, indent=2)
        )
        
        messages = [
            {
                "role": "system",
                "content": "You are an expert at identifying speakers in transcripts based on content analysis and context clues."
            },
            {
                "role": "user",
                "content": formatted_prompt
            }
        ]
        
        # Get context length for this request
        context_length = await self.get_model_context_length() or 4096
        response_tokens = min(2000, context_length // 4)  # Smaller response for speaker identification
        kwargs.setdefault("max_tokens", response_tokens)
        kwargs.setdefault("temperature", 0.2)
        
        response = await self.chat_completion(messages, **kwargs)
        
        # Parse the JSON response
        try:
            # Extract JSON from markdown code blocks if present
            content = response.content.strip()
            
            # Handle ```json format
            if content.startswith('```json') and content.endswith('```'):
                content = content[7:-3].strip()  # Remove ```json and ```
            # Handle generic ``` format
            elif content.startswith('```') and content.endswith('```'):
                content = content[3:-3].strip()  # Remove ``` and ```
            # Handle multiline code blocks
            if content.startswith('```'):
                lines = content.split('\n')
                if len(lines) > 2:
                    # Check if first line has language specifier
                    first_line = lines[0].strip()
                    if first_line in ['```', '```json', '```JSON']:
                        # Remove first and last lines
                        content = '\n'.join(lines[1:-1]).strip()
                    else:
                        # First line might contain both ``` and content
                        if first_line.startswith('```'):
                            # Remove ``` from first line and last line
                            first_content = first_line[3:]
                            middle_lines = lines[1:-1] if len(lines) > 2 else []
                            last_line = lines[-1].strip()
                            if last_line == '```':
                                content = '\n'.join([first_content] + middle_lines).strip()
                            else:
                                content = '\n'.join([first_content] + middle_lines + [last_line.replace('```', '')]).strip()
            
            identification_data = json.loads(content)
            
            # Add metadata
            identification_data["metadata"] = {
                "provider": self.config.provider.value,
                "model": self.config.model,
                "usage_tokens": response.usage_tokens
            }
            
            return identification_data
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse speaker identification JSON: {response.content}")
            return {
                "speaker_predictions": [],
                "confidence_level": "low",
                "reasoning": f"Failed to parse response: {str(e)}",
                "metadata": {
                    "provider": self.config.provider.value,
                    "model": self.config.model,
                    "usage_tokens": None,
                    "error": f"JSON parsing failed: {str(e)}"
                }
            }
    
    @staticmethod
    def create_from_settings() -> 'LLMService':
        """Create LLMService from application settings"""
        provider = LLMProvider(settings.LLM_PROVIDER)
        
        # Provider-specific configuration mapping
        if provider == LLMProvider.VLLM:
            model = settings.VLLM_MODEL_NAME
            api_key = settings.VLLM_API_KEY
            base_url = settings.VLLM_BASE_URL
        elif provider == LLMProvider.OPENAI:
            model = settings.OPENAI_MODEL_NAME
            api_key = settings.OPENAI_API_KEY
            base_url = settings.OPENAI_BASE_URL
        elif provider == LLMProvider.OLLAMA:
            model = settings.OLLAMA_MODEL_NAME
            api_key = None
            base_url = settings.OLLAMA_BASE_URL
        elif provider == LLMProvider.CLAUDE:
            model = settings.ANTHROPIC_MODEL_NAME
            api_key = settings.ANTHROPIC_API_KEY
            base_url = settings.ANTHROPIC_BASE_URL
        elif provider == LLMProvider.CUSTOM:
            model = settings.OPENROUTER_MODEL_NAME
            api_key = settings.OPENROUTER_API_KEY
            base_url = settings.OPENROUTER_BASE_URL
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")
        
        config = LLMConfig(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            max_tokens=131000,  # Use full model capacity as requested
            temperature=0.3,
            timeout=300  # 5 minutes timeout for large context processing
        )
        
        return LLMService(config)
    
    @staticmethod
    def get_supported_providers() -> List[str]:
        """Get list of supported LLM providers"""
        return [provider.value for provider in LLMProvider]
    
    async def health_check(self) -> bool:
        """
        Quick health check without sending full request to LLM
        
        Returns:
            True if LLM is available, False otherwise
        """
        try:
            session = await self._get_session()
            url = self.endpoints[self.config.provider]
            headers = self._get_headers()
            
            # Simple HEAD request or minimal payload to test connectivity
            test_payload = {
                "model": self.config.model,
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 1,
                "temperature": 0.0
            }
            
            async with session.post(url, json=test_payload, headers=headers) as response:
                # Accept 200 or even some error codes that indicate the service is up
                return response.status in [200, 400, 422]  # 400/422 might be validation errors but service is up
                
        except Exception as e:
            logger.debug(f"Health check failed for {self.config.provider}: {e}")
            return False

    async def validate_connection(self) -> Tuple[bool, str]:
        """
        Validate connection to LLM provider
        
        Returns:
            Tuple of (success, message)
        """
        try:
            test_messages = [
                {"role": "user", "content": "Respond with exactly: 'Connection test successful'"}
            ]
            
            response = await self.chat_completion(
                test_messages,
                max_tokens=50,
                temperature=0.0
            )
            
            if "connection test successful" in response.content.lower():
                return True, f"Successfully connected to {self.config.provider} ({self.config.model})"
            else:
                return False, f"Unexpected response: {response.content}"
                
        except Exception as e:
            return False, f"Connection failed: {str(e)}"


# Utility functions for creating LLM services with fallback
async def create_llm_service_with_fallback() -> LLMService:
    """
    Create LLM service with fallback to other providers if primary fails
    """
    primary_service = LLMService.create_from_settings()
    
    # Test primary provider
    try:
        is_valid, message = await primary_service.validate_connection()
        if is_valid:
            logger.info(f"Primary LLM provider connected: {message}")
            return primary_service
        else:
            logger.warning(f"Primary LLM provider failed: {message}")
    except Exception as e:
        logger.warning(f"Primary LLM provider error: {e}")
    
    # Try fallback providers
    fallback_providers = getattr(settings, 'LLM_FALLBACK_PROVIDERS', ['openai'])
    
    for provider_name in fallback_providers:
        if provider_name == settings.LLM_PROVIDER:
            continue  # Skip primary provider
            
        try:
            provider = LLMProvider(provider_name)
            fallback_config = LLMConfig(
                provider=provider,
                model=settings.LLM_MODEL,  # May need provider-specific defaults
                api_key=getattr(settings, f'{provider_name.upper()}_API_KEY', None),
                base_url=getattr(settings, f'{provider_name.upper()}_BASE_URL', None),
            )
            
            fallback_service = LLMService(fallback_config)
            is_valid, message = await fallback_service.validate_connection()
            
            if is_valid:
                logger.info(f"Fallback LLM provider connected: {message}")
                await primary_service.close()
                return fallback_service
            else:
                logger.warning(f"Fallback provider {provider_name} failed: {message}")
                await fallback_service.close()
                
        except Exception as e:
            logger.warning(f"Fallback provider {provider_name} error: {e}")
    
    # If all providers fail, return primary service anyway (will raise errors on use)
    logger.error("All LLM providers failed, returning primary service")
    return primary_service


# Context manager for proper cleanup
class LLMServiceContext:
    """Context manager for LLM service with proper cleanup"""
    
    def __init__(self, service: Optional[LLMService] = None):
        self.service = service
        self._created_service = service is None
    
    async def __aenter__(self) -> LLMService:
        if self.service is None:
            self.service = LLMService.create_from_settings()
        return self.service
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.service and self._created_service:
            await self.service.close()


# Utility function for quick LLM availability check
async def is_llm_available() -> bool:
    """
    Quick check to see if any LLM provider is available
    
    Returns:
        True if at least one LLM provider is available, False otherwise
    """
    try:
        async with LLMServiceContext() as llm_service:
            return await llm_service.health_check()
    except Exception as e:
        logger.debug(f"LLM availability check failed: {e}")
        return False