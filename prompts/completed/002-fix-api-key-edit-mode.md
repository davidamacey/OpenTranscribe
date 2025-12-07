<objective>
Fix the LLM Configuration modal to show the API Key field when editing an existing configuration.

Currently, when editing an LLM provider configuration, users cannot:
1. Enter a new API key (to update the existing one)
2. Use the "Discover Models" feature (which requires an API key for OpenAI/OpenRouter)
3. See any indication that an API key is already stored

This blocks users from testing model discovery on existing configurations.
</objective>

<context>
Read CLAUDE.md for project conventions.

Key files:
- `frontend/src/components/settings/LLMConfigModal.svelte` - The modal component (main file to modify)
- `frontend/src/lib/api/llmSettings.ts` - API types (already has `has_api_key: boolean` in UserLLMSettings)

Current behavior:
- Line 132: `api_key: '', // Never populate API key for security` - API key is never shown in edit mode
- Lines 624-667: API Key field only shown if provider `requires_api_key` is true
- Line 104: Form validation skips API key requirement when `editingConfig` exists
- The `editingConfig.has_api_key` property exists but is not used to show indicator

The backend already returns `has_api_key: boolean` for each configuration, indicating whether a key is stored.
</context>

<requirements>
1. **Show API Key field in edit mode** for providers that use API keys
   - Field should be optional in edit mode (empty = keep existing key)
   - Placeholder text should indicate: "Enter new API key (leave blank to keep current)"
   - This is already partially implemented (see line 635-636) but the field is hidden

2. **Show indicator when API key exists**
   - When `editingConfig?.has_api_key` is true, show a small indicator near the API Key label
   - Example: "API Key * (stored)" or a checkmark icon with tooltip "API key is configured"

3. **Enable "Discover Models" button in edit mode**
   - Currently disabled when `!formData.api_key` for providers requiring API key
   - In edit mode, if `editingConfig.has_api_key` is true AND no new key entered, the button should still be enabled
   - Backend should use stored key when no key provided in request (check if this already works)

4. **Fix the conditional rendering**
   - The API Key section (lines 623-667) uses `{#if getProviderDefaults(formData.provider)?.requires_api_key}`
   - This should also show for providers that optionally accept API keys when editing
   - Or at minimum, always show in edit mode for providers that can have API keys
</requirements>

<implementation>
Focus on `LLMConfigModal.svelte`:

1. Modify the API Key field visibility condition (around line 624):
   - Show if provider `requires_api_key` OR if editing and `editingConfig.has_api_key`

2. Add indicator for stored API key:
   - Near the "API Key *" label, add text or icon when `editingConfig?.has_api_key`

3. Update "Discover Models" button disabled condition (around line 532):
   - Current: `disabled={... || (getProviderDefaults(formData.provider)?.requires_api_key && !formData.api_key)}`
   - Should allow if editing with stored key: `... && !formData.api_key && !editingConfig?.has_api_key`

4. Verify backend handles missing api_key in requests for existing configs (it should use stored key)
</implementation>

<output>
Modify: `./frontend/src/components/settings/LLMConfigModal.svelte`
</output>

<verification>
After making changes:
1. Run `npm run check` in the frontend directory to verify no TypeScript errors
2. Test manually:
   - Create a new OpenAI/OpenRouter config with API key
   - Edit the config - API Key field should be visible with "(stored)" indicator
   - "Discover Models" button should be enabled without entering new key
   - Entering a new key should work to update the stored key
</verification>

<success_criteria>
- API Key field visible when editing configurations that have stored keys
- Clear indicator shows when an API key is already stored
- "Discover Models" button works in edit mode without re-entering API key
- No TypeScript errors
- Form validation still works correctly (new configs require key, edits don't)
</success_criteria>
