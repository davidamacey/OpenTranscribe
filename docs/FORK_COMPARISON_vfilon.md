# Fork Comparison: vfilon/OpenTranscribe vs davidamacey/OpenTranscribe

**Analysis Date:** December 13, 2025
**Fork URL:** https://github.com/vfilon/OpenTranscribe
**Main Repo Version:** v0.2.1
**Fork Base Version:** v0.1.0

## Executive Summary

The vfilon fork diverged from OpenTranscribe at v0.1.0 and added 14 commits with notable features:
- **Universal Media URL Support** - Expanded beyond YouTube to 1000+ platforms via yt-dlp
- **NGINX Reverse Proxy** - Production-ready SSL/TLS configuration
- **SpeakerSelector Component** - New frontend component for speaker management
- **GPU Configuration Separation** - Cleaner Docker overlay architecture
- **Task Status Reconciliation** - Better handling of stuck tasks

However, the main repo (v0.2.1) has also evolved significantly since v0.1.0 with:
- **Comprehensive i18n** - 7 language UI support
- **Refactored LLM Service** - Cleaner code with helper methods
- **tmpfs Security Hardening** - Secure temporary storage across all workers
- **Transcript Pagination** - Better handling of large transcripts
- **User Transcription Settings** - Per-user preferences

---

## Fork Commits Analysis

The fork contains **14 commits** after v0.1.0:

| Commit | Description | Value Assessment |
|--------|-------------|------------------|
| `f00bb22` | PyTorch ecosystem version pinning | **Useful** - Prevents dependency issues |
| `89a15ae` | Universal media URL processing | **Valuable** - Major feature expansion |
| `b1792f1` | tmpfs mode=1777 permissions | **Superseded** - Main has better tmpfs |
| `9b23c43` | NGINX reverse proxy configuration | **Valuable** - Production feature |
| `bc560e7` | GPU worker configuration enhancement | **Mixed** - Different approach than main |
| `1bd0692` | Dependencies update (minio, fonts) | **Superseded** - Main has newer deps |
| `0994c81` | LLM context window configuration | **Valuable** - Useful feature |
| `53f3601` | Task status reconciliation improvements | **Valuable** - Better error recovery |
| `da156ff` | Speaker management enhancements | **Mixed** - Good UI, but main has different approach |
| `9957395` | Task recovery logic enhancement | **Valuable** - Better reliability |
| `8038497` | Multi-language transcription support | **Superseded** - Main has this + i18n |
| `52f8675` | GPU overlay separation | **Consider** - Cleaner architecture |
| `d7a38b6` | License update (MIT → AGPL-3.0) | **Already done** - Main has this |
| `cb3f556` | License references update | **Already done** - Main has this |

---

## Detailed Comparison by Category

### 1. Backend Changes

#### 1.1 Dependencies (requirements.txt)

| Aspect | Fork | Main (v0.2.1) | Recommendation |
|--------|------|---------------|----------------|
| PyTorch ecosystem | Pins `pytorch-lightning==2.5.6`, `torchmetrics==1.8.2`, `pytorch-metric-learning==2.9.0` | Not pinned | **ADOPT** - Prevents transitive dependency breaks |
| minio | `>=7.2.18` | `>=7.1.17` | Already compatible |

#### 1.2 LLM Service (llm_service.py)

**Fork Approach:**
- Monolithic code with inline logic
- `summary_language` parameter (optional string)
- Manual `LANGUAGE_NAME_MAP` dictionary
- CLAUDE provider still active

**Main Approach:**
- Refactored with helper methods:
  - `_extract_claude_response()`
  - `_extract_ollama_response()`
  - `_extract_openai_response()`
  - `_send_llm_request()`
  - `_split_oversized_chunk_by_sentences()`
  - `_split_by_speaker_segments()`
  - `_get_provider_config()`
- `output_language` parameter with `LLM_OUTPUT_LANGUAGES` constant
- CLAUDE deprecated in favor of ANTHROPIC
- Better logging with resolved endpoint info

**Fork-Only Feature:**
```python
# Fork adds num_ctx for Ollama context window
"options": {
    "num_ctx": self.user_context_window or 32000
}
```

**Recommendation:** Keep main's refactored structure but **ADOPT** the `num_ctx` parameter for Ollama.

#### 1.3 YouTube Service (youtube_service.py)

**Critical Difference:**

