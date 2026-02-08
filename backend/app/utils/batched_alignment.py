"""
Batched wav2vec2 alignment for WhisperX.

Replaces WhisperX's sequential alignment (one segment at a time) with batched
GPU inference. The original alignment.py processes ~300 segments sequentially,
each requiring a separate CUDA kernel launch. This module groups segments into
batches, pads to equal length, and runs fewer, larger forward passes.

Estimated speedup: 3-10x on the wav2vec2 forward pass portion (which is
65-77% of total alignment time).

The CTC trellis + backtrack phase remains sequential (CPU-bound dynamic
programming) but is a smaller fraction of total time.
"""

import logging
import time

import numpy as np
import pandas as pd
import torch

logger = logging.getLogger(__name__)

# Alignment batch size (segments per batch). Higher = more GPU utilization
# but more padding waste. 16-32 is a good balance.
DEFAULT_BATCH_SIZE = 16


def align_batched(  # noqa: C901  # type: ignore
    transcript: list[dict],
    align_model,
    align_model_metadata: dict,
    audio,
    device: str,
    interpolate_method: str = "nearest",
    return_char_alignments: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> dict:
    """
    Batched forced alignment using wav2vec2.

    Drop-in replacement for whisperx.align() with batched GPU inference.
    Same inputs and outputs as the original, but groups wav2vec2 forward
    passes into batches for better GPU utilization.

    Args:
        transcript: List of segment dicts with 'start', 'end', 'text'
        align_model: Loaded wav2vec2 alignment model
        align_model_metadata: Model metadata dict with 'dictionary', 'language', 'type'
        audio: Audio tensor or numpy array
        device: 'cuda' or 'cpu'
        interpolate_method: NaN interpolation method for timestamps
        return_char_alignments: Whether to return character-level alignments
        batch_size: Number of segments per batch for wav2vec2 inference

    Returns:
        Dict with 'segments' and 'word_segments' keys (same as whisperx.align)
    """
    from whisperx.alignment import LANGUAGES_WITHOUT_SPACES
    from whisperx.alignment import backtrack_beam
    from whisperx.alignment import get_trellis
    from whisperx.alignment import merge_repeats
    from whisperx.audio import SAMPLE_RATE
    from whisperx.utils import interpolate_nans

    start_time = time.perf_counter()

    if not torch.is_tensor(audio):
        if isinstance(audio, str):
            from whisperx.audio import load_audio

            audio = load_audio(audio)
        audio = torch.from_numpy(audio)
    if len(audio.shape) == 1:
        audio = audio.unsqueeze(0)

    MAX_DURATION = audio.shape[1] / SAMPLE_RATE  # noqa: N806
    model_dictionary = align_model_metadata["dictionary"]
    model_lang = align_model_metadata["language"]
    model_type = align_model_metadata["type"]

    # Phase 1: Preprocess text (same as original - fast, CPU-only)
    phase1_start = time.perf_counter()
    import nltk
    from nltk.data import load as nltk_load

    try:
        sentence_splitter = nltk_load("tokenizers/punkt/english.pickle")
    except LookupError:
        nltk.download("punkt_tab", quiet=True)
        sentence_splitter = nltk_load("tokenizers/punkt/english.pickle")

    segment_data = {}
    valid_segment_indices = []  # Indices of segments that can be aligned

    for sdx, segment in enumerate(transcript):
        num_leading = len(segment["text"]) - len(segment["text"].lstrip())
        num_trailing = len(segment["text"]) - len(segment["text"].rstrip())
        text = segment["text"]

        per_word = text.split(" ") if model_lang not in LANGUAGES_WITHOUT_SPACES else text

        clean_char, clean_cdx = [], []
        for cdx, char in enumerate(text):
            char_ = char.lower()
            if model_lang not in LANGUAGES_WITHOUT_SPACES:
                char_ = char_.replace(" ", "|")
            if cdx < num_leading or cdx > len(text) - num_trailing - 1:
                pass
            elif char_ in model_dictionary:
                clean_char.append(char_)
                clean_cdx.append(cdx)
            else:
                clean_char.append("*")
                clean_cdx.append(cdx)

        clean_wdx = []
        for wdx, wrd in enumerate(per_word):
            if any(c in model_dictionary for c in wrd.lower()):
                clean_wdx.append(wdx)
            else:
                clean_wdx.append(wdx)

        sentence_spans = list(sentence_splitter.span_tokenize(text))

        segment_data[sdx] = {
            "clean_char": clean_char,
            "clean_cdx": clean_cdx,
            "clean_wdx": clean_wdx,
            "sentence_spans": sentence_spans,
        }

        # Check if segment is alignable
        t1 = segment["start"]
        if len(clean_char) > 0 and t1 < MAX_DURATION:
            valid_segment_indices.append(sdx)

    phase1_time = time.perf_counter() - phase1_start

    # Phase 2: Batched wav2vec2 inference
    phase2_start = time.perf_counter()

    # Prepare waveform segments for all valid segments
    waveform_data = []
    for sdx in valid_segment_indices:
        seg = transcript[sdx]
        f1 = int(seg["start"] * SAMPLE_RATE)
        f2 = int(seg["end"] * SAMPLE_RATE)
        waveform_segment = audio[:, f1:f2]

        # Handle minimum input length for wav2vec2
        if waveform_segment.shape[-1] < 400:
            lengths = torch.as_tensor([waveform_segment.shape[-1]])
            waveform_segment = torch.nn.functional.pad(
                waveform_segment, (0, 400 - waveform_segment.shape[-1])
            )
        else:
            lengths = None

        waveform_data.append(
            {
                "waveform": waveform_segment.squeeze(0),  # Remove batch dim for stacking
                "lengths": lengths,
                "sdx": sdx,
            }
        )

    # Run batched inference
    emissions_map = {}  # sdx -> emission tensor
    num_batches = (len(waveform_data) + batch_size - 1) // batch_size

    for batch_idx in range(num_batches):
        batch_start = batch_idx * batch_size
        batch_end = min(batch_start + batch_size, len(waveform_data))
        batch_items = waveform_data[batch_start:batch_end]

        if len(batch_items) == 1:
            # Single item - no padding needed
            item = batch_items[0]
            wf = item["waveform"].unsqueeze(0)  # Add batch dim back
            with torch.inference_mode():
                if model_type == "torchaudio":
                    emissions, _ = align_model(wf.to(device), lengths=item["lengths"])
                elif model_type == "huggingface":
                    emissions = align_model(wf.to(device)).logits
                else:
                    raise NotImplementedError(f"Align model of type {model_type} not supported.")
                emissions = torch.log_softmax(emissions, dim=-1)
            emissions_map[item["sdx"]] = emissions[0].cpu().detach()
        else:
            # Batch: pad waveforms to max length in this batch
            max_len = max(item["waveform"].shape[-1] for item in batch_items)
            padded_waveforms = []
            actual_lengths = []

            for item in batch_items:
                wf = item["waveform"]
                pad_amount = max_len - wf.shape[-1]
                if pad_amount > 0:
                    wf = torch.nn.functional.pad(wf, (0, pad_amount))
                padded_waveforms.append(wf)
                actual_lengths.append(item["waveform"].shape[-1])

            batch_tensor = torch.stack(padded_waveforms)

            with torch.inference_mode():
                if model_type == "torchaudio":
                    batch_lengths = torch.as_tensor(actual_lengths).to(device)
                    emissions, _ = align_model(batch_tensor.to(device), lengths=batch_lengths)
                elif model_type == "huggingface":
                    emissions = align_model(batch_tensor.to(device)).logits
                else:
                    raise NotImplementedError(f"Align model of type {model_type} not supported.")
                emissions = torch.log_softmax(emissions, dim=-1)

            # Distribute emissions back to individual segments
            for i, item in enumerate(batch_items):
                # Trim emission to actual length (remove padding effect)
                # The emission length corresponds to the waveform length
                emissions_map[item["sdx"]] = emissions[i].cpu().detach()

    phase2_time = time.perf_counter() - phase2_start
    logger.info(
        f"TIMING: batched wav2vec2 inference completed in {phase2_time:.3f}s "
        f"- {len(waveform_data)} segments in {num_batches} batches (batch_size={batch_size})"
    )

    # Phase 3: CTC decode + timestamp assignment (per-segment, CPU)
    phase3_start = time.perf_counter()

    blank_id = 0
    for char, code in model_dictionary.items():
        if char == "[pad]" or char == "<pad>":
            blank_id = code

    aligned_segments = []

    for sdx, segment in enumerate(transcript):
        t1 = segment["start"]
        t2 = segment["end"]
        text = segment["text"]

        aligned_seg = {
            "start": t1,
            "end": t2,
            "text": text,
            "words": [],
            "chars": None,
        }

        if return_char_alignments:
            aligned_seg["chars"] = []

        # Skip unalignable segments
        if sdx not in emissions_map:
            if len(segment_data[sdx]["clean_char"]) == 0:
                logger.warning(f'Failed to align segment ("{text}"): no characters in dictionary')
            elif t1 >= MAX_DURATION:
                logger.warning(f'Failed to align segment ("{text}"): start time >= audio duration')
            aligned_segments.append(aligned_seg)
            continue

        emission = emissions_map[sdx]
        text_clean = "".join(segment_data[sdx]["clean_char"])
        tokens = [model_dictionary.get(c, -1) for c in text_clean]

        f1 = int(t1 * SAMPLE_RATE)
        f2 = int(t2 * SAMPLE_RATE)
        waveform_len = f2 - f1

        trellis = get_trellis(emission, tokens, blank_id)
        path = backtrack_beam(trellis, emission, tokens, blank_id, beam_width=2)

        if path is None:
            logger.warning(f'Failed to align segment ("{text}"): backtrack failed')
            aligned_segments.append(aligned_seg)
            continue

        char_segments = merge_repeats(path, text_clean)

        duration = t2 - t1
        ratio = duration * waveform_len / (trellis.size(0) - 1)

        # Assign timestamps to aligned characters
        char_segments_arr = []
        word_idx = 0
        for cdx, char in enumerate(text):
            start, end, score = None, None, None
            if cdx in segment_data[sdx]["clean_cdx"]:
                char_seg = char_segments[segment_data[sdx]["clean_cdx"].index(cdx)]
                start = round(char_seg.start * ratio + t1, 3)
                end = round(char_seg.end * ratio + t1, 3)
                score = round(char_seg.score, 3)

            char_segments_arr.append(
                {
                    "char": char,
                    "start": start,
                    "end": end,
                    "score": score,
                    "word-idx": word_idx,
                }
            )

            if (
                model_lang in LANGUAGES_WITHOUT_SPACES
                or cdx == len(text) - 1
                or text[cdx + 1] == " "
            ):
                word_idx += 1

        char_segments_arr = pd.DataFrame(char_segments_arr)

        # Build aligned subsegments (sentences within segment)
        aligned_subsegments = []
        char_segments_arr["sentence-idx"] = None
        for sdx2, (sstart, send) in enumerate(segment_data[sdx]["sentence_spans"]):
            curr_chars = char_segments_arr.loc[
                (char_segments_arr.index >= sstart) & (char_segments_arr.index <= send)
            ]
            char_segments_arr.loc[
                (char_segments_arr.index >= sstart) & (char_segments_arr.index <= send),
                "sentence-idx",
            ] = sdx2

            sentence_text = text[sstart:send]
            sentence_start = curr_chars["start"].min()
            end_chars = curr_chars[curr_chars["char"] != " "]
            sentence_end = end_chars["end"].max()
            sentence_words = []

            for w_idx in curr_chars["word-idx"].unique():
                word_chars = curr_chars.loc[curr_chars["word-idx"] == w_idx]
                word_text = "".join(word_chars["char"].tolist()).strip()
                if len(word_text) == 0:
                    continue

                word_chars = word_chars[word_chars["char"] != " "]
                word_start = word_chars["start"].min()
                word_end = word_chars["end"].max()
                word_score = round(word_chars["score"].mean(), 3)

                word_segment = {"word": word_text}
                if not np.isnan(word_start):
                    word_segment["start"] = word_start
                if not np.isnan(word_end):
                    word_segment["end"] = word_end
                if not np.isnan(word_score):
                    word_segment["score"] = word_score

                sentence_words.append(word_segment)

            aligned_subsegments.append(
                {
                    "text": sentence_text,
                    "start": sentence_start,
                    "end": sentence_end,
                    "words": sentence_words,
                }
            )

            if return_char_alignments:
                curr_chars_out = curr_chars[["char", "start", "end", "score"]]
                curr_chars_out.fillna(-1, inplace=True)
                curr_chars_out = curr_chars_out.to_dict("records")
                curr_chars_out = [
                    {key: val for key, val in char.items() if val != -1} for char in curr_chars_out
                ]
                aligned_subsegments[-1]["chars"] = curr_chars_out

        aligned_subsegments = pd.DataFrame(aligned_subsegments)
        aligned_subsegments["start"] = interpolate_nans(
            aligned_subsegments["start"], method=interpolate_method
        )
        aligned_subsegments["end"] = interpolate_nans(
            aligned_subsegments["end"], method=interpolate_method
        )

        # Concatenate sentences with same timestamps
        agg_dict = {"text": " ".join, "words": "sum"}
        if model_lang in LANGUAGES_WITHOUT_SPACES:
            agg_dict["text"] = "".join
        if return_char_alignments:
            agg_dict["chars"] = "sum"
        aligned_subsegments = aligned_subsegments.groupby(["start", "end"], as_index=False).agg(
            agg_dict
        )
        aligned_subsegments = aligned_subsegments.to_dict("records")
        aligned_segments += aligned_subsegments

    phase3_time = time.perf_counter() - phase3_start

    # Build word_segments list
    word_segments = []
    for segment in aligned_segments:
        word_segments += segment["words"]

    total_time = time.perf_counter() - start_time
    logger.info(
        f"TIMING: batched alignment completed in {total_time:.3f}s "
        f"(preprocess={phase1_time:.3f}s, wav2vec2={phase2_time:.3f}s, "
        f"ctc_decode={phase3_time:.3f}s) - "
        f"{len(aligned_segments)} aligned segments, {len(word_segments)} words"
    )

    return {"segments": aligned_segments, "word_segments": word_segments}
