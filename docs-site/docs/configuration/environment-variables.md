---
sidebar_position: 1
---

# Environment Variables

Comprehensive reference for all OpenTranscribe environment variables.

## Quick Reference

Edit `.env` file in installation directory. See `.env.example` for full template.

## Database

```bash
POSTGRES_HOST=postgres
POSTGRES_PORT=5176
POSTGRES_USER=postgres
POSTGRES_PASSWORD=auto_generated_on_install
POSTGRES_DB=opentranscribe
```

## GPU Configuration

```bash
TORCH_DEVICE=auto  # or: cuda, mps, cpu
USE_GPU=auto  # or: true, false
GPU_DEVICE_ID=0  # Which GPU (0, 1, 2, etc.)
COMPUTE_TYPE=auto  # or: float16, float32, int8
BATCH_SIZE=auto  # or: 8, 16, 32
```

## Model & Caching

Configure AI models, caching behavior, and model discovery.

```bash
# Whisper Transcription Models
WHISPER_MODEL=large-v3-turbo  # or: large-v3, large-v2, medium, small, base, tiny

# PyAnnote Speaker Diarization
PYANNOTE_VERSION=auto  # or: v3, v4 (auto-detect installed version)
EMBEDDING_MODE=auto  # or: v3, v4 (embedding model version)
MIN_SPEAKERS=1
MAX_SPEAKERS=20

# Model Caching & Storage
MODEL_CACHE_DIR=./models
HUGGINGFACE_CACHE=${MODEL_CACHE_DIR}/huggingface
TORCH_CACHE=${MODEL_CACHE_DIR}/torch
HUGGINGFACE_TOKEN=hf_your_token_here

# Warm Cache (Pre-load Models on Startup)
WARM_CACHE_ENABLED=false
```

### Model Recommendations

| Use Case | Model | Notes |
|----------|-------|-------|
| English (primary) | `large-v3-turbo` | 6x faster, excellent English accuracy |
| Multilingual | `large-v3` | Best accuracy for 100+ languages |
| Translation to English | `large-v3` | Turbo cannot translate |
| Speed-critical | `large-v3-turbo` | Recommended for most use cases |
| Maximum accuracy | `large-v3` | Slower but best overall |

### Whisper Model VRAM Requirements

| Model | Batch Size 1 | Batch Size 8 | Batch Size 16 |
|-------|-------------|-------------|--------------|
| `tiny` | ~1GB | ~2GB | ~3GB |
| `base` | ~1GB | ~2GB | ~3GB |
| `small` | ~2GB | ~4GB | ~6GB |
| `medium` | ~5GB | ~10GB | ~15GB |
| `large-v3-turbo` | ~6GB | ~10GB | ~15GB |
| `large-v3` | ~10GB | ~20GB | ~30GB |
| `large-v2` | ~10GB | ~20GB | ~30GB |

## PyAnnote v4 Configuration

Configure speaker diarization and voice fingerprinting for speaker identification and tracking.

```bash
# Speaker Diarization Version
PYANNOTE_VERSION=auto  # or: v3, v4 (auto-detect installed version)

# Speaker Detection Ranges
MIN_SPEAKERS=1         # Minimum speakers to detect
MAX_SPEAKERS=20        # Maximum speakers to detect (no hard limit, can increase for large events)

# Embedding & Fingerprinting
EMBEDDING_MODE=auto    # or: v3, v4 (which embedding model to use)

# Model Caching & Warmup
WARM_CACHE_ENABLED=false  # Pre-load speaker models on startup for faster first transcription
MODEL_CACHE_DIR=./models
```

### Speaker Detection Use Cases

| Event Type | Speakers | Recommended MAX_SPEAKERS | Notes |
|-----------|----------|-------------------------|-------|
| Small meetings | 2-5 | 20 (default) | Works well with default |
| Medium meetings | 5-15 | 20 (default) | Works well with default |
| Large conferences | 15-30 | 30-40 | Increase MAX_SPEAKERS |
| Very large events | 30-50+ | 50-100 | No hard limit |

