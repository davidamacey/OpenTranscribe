# Implementation Plan: Adopting vfilon Fork Features

**Based on:** [Fork Comparison Analysis](./FORK_COMPARISON_vfilon.md)
**Priority:** High-value features that don't conflict with v0.2.1 improvements

---

## Quick Reference: What to Adopt

### Must Adopt (High Value, Low Risk)
- [ ] PyTorch version pinning
- [ ] LLM num_ctx parameter for Ollama
- [ ] Task status reconciliation improvements
- [ ] WebSocket token URL encoding
- [ ] NGINX reverse proxy support

### Consider Adopting (Medium Value)
- [ ] Universal media URL support (requires careful i18n integration)
- [ ] GPU overlay separation
- [ ] Domain-aware access info in scripts

### Do Not Adopt (Superseded by Main)
- tmpfs mode=1777 (main has better implementation)
- Multi-language transcription config (main has WHISPER_LANGUAGE)
- License updates (already done)

---

## Phase 1: Backend Quick Wins

### 1.1 PyTorch Version Pinning

**File:** `backend/requirements.txt`

**Add after line 41:**
```
# PyTorch ecosystem version pinning (prevents transitive dependency breaks)
pytorch-lightning==2.5.6
torchmetrics==1.8.2
pytorch-metric-learning==2.9.0
```

**Test:** `pip install -r requirements.txt` should complete without conflicts.

---

### 1.2 LLM num_ctx Parameter

**File:** `backend/app/services/llm_service.py`

**Find the Ollama payload section** (around line 200-220) and add `num_ctx`:

```python
# In chat_completion() method, Ollama section
if self.provider == LLMProvider.OLLAMA:
    payload = {
        "model": self.model,
        "messages": messages,
        "stream": False,
        "options": {
            "num_ctx": self.user_context_window or 32000  # ADD THIS
        }
    }
```

**Test:** Configure Ollama provider and verify context window is respected.

---

### 1.3 Task Status Reconciliation

**File:** `backend/app/services/task_detection_service.py`

**Add import at top:**
```python
from app.utils.task_utils import update_media_file_from_task_status
```

**In the stuck task detection loop, add reconciliation check:**

```python
# Before marking file as stuck, try to reconcile from task history
refreshed_file = update_media_file_from_task_status(db, media_file.id)
if refreshed_file and refreshed_file.status in [FileStatus.COMPLETED, FileStatus.ERROR]:
    logger.info(f"File {media_file.id} was processing but tasks have finished - skipping recovery")
    continue

# Improve timestamp fallback
last_update = media_file.task_last_update or media_file.task_started_at or media_file.updated_at
if last_update and last_update < stuck_threshold:
    # ... existing stuck handling
```

**Test:** Process a file, simulate status mismatch, verify recovery.

---

## Phase 2: Frontend Quick Win

### 2.1 WebSocket Token Encoding

**File:** `frontend/src/stores/websocket.ts`

**Find line ~150 and update:**

```typescript
// Before
const wsUrl = `${protocol}//${host}/api/ws?token=${token}`;

// After
const wsUrl = `${protocol}//${host}/api/ws?token=${encodeURIComponent(token)}`;
```

**Test:** Verify WebSocket connection works with tokens containing special characters.

---

## Phase 3: NGINX Reverse Proxy Support

### 3.1 Create docker-compose.nginx.yml

**File:** `docker-compose.nginx.yml` (new file)

```yaml
# docker-compose.nginx.yml
# Optional overlay for NGINX reverse proxy with SSL/TLS
#
# Usage:
#   1. Set NGINX_SERVER_NAME in .env
#   2. Place SSL certificates in nginx/ssl/
#   3. Run: ./opentr.sh start prod
#
# The script auto-detects NGINX_SERVER_NAME and includes this overlay.

services:
  nginx:
    image: nginx:1.27-alpine
    container_name: opentranscribe-nginx
    restart: always
    depends_on:
      frontend:
        condition: service_started
      backend:
        condition: service_started
      flower:
        condition: service_started
      minio:
        condition: service_started
    env_file:
      - .env
    command: >
      /bin/sh -c "envsubst '$$NGINX_SERVER_NAME'
      < /etc/nginx/templates/site.conf.template
      > /etc/nginx/conf.d/site.conf && nginx -g 'daemon off;'"
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ${NGINX_CERT_FILE:-./nginx/ssl/site.crt}:/etc/nginx/certs/site.crt:ro
      - ${NGINX_CERT_KEY:-./nginx/ssl/site.key}:/etc/nginx/certs/site.key:ro
      - ./nginx/site.conf.template:/etc/nginx/templates/site.conf.template:ro
    networks:
      - default

networks:
  default:
    name: ${COMPOSE_PROJECT_NAME:-opentranscribe}_default
```

---

### 3.2 Create nginx/site.conf.template

**File:** `nginx/site.conf.template` (new file)

```nginx
# OpenTranscribe NGINX Configuration
# Handles SSL termination and reverse proxy to services

