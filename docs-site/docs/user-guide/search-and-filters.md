---
sidebar_position: 4
---

# Search & Filters

OpenTranscribe provides powerful hybrid search combining full-text and semantic search with advanced filtering.

![Search transcripts page with advanced filters sidebar](/img/screenshots/search/search-empty.png)

## Search Types

### Full-Text Search
Lightning-fast keyword search powered by OpenSearch 3.4.0:
- Exact phrase matching
- Wildcard support
- Boolean operators (AND, OR, NOT)
- Optimized scoring and relevance ranking

### Semantic Search
AI-powered contextual search:
- Finds conceptually similar content
- Works across paraphrases
- Understands meaning, not just keywords

### Hybrid Search
Combines full-text and semantic search for the best results:
- Automatic score normalization across search types
- Weighted combination for optimal relevance
- Falls back gracefully if neural search is unavailable

:::note Hybrid Search Fix (v0.4.0)
A critical bug in OpenSearch 3.4 caused hybrid search to silently fall back to keyword-only (BM25) search due to an `ArrayIndexOutOfBoundsException` triggered by the combination of aggregations, `collapse`, and RRF search pipelines. This was fixed in v0.4.0 — semantic search now works as intended. The improvement is significant: for example, searching "pytorch" went from 1 result to 83 results after the fix. Typo tolerance and query latency (255–500ms) are also confirmed working. If you were using an earlier version, reindexing is not required — the fix is in the query layer.
:::

## Filters

Filter transcriptions by:
- **Speaker**: Find content by specific speakers
- **Date Range**: Time-based filtering
- **Duration**: File length
- **Tags**: Custom categorization
- **Collections**: Grouped media files
- **Status**: Processing status
- **File Type**: Audio vs video

## Gallery Views

![Gallery overview with filter sidebar showing tags, collections, and speakers](/img/screenshots/gallery/gallery-overview.png)

The main file gallery supports multiple display modes:

- **Grid View**: Card-based layout showing thumbnails and metadata (default)
- **List View**: Compact table layout for faster scanning of large libraries
- **Pagination**: Navigate through large file collections with configurable page sizes
- **Virtual Scrolling**: Smooth performance even with thousands of files

## Search Query Syntax

### Full-Text Search Operators

OpenTranscribe's full-text search supports standard query syntax:

| Syntax | Example | Description |
|--------|---------|-------------|
| **Exact phrase** | `"project deadline"` | Matches the exact phrase |
| **AND** | `budget AND timeline` | Both terms must appear |
| **OR** | `budget OR finance` | Either term can appear |
| **NOT** | `meeting NOT standup` | Excludes a term |
| **Wildcard** | `transcri*` | Matches any suffix (transcribe, transcription, etc.) |
| **Fuzzy match** | Automatic | Handles typos and minor spelling variations |

Operators can be combined: `"quarterly review" AND budget NOT draft`

### Semantic Search Tips

Semantic search finds conceptually related content even when exact words differ:

- Search for `"budget concerns"` to find mentions of "financial constraints", "cost overruns", or "spending limits"
- Search for `"next steps"` to find action items, follow-ups, and task assignments
- Works best with natural language queries rather than single keywords
- Semantic search runs automatically alongside full-text search in hybrid mode

### Combining Filters with Search

For maximum precision, combine text queries with filters:

1. Enter your search query in the search bar
2. Open the **Filter** sidebar
3. Apply filters (speaker, date range, tags, collections, file type)
4. Results are narrowed to match both the query and all active filters

### Search Result Highlighting

When search results are returned, matching text is highlighted with `<em>` tags in the result snippets. This makes it easy to see exactly where your search terms appear within each transcript. Result snippets show up to 150 characters of surrounding context for each match.

![Search results with highlighted matching transcript segments](/img/screenshots/search/search-results.png)

## Transcript Comments

Add timestamped comments to any transcript for notes, annotations, or collaboration.

### Adding a Comment

1. Open a transcript and navigate to the **Comments** section
2. Type your comment in the text area
3. Click **"Mark Current Time"** to attach the current playback timestamp -- a timestamp is required
4. Click **"Add Comment"** to save

### Timestamp-Linked Comments

Every comment is linked to a specific point in the media file:

- Comments display the timestamp in `MM:SS` format
- Click the **timestamp badge** on any comment to jump the player to that moment
- Comments are sorted chronologically by timestamp
- You can clear and re-set the timestamp before submitting

### Editing and Deleting Comments

- **Edit**: Click the **Edit** link on your own comment, modify the text, then click **Save**
- **Delete**: Click the **Delete** link on your own comment and confirm the deletion
- Only the comment author can edit or delete their comments
- A confirmation dialog appears before deletion to prevent accidental removal

### Comments in Exports

When exporting a transcript as `.txt`, you can optionally include comments in the export output (see [Export Options](./uploading-files.md#export-options)).

## Next Steps

- [Collections](./collections.md)
- [Speaker Management](./speaker-management.md)
