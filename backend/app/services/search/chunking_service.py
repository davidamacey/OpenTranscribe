"""Transcript chunking service for search indexing."""

import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


def chunk_transcript_by_speaker_turns(
    segments: list[dict[str, Any]],
    file_uuid: str,
    file_id: int,
    user_id: int,
    title: str,
    speakers: list[str],
    tags: list[str],
    upload_time: str,
    language: str = "en",
    content_type: str = "",
    duration: float | None = None,
    file_size: int | None = None,
    collection_ids: list[int] | None = None,
    target_words: int | None = None,
    overlap_words: int | None = None,
) -> list[dict[str, Any]]:
    """
    Chunk transcript segments into search-optimized documents.

    Strategy:
    1. Group consecutive segments by same speaker into speaker turns
    2. If a turn exceeds target_words, split with sliding window overlap
    3. If a turn is very short, merge with adjacent turns (same speaker)
    4. Each chunk retains: start_time, end_time, speaker, file metadata

    Args:
        segments: List of transcript segments with keys: start, end, text, speaker
        file_uuid: UUID of the media file
        file_id: Integer ID of the media file
        user_id: Integer ID of the file owner
        title: File title
        speakers: All speaker names in the file
        tags: Tags associated with the file
        upload_time: ISO timestamp of upload
        language: Language code
        target_words: Target words per chunk (default from settings)
        overlap_words: Overlap words between chunks (default from settings)

    Returns:
        List of chunk dicts ready for indexing.
    """
    if target_words is None:
        target_words = settings.SEARCH_CHUNK_TARGET_WORDS
    if overlap_words is None:
        overlap_words = settings.SEARCH_CHUNK_OVERLAP_WORDS

    # Step 1: Group consecutive segments by same speaker into turns
    turns = _group_segments_into_speaker_turns(segments)

    # Step 2: Split long turns with sliding window, merge short turns
    chunks: list[dict[str, Any]] = []
    chunk_index = 0

    for turn in turns:
        turn_text = turn["text"]
        turn_words = turn_text.split()
        word_count = len(turn_words)

        if word_count < 20 and chunks:
            # Very short turn - try to merge with last chunk if same speaker
            last_chunk = chunks[-1]
            if last_chunk["speaker"] == turn["speaker"]:
                last_chunk["content"] += " " + turn_text
                last_chunk["end_time"] = turn["end"]
                continue

        if word_count <= target_words:
            # Turn fits in one chunk
            chunks.append(
                _make_chunk(
                    content=turn_text,
                    speaker=turn["speaker"],
                    start_time=turn["start"],
                    end_time=turn["end"],
                    chunk_index=chunk_index,
                    file_uuid=file_uuid,
                    file_id=file_id,
                    user_id=user_id,
                    title=title,
                    speakers=speakers,
                    tags=tags,
                    upload_time=upload_time,
                    language=language,
                    content_type=content_type,
                    duration=duration,
                    file_size=file_size,
                    collection_ids=collection_ids,
                )
            )
            chunk_index += 1
        else:
            # Long monologue - split with sliding window
            sub_chunks = _split_long_turn(
                turn,
                target_words,
                overlap_words,
                chunk_index,
                file_uuid,
                file_id,
                user_id,
                title,
                speakers,
                tags,
                upload_time,
                language,
                content_type=content_type,
                duration=duration,
                file_size=file_size,
                collection_ids=collection_ids,
            )
            chunks.extend(sub_chunks)
            chunk_index += len(sub_chunks)

    logger.info(
        f"Chunked transcript for file {file_uuid}: "
        f"{len(segments)} segments -> {len(turns)} turns -> {len(chunks)} chunks"
    )
    return chunks


def _group_segments_into_speaker_turns(
    segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Group consecutive segments by the same speaker into turns."""
    if not segments:
        return []

    turns = []
    current_turn = {
        "speaker": segments[0].get("speaker", "Unknown"),
        "text": segments[0].get("text", "").strip(),
        "start": segments[0].get("start", 0.0),
        "end": segments[0].get("end", 0.0),
    }

    for seg in segments[1:]:
        seg_speaker = seg.get("speaker", "Unknown")
        seg_text = seg.get("text", "").strip()

        if seg_speaker == current_turn["speaker"]:
            # Same speaker - extend current turn
            current_turn["text"] += " " + seg_text
            current_turn["end"] = seg.get("end", current_turn["end"])
        else:
            # New speaker - save current turn and start new one
            if current_turn["text"].strip():
                turns.append(current_turn)
            current_turn = {
                "speaker": seg_speaker,
                "text": seg_text,
                "start": seg.get("start", 0.0),
                "end": seg.get("end", 0.0),
            }

    # Don't forget the last turn
    if current_turn["text"].strip():
        turns.append(current_turn)

    return turns


def _split_long_turn(
    turn: dict[str, Any],
    target_words: int,
    overlap_words: int,
    start_chunk_index: int,
    file_uuid: str,
    file_id: int,
    user_id: int,
    title: str,
    speakers: list[str],
    tags: list[str],
    upload_time: str,
    language: str,
    content_type: str = "",
    duration: float | None = None,
    file_size: int | None = None,
    collection_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    """Split a long speaker turn into overlapping chunks."""
    words = turn["text"].split()
    total_words = len(words)
    chunks = []
    pos = 0
    chunk_index = start_chunk_index

    # Guard against infinite loop when overlap >= target
    overlap_words = min(overlap_words, target_words - 1)

    # Estimate time per word for timestamp interpolation
    turn_duration: float = turn["end"] - turn["start"]
    time_per_word = turn_duration / max(total_words, 1)

    while pos < total_words:
        end_pos = min(pos + target_words, total_words)
        chunk_text = " ".join(words[pos:end_pos])

        # Interpolate timestamps
        chunk_start = turn["start"] + (pos * time_per_word)
        chunk_end = turn["start"] + (end_pos * time_per_word)

        chunks.append(
            _make_chunk(
                content=chunk_text,
                speaker=turn["speaker"],
                start_time=round(chunk_start, 2),
                end_time=round(chunk_end, 2),
                chunk_index=chunk_index,
                file_uuid=file_uuid,
                file_id=file_id,
                user_id=user_id,
                title=title,
                speakers=speakers,
                tags=tags,
                upload_time=upload_time,
                language=language,
                content_type=content_type,
                duration=duration,
                file_size=file_size,
                collection_ids=collection_ids,
            )
        )
        chunk_index += 1

        # Advance with overlap
        pos = end_pos if end_pos >= total_words else end_pos - overlap_words

    return chunks


def _make_chunk(
    content: str,
    speaker: str,
    start_time: float,
    end_time: float,
    chunk_index: int,
    file_uuid: str,
    file_id: int,
    user_id: int,
    title: str,
    speakers: list[str],
    tags: list[str],
    upload_time: str,
    language: str,
    content_type: str = "",
    duration: float | None = None,
    file_size: int | None = None,
    collection_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Create a chunk document dict."""
    return {
        "file_id": file_id,
        "file_uuid": file_uuid,
        "user_id": user_id,
        "chunk_index": chunk_index,
        "content": content,
        "title": title,
        "speaker": speaker,
        "speakers": speakers,
        "tags": tags,
        "upload_time": upload_time,
        "language": language,
        "start_time": round(start_time, 2),
        "end_time": round(end_time, 2),
        "content_type": content_type,
        "duration": duration,
        "file_size": file_size,
        "collection_ids": collection_ids or [],
    }
