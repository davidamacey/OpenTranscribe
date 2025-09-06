#!/usr/bin/env python3
"""
Test script to debug speaker identification issues
"""
import asyncio
import json
import sys

# Add the backend directory to Python path
sys.path.insert(0, '/mnt/nvm/repos/transcribe-app/backend')

async def test_speaker_identification():
    from app.services.llm_service import LLMServiceContext

    # Test data
    test_transcript = """
SPEAKER_01: [00:00] Hello everyone, welcome to today's meeting.
SPEAKER_02: [00:15] Thanks for having me. I'm excited to discuss the new project.
SPEAKER_01: [00:30] Great! Let's start with the technical requirements.
"""

    test_speaker_segments = [
        {"speaker_label": "SPEAKER_01", "segments": 2},
        {"speaker_label": "SPEAKER_02", "segments": 1}
    ]

    test_known_speakers = []

    try:
        async with LLMServiceContext() as llm_service:
            print("LLM Service initialized successfully")
            print(f"Provider: {llm_service.config.provider}")
            print(f"Model: {llm_service.config.model}")

            # Test the identify_speakers method
            print("\nCalling identify_speakers...")
            result = await llm_service.identify_speakers(
                transcript=test_transcript,
                speaker_segments=test_speaker_segments,
                known_speakers=test_known_speakers
            )

            print("Success! Result:")
            print(json.dumps(result, indent=2))

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_speaker_identification())
