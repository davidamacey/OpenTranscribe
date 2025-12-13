---
sidebar_position: 1
---

# LLM Integration

OpenTranscribe integrates with multiple Large Language Model (LLM) providers for AI-powered features like summarization and speaker identification.

## Supported Providers

- **vLLM**: Self-hosted, high-performance inference
- **OpenAI**: GPT-4, GPT-4o, and compatible models
- **Anthropic**: Claude 3.5, Claude 3, and Claude Opus 4.5 models
- **Ollama**: Local LLM server with many model options
- **OpenRouter**: Access to multiple models through one API

## Key Features

### AI Summarization

Generate BLUF (Bottom Line Up Front) summaries with:
- Executive summary
- Key discussion points
- Speaker analysis and talk time
- Action items with priorities
- Decisions and follow-ups

**Multilingual Output (New in v0.2.0)**:
Generate summaries in 12 different languages:
- English, Spanish, French, German
- Portuguese, Chinese, Japanese, Korean
- Italian, Russian, Arabic, Hindi

Configure in Settings → Transcription → LLM Output Language.

### Speaker Identification

LLM-powered speaker name suggestions based on:
- Conversation context
- Speaking patterns
- Topic expertise
- Cross-video speaker matching

### Model Auto-Discovery (New in v0.2.0)

Automatic model discovery for multiple providers:

**Supported providers:**
- **vLLM**: OpenAI-compatible /v1/models endpoint
- **Ollama**: Native /api/tags endpoint
- **Anthropic**: Native /v1/models endpoint

**Features:**
- Model selection dropdown populated dynamically
- No manual model name entry required
- Edit mode supports stored API keys (no need to re-enter)
- Works with any OpenAI-compatible API endpoint

## Configuration

Set your preferred provider in `.env`:

```bash
# LLM Provider Selection
LLM_PROVIDER=vllm  # or: openai, anthropic, ollama, openrouter

# Provider-specific settings
VLLM_API_URL=http://your-vllm-server:8000/v1
OPENAI_API_KEY=sk-xxxxx
ANTHROPIC_API_KEY=sk-ant-xxxxx
OLLAMA_API_URL=http://localhost:11434
```

## Provider-Specific Guides

### vLLM (Self-Hosted)

Best for privacy-first deployments:

```bash
# Example vLLM server setup
docker run --gpus all -p 8000:8000 vllm/vllm-openai:latest \
  --model meta-llama/Llama-2-70b-chat-hf
```

Configure in `.env`:
```bash
LLM_PROVIDER=vllm
VLLM_API_URL=http://localhost:8000/v1
VLLM_MODEL_NAME=meta-llama/Llama-2-70b-chat-hf
```

### OpenAI

Quick setup with commercial API:

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-xxxxx
OPENAI_MODEL=gpt-4o
```

### Anthropic

Claude models with automatic model discovery:

```bash
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-xxxxx
ANTHROPIC_MODEL=claude-opus-4-5-20251101  # or claude-sonnet-4-20250514
```

**Default model:** claude-opus-4-5-20251101 (Claude Opus 4.5)

### Ollama

Local LLM server:

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull a model
ollama pull llama3.2:latest

# Configure OpenTranscribe
LLM_PROVIDER=ollama
OLLAMA_API_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:latest
```

**Default model:** llama3.2:latest

## No LLM Mode

OpenTranscribe works without LLM configuration:
- Transcription: ✅ Full functionality
- Speaker Diarization: ✅ Full functionality
- AI Summarization: ❌ Requires LLM
- Speaker Identification Suggestions: ❌ Requires LLM

Leave `LLM_PROVIDER` empty to disable AI features.

## Next Steps

- [User Guide: AI Summarization](../user-guide/ai-summarization.md)
- [Environment Variables](../configuration/environment-variables.md)
- [FAQ](../faq.md)