| Feature | Fork | Main |
|---------|------|------|
| URL Validation | `GENERIC_URL_PATTERN` (any HTTP/HTTPS) | `YOUTUBE_URL_PATTERN` (strict YouTube) |
| Source Detection | Dynamic from `extractor` | Hardcoded `"youtube"` |
| Platform Support | YouTube, Vimeo, Twitter/X, TikTok, etc. | YouTube only |

**Fork Implementation:**
```python
# Fork - Accepts any HTTP/HTTPS URL
def is_valid_youtube_url(self, url: str) -> bool:
    """Now supports generic URLs (YouTube, Vimeo, etc.) via yt-dlp."""
    return bool(GENERIC_URL_PATTERN.match(url.strip()))

# Fork - Dynamic source detection
source = youtube_info.get("extractor", "youtube").lower()
return {"source": source, ...}
```

**Main Implementation:**
```python
# Main - Strict YouTube pattern
def is_valid_youtube_url(self, url: str) -> bool:
    return bool(YOUTUBE_URL_PATTERN.match(url.strip()))

# Main - Hardcoded source
return {"source": "youtube", ...}
```

**Recommendation:** **STRONGLY CONSIDER ADOPTING** universal media URL support - significant feature expansion.

#### 1.4 Task Detection Service (task_detection_service.py)

**Fork Adds Status Reconciliation:**
```python
# Fork - Before marking file as stuck, check task history
from app.utils.task_utils import update_media_file_from_task_status

# Check for completed tasks before marking as stuck
refreshed_file = update_media_file_from_task_status(db, media_file.id)
if refreshed_file and refreshed_file.status in [FileStatus.COMPLETED, FileStatus.ERROR]:
    logger.info("File was marked as processing but all tasks have finished...")
    continue
```

**Fork uses better timestamp fallback:**
```python
# Fork - Multiple timestamp sources
last_update = media_file.task_last_update or media_file.task_started_at or media_file.upload_time

# Main - Single timestamp
if media_file.updated_at and media_file.updated_at < stuck_threshold:
```

**Recommendation:** **ADOPT** - Better handling of edge cases where tasks complete but status isn't updated.

#### 1.5 Configuration (config.py)

| Setting | Fork | Main |
|---------|------|------|
| WHISPER_LANGUAGE | Not present | `os.getenv("WHISPER_LANGUAGE", "auto")` |
| MIN_SPEAKERS | Not present | `int(os.getenv("MIN_SPEAKERS", "1"))` |
| MAX_SPEAKERS | Not present | `int(os.getenv("MAX_SPEAKERS", "20"))` |
| NUM_SPEAKERS | Not present | Optional int |

**Recommendation:** Main already has these - no action needed.

---

### 2. Frontend Changes

#### 2.1 FileUploader.svelte

**Fork - Universal Media URL:**
```svelte
<!-- Fork -->
let mediaUrl = '';

async function processUrl() {
  const response = await axiosInstance.post('/files/process-url', {
    url: mediaUrl.trim()
  });
}

<input id="media-url" bind:value={mediaUrl} placeholder="YouTube, Vimeo, Twitter/X, TikTok, etc." />
<button on:click={processUrl}>Process Media</button>
```

**Main - YouTube-Specific:**
```svelte
<!-- Main -->
let youtubeUrl = '';

async function processYouTubeUrl() { ... }

<input id="youtube-url" bind:value={youtubeUrl} />
<button on:click={processYouTubeUrl}>{$t('uploader.processYoutubeTooltip')}</button>
```

**Key Differences:**
| Aspect | Fork | Main |
|--------|------|------|
| Variable naming | `mediaUrl` | `youtubeUrl` |
| Function naming | `processUrl()` | `processYouTubeUrl()` |
| Internationalization | None | Full i18n with `$t()` |
| Platform scope | Universal | YouTube only |

**Recommendation:** **ADOPT** universal media support while **PRESERVING** main's i18n infrastructure.

#### 2.2 SpeakerSelector.svelte (NEW in Fork)

**Fork adds a 294-line component** that doesn't exist in main:

```svelte
<!-- Fork - SpeakerSelector.svelte (key features) -->
<script lang="ts">
  export interface SpeakerOption {
    id?: string | number;
    uuid?: string;
    name?: string;
    display_name?: string | null;
    speaker_label?: string | null;
  }

  export let speakerList: SpeakerOption[] = [];
  export let selectedSpeakerId: string | number | null = null;
  export let fallbackLabel: string = 'Unknown speaker';
  export let disabled: boolean = false;
  export let includeCreateOption: boolean = true;
</script>

<!-- Features -->
- Searchable dropdown with filtering
- Speaker sorting by original numbering (SPEAKER_XX)
- Create new speaker option with auto-incrementing
- Full accessibility support (aria-haspopup, aria-expanded)
- Light/dark mode support
```

