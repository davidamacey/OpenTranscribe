---
sidebar_position: 1
---

# LLM Integration

OpenTranscribe integrates with multiple Large Language Model (LLM) providers for AI-powered features like summarization and speaker identification.

## Supported Providers

- **vLLM**: Self-hosted, high-performance inference
- **OpenAI**: GPT-4, GPT-3.5, and compatible models
- **Anthropic Claude**: Claude 3 models (Opus, Sonnet, Haiku)
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

### Speaker Identification

LLM-powered speaker name suggestions based on:
- Conversation context
- Speaking patterns
- Topic expertise
- Cross-video speaker matching

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
OPENAI_MODEL=gpt-4-turbo-preview
```

### Ollama

Local LLM server:

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull a model
ollama pull llama2:70b

# Configure OpenTranscribe
LLM_PROVIDER=ollama
OLLAMA_API_URL=http://localhost:11434
OLLAMA_MODEL=llama2:70b
```

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
