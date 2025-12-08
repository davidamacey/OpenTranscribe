<objective>
Implement auto-population of available models for OpenAI-compatible LLM providers in the settings UI.

Currently, Ollama has model discovery via its `/api/tags` endpoint. This feature extends the same pattern to OpenAI-compatible providers (OpenAI, vLLM, OpenRouter) using the standard `/v1/models` endpoint.

This addresses TO-DOS.md Feature #4: "Auto-populate OpenAI models in LLM settings"
</objective>

<context>
Read CLAUDE.md for project conventions.

**Tech Stack:**
- Backend: FastAPI (Python)
- Frontend: Svelte/TypeScript
- API pattern: REST with typed schemas

**Existing Implementation to Follow:**
The Ollama model discovery is already implemented and should be used as the reference pattern:

@backend/app/api/endpoints/llm_settings.py (lines 680-750) - `get_ollama_models()` endpoint
@frontend/src/lib/api/llmSettings.ts (lines 194-211) - `getOllamaModels()` API method
@frontend/src/components/settings/LLMConfigModal.svelte (lines 261-289, 444-512) - Ollama model discovery UI

**Key Points:**
- OpenAI-compatible APIs expose models at `GET /v1/models`
- Response format: `{ "data": [{ "id": "model-name", "created": timestamp, "owned_by": "owner" }, ...] }`
- Some providers require API key authentication for listing models
- vLLM uses same format but typically doesn't require auth
- OpenRouter uses same format with API key required
</context>

<requirements>
1. **Backend Endpoint** (`backend/app/api/endpoints/llm_settings.py`):
   - Add new endpoint: `GET /llm-settings/openai-compatible/models`
   - Parameters: `base_url` (required), `api_key` (optional)
   - Fetch from `{base_url}/models` (append /models to base URL)
   - Return format matching Ollama response structure for frontend consistency:
     ```python
     {
       "success": bool,
       "models": [{"name": str, "id": str, "owned_by": str, "created": int}],
       "total": int,
       "message": str
     }
     ```
   - Handle authentication headers when api_key provided
   - 10 second timeout like Ollama endpoint
   - Proper error handling for connection errors and non-200 responses

2. **Frontend API** (`frontend/src/lib/api/llmSettings.ts`):
   - Add new method: `getOpenAICompatibleModels(baseUrl: string, apiKey?: string)`
   - Return type matching existing `getOllamaModels` pattern

3. **Frontend UI** (`frontend/src/components/settings/LLMConfigModal.svelte`):
   - Add "Discover Models" button for providers: openai, vllm, openrouter
   - Reuse existing model selector UI pattern from Ollama implementation
   - Show button only when `base_url` is filled (for openai/vllm/openrouter)
   - For providers requiring API key (openai, openrouter), button should be disabled if no API key entered
   - vLLM typically doesn't need API key, so enable button with just base_url

4. **Provider-Specific Behavior:**
   - `openai`: Requires API key, default base_url is `https://api.openai.com/v1`
   - `vllm`: API key optional, base_url required
   - `openrouter`: Requires API key, default base_url is `https://openrouter.ai/api/v1`
</requirements>

<implementation>
Follow existing patterns closely:

1. Backend endpoint structure mirrors `get_ollama_models()`:
   - Use `aiohttp` for async HTTP requests
   - Same timeout and error handling pattern
   - Log errors with logger

2. Frontend API mirrors `getOllamaModels()`:
   - Same response structure for frontend consistency
   - Pass apiKey as optional query param or header

3. UI reuses existing state variables where possible:
   - Consider renaming `ollamaModels` -> `discoveredModels` for reuse
   - Or add parallel state: `openaiCompatibleModels`
   - `showModelSelector` can be reused
</implementation>

<output>
Modify these files (relative paths from project root):

- `backend/app/api/endpoints/llm_settings.py` - Add new endpoint
- `frontend/src/lib/api/llmSettings.ts` - Add API method
- `frontend/src/components/settings/LLMConfigModal.svelte` - Add UI for model discovery

Do NOT create new files - extend existing implementations.
</output>

<verification>
After implementing:

1. Start dev environment: `./opentr.sh start dev`
2. Navigate to Settings > LLM Provider
3. Create new configuration with OpenAI provider
4. Enter base_url and API key
5. Click "Discover Models" button
6. Verify model list populates
7. Select a model and verify it fills the model_name field
8. Test with vLLM (if available) without API key
9. Check browser console for errors
10. Check backend logs: `./opentr.sh logs backend`
</verification>

<success_criteria>
- "Discover Models" button appears for OpenAI, vLLM, and OpenRouter providers
- Button is disabled when required fields are missing (base_url, api_key for providers that need it)
- Clicking button fetches and displays available models in dropdown
- Selecting a model populates the model_name field
- Error messages display appropriately for connection failures
- Existing Ollama model discovery continues to work unchanged
</success_criteria>