**Recommendation:** **EVALUATE** - Main may have different speaker UI. Check if this improves UX.

#### 2.3 WebSocket Token Handling (websocket.ts)

```typescript
// Fork - URL-encoded token
const wsUrl = `${protocol}//${host}/api/ws?token=${encodeURIComponent(token)}`;

// Main - Direct token (no encoding)
const wsUrl = `${protocol}//${host}/api/ws?token=${token}`;
```

**Recommendation:** **ADOPT** `encodeURIComponent()` - safer for tokens with special characters.

#### 2.4 Flower Dashboard URL (Navbar.svelte)

**Fork - Hardcoded:**
```typescript
const url = `${protocol}//${host}/flower/`;
```

**Main - Configurable:**
```typescript
const port = import.meta.env.VITE_FLOWER_PORT || '5175';
const urlPrefix = import.meta.env.VITE_FLOWER_URL_PREFIX || 'flower';
const url = `${protocol}//${host}:${port}/${urlPrefix}/`;
```

**Recommendation:** Keep main's approach - more flexible for different deployments.

#### 2.5 Main-Only Features (Not in Fork)

- **i18n/Internationalization** - 7 language support
- **Transcript Pagination** - Better handling of large transcripts
- **Transcription Settings API** - User-level preferences
- **Speaker notification type** in WebSocket (`speaker_updated`)

---

### 3. Infrastructure/Docker Changes

#### 3.1 docker-compose.yml - tmpfs Configuration

**Main has tmpfs hardening** that fork lacks:

```yaml
# Main - tmpfs for all workers
services:
  backend:
    tmpfs:
      - /app/temp:noexec,nosuid,size=4g,mode=1777
  celery-worker:
    tmpfs:
      - /app/temp:noexec,nosuid,size=20g,mode=1777
  # ... same for all workers
```

**Fork:** No tmpfs configuration.

**Recommendation:** Keep main's tmpfs - **security hardening**.

#### 3.2 docker-compose.gpu.yml (NEW in Fork)

Fork separates GPU config into an overlay:

```yaml
# Fork - docker-compose.gpu.yml
services:
  celery-worker:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              capabilities: [gpu]
              device_ids: ['${GPU_DEVICE_ID:-0}']
```

**Main:** GPU config baked into base docker-compose.yml.

**Recommendation:** **CONSIDER** - Cleaner separation for macOS/CPU-only systems.

#### 3.3 docker-compose.nginx.yml (NEW in Fork)

**Full NGINX reverse proxy support:**

```yaml
# Fork - docker-compose.nginx.yml
services:
  nginx:
    image: nginx:1.27-alpine
    ports:
      - 80:80
      - 443:443
    volumes:
      - ${NGINX_CERT_FILE:-./nginx/ssl/site.crt}:/etc/nginx/certs/site.crt:ro
      - ${NGINX_CERT_KEY:-./nginx/ssl/site.key}:/etc/nginx/certs/site.key:ro
```

**Main:** No NGINX support.

**Recommendation:** **STRONGLY CONSIDER ADOPTING** - Essential for production deployments.

#### 3.4 nginx/site.conf.template (NEW in Fork)

**Production-ready NGINX configuration:**

```nginx
# Fork - Key features
server {
    listen 443 ssl;
    http2 on;
    ssl_protocols TLSv1.2 TLSv1.3;

    client_max_body_size 2G;       # Large file uploads
    proxy_read_timeout 600s;        # Long transcription requests

    location /api/ws { ... }        # WebSocket proxy
    location /api/ { ... }          # REST API proxy
    location /flower/ { ... }       # Flower dashboard
    location /minio/ { ... }        # MinIO console
}
```

**Recommendation:** **ADOPT** - Critical for production deployments with SSL.

#### 3.5 docker-compose.override.yml - Image Naming

**Fork explicitly names images:**
```yaml
# Fork - Explicit image names for cache efficiency
services:
  backend:
    image: opentranscribe-backend-dev:latest
  celery-worker:
    image: opentranscribe-backend-dev:latest  # Reuses same image
```

**Main:** Implicit naming.

**Recommendation:** **CONSIDER** - May save overlay2 storage.

#### 3.6 opentr.sh Script Enhancements

**Fork additions:**

1. **Early .env loading:**
```bash
if [ -f ".env" ]; then
  set -a
  source ./.env
  set +a