server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name ${NGINX_SERVER_NAME};

    # Redirect HTTP to HTTPS
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;
    server_name ${NGINX_SERVER_NAME};

    # SSL Configuration
    ssl_certificate /etc/nginx/certs/site.crt;
    ssl_certificate_key /etc/nginx/certs/site.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;

    # File upload size limit (for audio/video transcription)
    client_max_body_size 2G;
    client_body_timeout 300s;
    client_body_buffer_size 128k;

    # Common proxy settings
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # Frontend SPA
    location / {
        proxy_pass http://frontend:8080;
        proxy_http_version 1.1;
    }

    # Backend WebSocket (must be before /api/ to match first)
    location /api/ws {
        proxy_pass http://backend:8080/api/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }

    # Backend REST API
    location /api/ {
        proxy_pass http://backend:8080/api/;
        proxy_http_version 1.1;
        proxy_request_buffering off;
        proxy_read_timeout 600s;
        proxy_connect_timeout 600s;
        proxy_send_timeout 600s;
    }

    # Flower dashboard
    location /flower/ {
        proxy_pass http://flower:5555/flower/;
        proxy_http_version 1.1;
        proxy_redirect off;
    }

    # MinIO Console
    location /minio/ {
        proxy_pass http://minio:9001/;
        proxy_http_version 1.1;
    }
}
```

---

### 3.3 Create nginx/ssl/.gitkeep

**File:** `nginx/ssl/.gitkeep` (new empty file)

This keeps the directory in git for users to place their SSL certificates.

---

### 3.4 Update .env.example

**Add to `.env.example` (NGINX section):**

```bash
# =============================================================================
# NGINX Reverse Proxy (Optional)
# =============================================================================
# Set NGINX_SERVER_NAME to enable NGINX reverse proxy with SSL
# Leave empty to use direct container access (default)

# Your domain name (e.g., transcribe.example.com)
# NGINX_SERVER_NAME=

# SSL certificate paths (relative to project root)
# NGINX_CERT_FILE=./nginx/ssl/site.crt
# NGINX_CERT_KEY=./nginx/ssl/site.key
```

---

### 3.5 Update opentr.sh

**Add early .env loading after shebang:**

```bash
#!/bin/bash

# Load environment variables from .env if present
if [ -f ".env" ]; then
  set -a
  source ./.env
  set +a
fi
```

**In start_app() function, add NGINX detection:**

```bash
# Add NGINX overlay if NGINX_SERVER_NAME is set
if [ -n "$NGINX_SERVER_NAME" ]; then
  COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.nginx.yml"
  echo "📡 NGINX reverse proxy enabled for: $NGINX_SERVER_NAME"
fi
```

---

### 3.6 Update scripts/common.sh - Domain-Aware Access Info

**Replace print_access_info() function:**

```bash
print_access_info() {
  local domain=""
  local protocol="https"

  # Check for NGINX configuration
  if [ -f .env ]; then
    domain=$(grep '^NGINX_SERVER_NAME=' .env | grep -v '^#' | cut -d'=' -f2 | tr -d ' "' | head -1)
  fi

  # Also check environment variable
  if [ -z "$domain" ]; then
    domain="${NGINX_SERVER_NAME:-}"
  fi

  if [ -n "$domain" ]; then
    # NGINX reverse proxy mode
    echo "🌐 Access the application at:"
    echo "   - Frontend: ${protocol}://${domain}"
    echo "   - API: ${protocol}://${domain}/api"
    echo "   - API Documentation: ${protocol}://${domain}/api/docs"
    echo "   - MinIO Console: ${protocol}://${domain}/minio"
    echo "   - Flower Dashboard: ${protocol}://${domain}/flower"
  else
    # Direct container access mode (default)
    echo "🌐 Access the application at:"
    echo "   - Frontend: http://localhost:5173"
    echo "   - API: http://localhost:5174/api"
    echo "   - API Documentation: http://localhost:5174/docs"
    echo "   - MinIO Console: http://localhost:5179"
    echo "   - Flower Dashboard: http://localhost:5175/flower"
    echo "   - OpenSearch Dashboards: http://localhost:5182"
  fi
}
```

---

## Phase 4: Universal Media URL Support (Future)

This is a larger change that requires careful integration with main's i18n system.

### Files to Modify:

1. **`backend/app/services/youtube_service.py`**
   - Change URL validation pattern to accept generic URLs
   - Update source detection to use yt-dlp extractor
   - Rename service to `media_service.py` (optional)

2. **`frontend/src/components/FileUploader.svelte`**
   - Rename `youtubeUrl` to `mediaUrl`
   - Update placeholder text (with i18n keys)
   - Update button text (with i18n keys)

3. **`frontend/src/lib/i18n/locales/*.json`**
   - Add new translation keys for universal media support

4. **`backend/app/api/endpoints/files/url_processing.py`**
   - Update endpoint documentation to reflect universal support

### Estimated Effort: Medium (requires i18n updates in 7 languages)

---

## Testing Checklist

### Phase 1 Tests
- [ ] `pip install -r requirements.txt` completes without errors
- [ ] Ollama context window is respected (check logs)
- [ ] Stuck task recovery works correctly

### Phase 2 Tests
- [ ] WebSocket connects with tokens containing `+`, `=`, `/` characters

### Phase 3 Tests
- [ ] `./opentr.sh start prod` with NGINX_SERVER_NAME set
- [ ] HTTPS redirect works (HTTP → HTTPS)
- [ ] WebSocket connections work through NGINX
- [ ] Large file uploads work (test 1GB+ file)
- [ ] Flower dashboard accessible at /flower/
- [ ] MinIO console accessible at /minio/

---

## Rollback Plan

All changes are additive and backward-compatible:

- **PyTorch pinning:** Remove lines from requirements.txt
- **num_ctx:** Remove the options dict from Ollama payload
- **Task reconciliation:** Remove the reconciliation check
- **WebSocket encoding:** Remove encodeURIComponent()
- **NGINX:** Delete docker-compose.nginx.yml, nginx/ directory; unset NGINX_SERVER_NAME

---

## Documentation Updates Needed

After implementation:

1. Update `CLAUDE.md` with NGINX configuration section
2. Update `README.md` with NGINX deployment instructions
3. Add `docs-site/docs/deployment/nginx.md` for detailed guide