### Warm Cache Benefits

Enabling `WARM_CACHE_ENABLED=true` pre-loads PyAnnote models on startup:
- **First transcription**: 15-20 seconds faster (models already loaded)
- **Subsequent transcriptions**: No performance change
- **Trade-off**: ~500MB additional memory usage at startup
- **Recommended for**: High-throughput systems with continuous transcription

## OpenSearch Neural Search

Configure neural search capabilities for semantic search across transcriptions.

```bash
# Enable/Disable Neural Search
NEURAL_SEARCH_ENABLED=true

# ML Commons Plugin (Powers Neural Search)
OPENSEARCH_ML_COMMONS_ENABLED=true

# OpenSearch Connection
OPENSEARCH_URL=http://opensearch:9200
OPENSEARCH_USERNAME=admin
OPENSEARCH_PASSWORD=your_secure_password

# Vector Search Configuration
NEURAL_SEARCH_MODEL_ID=your_model_id  # ML Commons model ID for embeddings
NEURAL_SEARCH_BATCH_SIZE=32
```

### Neural Search VRAM Requirements

| Embedding Model | VRAM (GPU) | VRAM (CPU) | Batch Size |
|-----------------|-----------|-----------|-----------|
| sentence-transformers/all-MiniLM-L6-v2 | ~200MB | ~500MB | 32-64 |
| sentence-transformers/all-mpnet-base-v2 | ~400MB | ~1GB | 16-32 |
| bge-base-en-v1.5 | ~400MB | ~1GB | 16-32 |
| bge-large-en-v1.5 | ~1GB | ~2GB | 8-16 |
| BAAI/bge-large-zh-v1.5 | ~1GB | ~2GB | 8-16 |

### ML Commons Plugin

The OpenSearch ML Commons plugin enables vector embeddings and semantic search:
- **Status**: Automatically detected on OpenSearch startup
- **Configuration**: Database-driven via Admin UI
- **Fallback**: Full-text search if neural search disabled

## LLM Integration

```bash
LLM_PROVIDER=  # vllm, openai, anthropic, ollama, openrouter
VLLM_API_URL=http://localhost:8000/v1
OPENAI_API_KEY=sk-xxxxx
ANTHROPIC_API_KEY=sk-ant-xxxxx
```

## Multi-GPU Scaling

```bash
GPU_SCALE_ENABLED=false
GPU_SCALE_DEVICE_ID=2
GPU_SCALE_WORKERS=4
```

## Ports

```bash
FRONTEND_PORT=5173
BACKEND_PORT=5174
FLOWER_PORT=5175
POSTGRES_PORT=5176
REDIS_PORT=5177
MINIO_PORT=5178
MINIO_CONSOLE_PORT=5179
OPENSEARCH_PORT=5180
```

## HTTPS/SSL Configuration

Enable HTTPS with NGINX reverse proxy for secure access and browser microphone recording from network devices.

```bash
# Set hostname to enable HTTPS (triggers NGINX reverse proxy)
NGINX_SERVER_NAME=opentranscribe.local

# Optional: Custom ports (defaults shown)
NGINX_HTTP_PORT=80
NGINX_HTTPS_PORT=443

# Optional: Custom certificate paths (defaults shown)
NGINX_CERT_FILE=./nginx/ssl/server.crt
NGINX_CERT_KEY=./nginx/ssl/server.key
```

**Quick setup:** Run `./opentranscribe.sh setup-ssl` to configure interactively.

See [NGINX Setup Guide](/docs/configuration/nginx-setup) for full documentation.

## Authentication Configuration

OpenTranscribe uses a **database-driven authentication system** with support for multiple simultaneous auth methods (hybrid authentication). See [Authentication Overview](../authentication/overview.md) for detailed configuration.

### Configuration Sources

