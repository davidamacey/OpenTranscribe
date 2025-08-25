# LLM Deployment Options for OpenTranscribe

OpenTranscribe supports multiple AI summarization backends. Choose the option that best fits your infrastructure and requirements.

## Deployment Scenarios

### 1. Cloud-Only (Recommended for Most Users)
Use external API providers like OpenAI, Claude, or OpenRouter.

**Setup:**
```bash
# Copy environment template
cp .env.example .env

# Edit .env and configure your provider
LLM_PROVIDER=openai
OPENAI_API_KEY=your-api-key-here
OPENAI_MODEL_NAME=gpt-4o-mini

# Start without local LLM
docker compose up
```

**Supported Providers:**
- `openai` - OpenAI GPT models
- `anthropic` - Claude models  
- `custom` - OpenRouter (supports many models)

### 2. Local vLLM Inference (High-Performance GPUs)
Run powerful models locally using vLLM for maximum privacy and control.

**Requirements:** NVIDIA GPU with 16GB+ VRAM

**Setup:**
```bash
# Configure for vLLM  
echo "LLM_PROVIDER=vllm" >> .env
echo "VLLM_MODEL_NAME=gpt-oss-20b" >> .env

# Edit docker-compose.vllm.yml to uncomment your desired model
# 20B model is enabled by default

# Start with vLLM service
docker compose -f docker-compose.yml -f docker-compose.vllm.yml up
```

**Available Models (edit docker-compose.vllm.yml to select):**
- `vllm-gptoss-20b` - 20B parameter model (16GB VRAM) - **Default enabled**
- `vllm-gptoss-120b` - 120B parameter model (96GB VRAM) - Commented out by default

### 3. Local Ollama Inference (Consumer GPUs)
More user-friendly local inference for smaller models.

**Requirements:** NVIDIA GPU with 8GB+ VRAM

**Setup:**
```bash
# Configure for Ollama
echo "LLM_PROVIDER=ollama" >> .env  
echo "OLLAMA_MODEL_NAME=llama3.2:3b-instruct-q4_K_M" >> .env

# Edit docker-compose.vllm.yml and uncomment the ollama service

# Start with Ollama service
docker compose -f docker-compose.yml -f docker-compose.vllm.yml up

# Pull your desired model (first time only)
docker exec ollama ollama pull llama3.2:3b-instruct-q4_K_M
```

### 4. No LLM (Transcription Only)
Run OpenTranscribe without AI summarization features.

**Setup:**
```bash
# Leave LLM_PROVIDER unset or empty
echo "LLM_PROVIDER=" >> .env

# Start normally
docker compose up
```

The application will work normally but summarization features will show "LLM unavailable" status.

## Environment Variable Reference

### Core LLM Settings
```bash
LLM_PROVIDER=openai|vllm|ollama|anthropic|custom
```

### OpenAI Configuration
```bash
OPENAI_API_KEY=sk-your-key
OPENAI_MODEL_NAME=gpt-4o-mini
OPENAI_BASE_URL=  # Optional, for compatible APIs
```

### Anthropic Claude Configuration
```bash
ANTHROPIC_API_KEY=sk-ant-your-key
ANTHROPIC_MODEL_NAME=claude-3-haiku-20240307
```

### OpenRouter Configuration (Supports Many Models)
```bash
LLM_PROVIDER=custom
OPENROUTER_API_KEY=sk-or-your-key
OPENROUTER_MODEL_NAME=anthropic/claude-3-haiku
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

### vLLM Configuration
```bash
VLLM_BASE_URL=http://localhost:8012/v1
VLLM_MODEL_NAME=gpt-oss-20b
CUDA_VISIBLE_DEVICES=0,1,2  # GPU selection
```

### Ollama Configuration
```bash
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL_NAME=llama3.2:3b-instruct-q4_K_M
OLLAMA_WEBAPI_PORT=11434
```

## Performance and Cost Considerations

| Option | Cost | Latency | Privacy | Setup Difficulty |
|--------|------|---------|---------|-----------------|
| Cloud (OpenAI) | $$$ | Low | Shared | Easy |
| Cloud (OpenRouter) | $$ | Low | Shared | Easy |
| vLLM Local | Free* | Medium | Full | Hard |
| Ollama Local | Free* | High | Full | Medium |

*Hardware costs and electricity not included

## GPU Requirements

### vLLM Models
- **gpt-oss-20b**: 16GB VRAM minimum (RTX 4090, A6000)
- **gpt-oss-120b**: 96GB VRAM (2x A100 80GB)

### Ollama Models  
- **3B models**: 8GB VRAM (RTX 4060 Ti, RTX 3080)
- **7B models**: 12GB VRAM (RTX 4070 Ti, RTX 3080 Ti)
- **13B models**: 16GB VRAM (RTX 4090, A6000)

## Troubleshooting

### LLM Service Not Available
1. Check if the service is running: `docker compose ps`
2. Verify environment variables in `.env`
3. Check API keys are valid
4. For local models, ensure GPU drivers are installed

### Context Length Limitations
OpenTranscribe automatically handles models with different context windows using intelligent section-by-section processing:

- **Automatic Detection**: Queries model endpoints to get actual context limits
- **Smart Chunking**: Long transcripts are split into sections at natural boundaries (speaker changes, topics)
- **Section Processing**: Each section is individually summarized with full context awareness
- **Intelligent Stitching**: Section summaries are combined into comprehensive BLUF format final summary
- **No Content Loss**: Entire transcript is processed regardless of model context limits

**Processing Behavior by Model Type:**
- **Small Models (4K tokens)**: Long transcripts automatically split into multiple sections
- **Medium Models (8K-32K tokens)**: Most conversations fit in 1-3 sections  
- **Large Models (128K+ tokens)**: Most transcripts processed as single section
- **All Models**: Complete transcript content is always processed and summarized

**Benefits of Section-by-Section Processing:**
- ✅ **No transcript length limits** - process hours of content with any model
- ✅ **Higher quality summaries** - each section gets full model attention
- ✅ **Better cost efficiency** - smaller models can handle enterprise-length content
- ✅ **Automatic optimization** - uses single-pass for short content, multi-pass for long content

### Out of Memory Errors
1. Reduce model size (use smaller Ollama models)
2. Adjust GPU memory utilization in compose file
3. Enable model quantization
4. Use cloud providers instead

### Slow Performance
1. Use cloud providers for faster inference
2. Ensure NVIDIA drivers and CUDA are properly installed
3. Check GPU utilization: `nvidia-smi`
4. Consider using smaller local models

## Migration Between Providers

You can switch between providers by:
1. Updating your `.env` file
2. Restarting the services: `docker compose restart backend celery-worker`

No data migration is required - existing summaries remain unchanged.