fi
```

2. **GPU auto-detection:**
```bash
if [ "$DOCKER_RUNTIME" = "nvidia" ] && [ -f "docker-compose.gpu.yml" ]; then
  COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.gpu.yml"
fi
```

3. **NGINX auto-detection:**
```bash
if [ -n "$NGINX_SERVER_NAME" ]; then
  COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.nginx.yml"
fi
```

4. **Domain-aware access info:**
```bash
# Shows https://domain.com instead of localhost when NGINX configured
```

**Recommendation:** **ADOPT** - Better production workflow.

---

## Evaluation Summary

### Changes to ADOPT (High Value)

| Change | Reason | Files Affected |
|--------|--------|----------------|
| Universal Media URL Support | Major feature - 1000+ platform support | `youtube_service.py`, `FileUploader.svelte`, backend endpoint |
| NGINX Reverse Proxy | Production essential | `docker-compose.nginx.yml`, `nginx/site.conf.template`, `opentr.sh` |
| Task Status Reconciliation | Better reliability | `task_detection_service.py` |
| LLM num_ctx Parameter | Ollama context window config | `llm_service.py` |
| PyTorch Version Pinning | Dependency stability | `requirements.txt` |
| WebSocket Token Encoding | Security best practice | `websocket.ts` |
| GPU/NGINX Auto-detection | Better UX | `opentr.sh`, `scripts/common.sh` |

### Changes to CONSIDER (Medium Value)

| Change | Reason | Consideration |
|--------|--------|---------------|
| docker-compose.gpu.yml separation | Cleaner architecture | May conflict with main's GPU profiles |
| SpeakerSelector component | New UI component | Evaluate against main's speaker UI |
| Explicit Docker image naming | Storage efficiency | Minor benefit |

### Changes NOT to Adopt (Already Superseded)

| Change | Reason |
|--------|--------|
| tmpfs mode=1777 | Main has full tmpfs with noexec,nosuid |
| Multi-language transcription | Main has WHISPER_LANGUAGE + full i18n |
| License updates | Already in main |
| Dependencies (minio) | Main has compatible versions |

### Main Features to PRESERVE

| Feature | Reason |
|---------|--------|
| i18n/Internationalization | 7 language UI support |
| Refactored LLM Service | Cleaner, maintainable code |
| tmpfs Security Hardening | Production security |
| Transcript Pagination | Better UX for large transcripts |
| User Transcription Settings | Per-user preferences |
| Configurable Flower URL | Deployment flexibility |

---

## Implementation Plan

### Phase 1: Backend (Low Risk)

1. **Add PyTorch version pinning to requirements.txt**
   - Add `pytorch-lightning==2.5.6`
   - Add `torchmetrics==1.8.2`
   - Add `pytorch-metric-learning==2.9.0`

2. **Add num_ctx to LLM Service**
   - Add `num_ctx` to Ollama payload in `llm_service.py`

3. **Improve Task Detection Service**
   - Add status reconciliation before marking files as stuck
   - Use multiple timestamp fallbacks

### Phase 2: Infrastructure (Medium Risk)

1. **Add NGINX support**
   - Create `docker-compose.nginx.yml`
   - Create `nginx/site.conf.template`
   - Add NGINX environment variables to `.env.example`

2. **Update opentr.sh**
   - Add early .env loading
   - Add NGINX auto-detection
   - Add domain-aware access info to `scripts/common.sh`

3. **Consider GPU overlay separation**
   - Evaluate creating `docker-compose.gpu.yml`
   - Update opentr.sh for GPU auto-detection

### Phase 3: Frontend (Higher Risk - Requires Testing)

1. **Implement Universal Media URL Support**
   - Update `youtube_service.py` to accept generic URLs
   - Rename `youtubeUrl` to `mediaUrl` in FileUploader (preserve i18n)
   - Update API endpoint descriptions

2. **Add WebSocket token encoding**
   - Update `websocket.ts` to use `encodeURIComponent()`

3. **Evaluate SpeakerSelector component**
   - Compare with existing speaker UI
   - Determine if adoption improves UX

---

## Conclusion

The vfilon fork adds valuable production features (NGINX, universal media) that would benefit OpenTranscribe users. However, the main repo has evolved significantly with i18n, refactored code, and security hardening that should be preserved.

**Recommended approach:** Cherry-pick specific features from the fork while maintaining main's architectural improvements. The universal media URL support and NGINX reverse proxy are the highest-value additions that would make OpenTranscribe more versatile for production deployments.

**Note to fork author:** Consider submitting these as PRs! The universal media support and NGINX configuration would be excellent contributions to the project.
