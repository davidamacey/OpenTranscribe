# Search Architecture

This document explains how OpenTranscribe's search system works, including how results are ranked, what signals contribute to relevance, and the technical architecture behind it.

## Overview

OpenTranscribe uses **hybrid search** — a combination of keyword matching and semantic (meaning-based) similarity — powered by OpenSearch. When you search, two independent methods run simultaneously, and their results are merged into a single ranked list.

## How Search Results Are Ranked

### Two Search Methods

**1. Keyword Search (BM25)**

Traditional full-text search that looks for exact word matches. It scores based on:
- **Term frequency** — how often the search term appears in a segment
- **Inverse document frequency** — rarer words score higher (matching "diarization" is worth more than matching "the")
- **Field length normalization** — a match in a short title scores higher than the same match buried in a long transcript

**2. Semantic Search (Neural/Vector)**

Meaning-based search using a sentence-transformer model (`all-MiniLM-L6-v2` by default). The model converts both the query and transcript chunks into 384-dimensional vectors, then finds chunks whose *meaning* is similar to the query — even without shared keywords.

For example, searching "compensation discussion" can match a segment about "salary negotiations" even though those exact words don't appear.

### Combining Results: Reciprocal Rank Fusion (RRF)

The two search methods each produce their own ranked list. These are combined using **Reciprocal Rank Fusion (RRF)**, a technique that merges rankings without needing to normalize different scoring systems.

The formula for each document:

```
RRF_score = 1/(k + rank_in_keyword) + 1/(k + rank_in_semantic)
```

Where `k` is a constant (default: 40) that controls how much weight goes to top-ranked results.

**What this means in practice:**
- A file ranked #1 in keyword search and #5 in semantic search scores higher than one ranked #3 in both
- Documents that appear in both lists get a natural boost
- Neither method can completely dominate the other

### Why More Keyword Matches Doesn't Always Mean Higher Rank

Several factors explain why a file with fewer keyword matches might rank higher:

1. **RRF uses rank position, not match count** — What matters is how highly the best-matching segment ranked, not how many segments matched
2. **Best segment wins** — A file's rank is determined by its single highest-scoring segment, not the total number of matches
3. **Semantic signal matters** — Strong meaning-based similarity contributes to the combined score even with fewer keyword hits
4. **Field boosting** — A match in the transcript content (3x boost) or speaker name (3x boost) outweighs matches in lower-weighted fields
5. **Dual-match bonus** — Files with both keyword AND semantic matches get a +5% relevance display bonus

### Field Boosting

Not all fields are weighted equally. When searching:

| Field | Boost | Description |
|---|---|---|
| Transcript content | 3x | The actual spoken words (stemmed for English) |
| Transcript content (exact) | 2x | Exact phrase matching without stemming |
| File title | 2x | The filename or title |
| Speaker name | 3x | Speaker names (excluded when filtering by speaker) |

## How Transcripts Are Indexed

### Chunking Strategy

Transcripts are broken into searchable chunks using a speaker-turn-based strategy:

1. **Group by speaker turn** — Consecutive segments from the same speaker are merged into a single turn
2. **Split long turns** — Turns exceeding ~200 words are split with a 40-word overlap between chunks to preserve context
3. **Merge short turns** — Very short turns (< 20 words) from the same speaker are merged with the previous chunk
4. **One chunk = one OpenSearch document** — Each chunk is indexed separately with the file's metadata

**Typical results:**
- 30-minute meeting: ~10-15 chunks
- Long monologue/lecture: ~15-50 chunks
- Short conversational exchanges: ~5-10 chunks

### What's Stored Per Chunk

Each chunk contains:
- **Content** — The transcript text for that segment
- **Speaker** — The primary speaker of the chunk
- **Timestamps** — Start and end times for video navigation
- **File metadata** — Title, all speakers, tags, upload time, language
- **Vector embedding** — 384-dimensional semantic representation (when neural search is enabled)

## Search Result Display

### Relevance Percentage

The percentage shown on search results is a **normalized display score** mapped to a 20-99% range:

- **99%** — The most relevant result in this particular search
- **20%** — The least relevant result that passed filtering
- **+5% bonus** — Applied to files that matched on both keyword and semantic signals