Authentication is configured via **Super Admin UI** (Settings → Authentication) and stored in the database with **AES-256-GCM encryption**:

| Configuration Level | Source | Priority | Notes |
|-------------------|--------|----------|-------|
| Primary | Database (`auth_config` table) | ✅ Primary | Set via Super Admin UI |
| Legacy/Override | Environment variables | ⚠️ Secondary | ENV vars override DB for legacy support |

### Multi-Method Authentication

Multiple authentication methods can be enabled simultaneously. Users can authenticate via any enabled method:

```bash
# Authentication Type (Indicator - set via Super Admin UI)
AUTH_TYPE=local,ldap,keycloak  # Enabled methods (informational, read-only)
```

### LDAP/Active Directory Configuration

```bash
# LDAP/Active Directory (configured via Super Admin UI)
# These ENV variables are for legacy/development use only
LDAP_SERVER=ldaps://your-ad-server.domain.com
LDAP_PORT=636
LDAP_USE_SSL=true
LDAP_BIND_DN=CN=service-account,CN=Users,DC=domain,DC=com
LDAP_BIND_PASSWORD=your-service-account-password
LDAP_SEARCH_BASE=DC=domain,DC=com
LDAP_USERNAME_ATTR=sAMAccountName
```

### Keycloak/OIDC Configuration

```bash
# Keycloak/OIDC (configured via Super Admin UI)
# These ENV variables are for legacy/development use only
KEYCLOAK_SERVER_URL=https://keycloak.yourdomain.com
KEYCLOAK_REALM=opentranscribe
KEYCLOAK_CLIENT_ID=opentranscribe-app
KEYCLOAK_CLIENT_SECRET=your-client-secret
KEYCLOAK_ADMIN_ROLE=admin
```

### PKI/X.509 Certificate Configuration

```bash
# PKI/X.509 Certificates (configured via Super Admin UI)
# These ENV variables are for legacy/development use only
PKI_CA_CERT_PATH=/path/to/ca.crt
PKI_ADMIN_DNS=CN=Admin User,O=Company,C=US
```

### Security Features

```bash
# Password Policy (FedRAMP IA-5)
PASSWORD_POLICY_ENABLED=true
PASSWORD_MIN_LENGTH=12
PASSWORD_REQUIRE_UPPERCASE=true
PASSWORD_REQUIRE_LOWERCASE=true
PASSWORD_REQUIRE_DIGIT=true
PASSWORD_REQUIRE_SPECIAL=true
PASSWORD_HISTORY_COUNT=24
PASSWORD_MAX_AGE_DAYS=60

# Account Lockout (NIST AC-7)
ACCOUNT_LOCKOUT_ENABLED=true
ACCOUNT_LOCKOUT_THRESHOLD=5
ACCOUNT_LOCKOUT_DURATION_MINUTES=15
ACCOUNT_LOCKOUT_PROGRESSIVE=true
ACCOUNT_LOCKOUT_MAX_DURATION_MINUTES=1440

# Multi-Factor Authentication
MFA_ENABLED=true
MFA_ISSUER_NAME=OpenTranscribe
MFA_BACKUP_CODE_COUNT=10

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_AUTH_PER_MINUTE=10
RATE_LIMIT_API_PER_MINUTE=100

# Audit Logging (FedRAMP AU-2/AU-3)
AUDIT_LOG_ENABLED=true
AUDIT_LOG_FORMAT=json  # or: cef
AUDIT_LOG_TO_OPENSEARCH=false

# Login Banner
LOGIN_BANNER_ENABLED=false
LOGIN_BANNER_TITLE=Security Notice
LOGIN_BANNER_TEXT=This is a restricted system...
```

## Next Steps

- [Authentication Overview](../authentication/overview.md)
- [GPU Setup](../installation/gpu-setup.md)
- [Multi-GPU Scaling](./multi-gpu-scaling.md)
- [LLM Integration](../features/llm-integration.md)
