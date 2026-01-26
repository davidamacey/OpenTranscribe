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

## AI Models

```bash
WHISPER_MODEL=large-v2  # or: tiny, base, small, medium, large-v3
MIN_SPEAKERS=1
MAX_SPEAKERS=20
HUGGINGFACE_TOKEN=hf_your_token_here
MODEL_CACHE_DIR=./models
```

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

## Authentication

OpenTranscribe supports multiple authentication methods. See [Authentication Overview](../authentication/overview.md) for detailed configuration.

### Authentication Methods

```bash
# LDAP/Active Directory
LDAP_ENABLED=false
LDAP_SERVER=ldaps://your-ad-server.domain.com
LDAP_PORT=636
LDAP_USE_SSL=true
LDAP_BIND_DN=CN=service-account,CN=Users,DC=domain,DC=com
LDAP_BIND_PASSWORD=your-service-account-password
LDAP_SEARCH_BASE=DC=domain,DC=com
LDAP_USERNAME_ATTR=sAMAccountName
LDAP_ADMIN_USERS=admin1,admin2

# Keycloak/OIDC
KEYCLOAK_ENABLED=false
KEYCLOAK_SERVER_URL=https://keycloak.yourdomain.com
KEYCLOAK_REALM=opentranscribe
KEYCLOAK_CLIENT_ID=opentranscribe-app
KEYCLOAK_CLIENT_SECRET=your-client-secret
KEYCLOAK_ADMIN_ROLE=admin

# PKI/X.509 Certificates
PKI_ENABLED=false
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