This percentage is relative to the current search — it's not an absolute quality score.

### Match Types

Results are classified by how they matched:

- **Keyword match** — Exact word matches found (highlighted in results)
- **Semantic match** — Meaning-based similarity found (related terms highlighted)
- **Both** — Matched on both signals (highest confidence)

### Semantic-Only Filtering

Results that match only on semantic similarity (no keyword overlap) face additional filtering to prevent low-confidence matches from appearing:

- Must exceed a minimum score threshold
- The weakest 35% of semantic-only results are suppressed
- Remaining semantic-only results are labeled with confidence level (high/low)

## Configuration

These settings can be tuned via environment variables:

| Setting | Default | Description |
|---|---|---|
| `SEARCH_RRF_RANK_CONSTANT` | 40 | RRF weighting constant. Lower values give more weight to top-ranked results |
| `SEARCH_RRF_WINDOW_SIZE` | 500 | Number of results each search method retrieves before RRF combination |
| `SEARCH_CHUNK_TARGET_WORDS` | 200 | Target word count per transcript chunk |
| `SEARCH_CHUNK_OVERLAP_WORDS` | 40 | Word overlap between split chunks for context preservation |
| `SEARCH_HYBRID_MIN_SCORE` | 0.01 | Minimum score threshold for semantic-only results |
| `SEARCH_SEMANTIC_SUPPRESS_RATIO` | 0.35 | Ratio of weakest semantic-only results to suppress |
| `OPENSEARCH_NEURAL_SEARCH_ENABLED` | true | Enable/disable semantic search (falls back to keyword-only) |
| `OPENSEARCH_NEURAL_MODEL` | `huggingface/sentence-transformers/all-MiniLM-L6-v2` | Embedding model for semantic search |

### Available Embedding Models

| Tier | Model | Dimensions | Size | Language |
|---|---|---|---|---|
| Fast (default) | all-MiniLM-L6-v2 | 384 | 80MB | English |
| Fast | paraphrase-multilingual-MiniLM-L12-v2 | 384 | 420MB | 50+ languages |
| Balanced | all-mpnet-base-v2 | 768 | 420MB | English |
| Balanced | paraphrase-multilingual-mpnet-base-v2 | 768 | 1.1GB | 50+ languages |
| Best quality | all-distilroberta-v1 | 768 | 290MB | English |
| Best multilingual | distiluse-base-multilingual-cased-v1 | 512 | 480MB | 15 languages |

Changing models requires reindexing all transcripts. Use the admin reindex function after changing the model.

## Technical Architecture

### Search Pipeline

```
User Query
  |
  v
Parse query operators (e.g., speaker:"Jane")
  |
  v
Build hybrid query
  |-- BM25 leg: multi_match on boosted fields (up to 500 results)
  |-- Neural leg: vector similarity via OpenSearch ML (up to 500 results)
  |
  v
OpenSearch RRF pipeline combines both rank lists
  |
  v
Retrieve ~2000 chunks (over-fetch for file grouping)
  |
  v
Filter semantic-only results below thresholds
  |
  v
Group chunks by file (max score per file = file relevance)
  |
  v
Sort and paginate (20 results per page)
  |
  v
Apply semantic highlighting to page results
  |
  v
Normalize scores to 20-99% display range
```

### Index Structure

- **Index name**: `transcript_chunks` (aliased as `transcript_search`)
- **One document per chunk** with denormalized file metadata
- **Custom analyzer**: English snowball stemmer with stop words and shingle filter for the `content` field
- **HNSW vector index**: Cosine similarity, ef_construction=256, m=16 for the embedding field

### Key Implementation Files

| File | Purpose |
|---|---|
| `backend/app/services/search/hybrid_search_service.py` | Search query construction, RRF combination, result grouping |
| `backend/app/services/search/indexing_service.py` | Index mapping, analyzer definitions, bulk indexing |
| `backend/app/services/search/chunking_service.py` | Speaker-turn chunking strategy |
| `backend/app/api/endpoints/search.py` | Search API endpoint |
| `backend/app/core/config.py` | Search configuration defaults |
