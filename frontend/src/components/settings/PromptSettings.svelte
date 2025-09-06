<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { PromptsApi, type SummaryPrompt, type ActivePromptResponse, type SummaryPromptCreate, type SummaryPromptUpdate } from '../../lib/api/prompts';
  import ConfirmationModal from '../ConfirmationModal.svelte';

  export let onSettingsChange: (() => void) | null = null;

  // State variables
  let loading = false;
  let saving = false;
  let error = '';
  let success = '';
  
  let allPrompts: SummaryPrompt[] = [];
  let activePrompt: SummaryPrompt | null = null;
  let selectedPromptId: number | null = null;
  
  // Create/Edit prompt form
  let showCreateForm = false;
  let editingPrompt: SummaryPrompt | null = null;
  
  // View prompt modal
  let showViewModal = false;
  let viewingPrompt: SummaryPrompt | null = null;
  
  // Delete confirmation modal
  let showDeleteModal = false;
  let promptToDelete: SummaryPrompt | null = null;
  
  // Unsaved changes confirmation modal
  let showUnsavedChangesModal = false;
  let pendingCloseAction: (() => void) | null = null;
  
  // Form dirty state tracking
  let originalFormData = {};
  let isDirty = false;
  
  let formData = {
    name: '',
    description: '',
    prompt_text: '',
    content_type: 'general'
  };
  
  const contentTypes = [
    { value: 'general', label: 'General' },
    { value: 'meeting', label: 'Meeting' },
    { value: 'interview', label: 'Interview' },
    { value: 'podcast', label: 'Podcast' },
    { value: 'documentary', label: 'Documentary' },
    { value: 'speaker_identification', label: 'Speaker Identification' }
  ];

  onMount(async () => {
    await loadData();
  });
  
  onDestroy(() => {
    // Cleanup: ensure body scrolling is restored and event listeners removed
    document.body.style.overflow = '';
    if (keydownHandler) {
      document.removeEventListener('keydown', keydownHandler);
      keydownHandler = null;
    }
  });

  async function loadData() {
    loading = true;
    error = '';
    
    try {
      // Load all prompts
      const promptsResponse = await PromptsApi.getPrompts({
        include_system: true,
        include_user: true,
        limit: 100
      });
      allPrompts = promptsResponse.prompts || [];

      // Load active prompt
      const activeResponse = await PromptsApi.getActivePrompt();
      activePrompt = activeResponse.active_prompt;
      selectedPromptId = activeResponse.active_prompt_id;
      
      // Auto-select universal prompt if no prompt is selected
      if (!selectedPromptId && allPrompts.length > 0) {
        const universalPrompt = allPrompts.find(p => 
          p.is_system_default && 
          (p.name.toLowerCase().includes('universal') || p.name.toLowerCase().includes('general'))
        );
        
        if (universalPrompt) {
          await setActivePrompt(universalPrompt.id);
        } else {
          // Fallback to first system prompt if no universal found
          const firstSystemPrompt = allPrompts.find(p => p.is_system_default);
          if (firstSystemPrompt) {
            await setActivePrompt(firstSystemPrompt.id);
          }
        }
      }
    } catch (err: any) {
      console.error('Error loading prompts:', err);
      error = err.response?.data?.detail || 'Failed to load prompts';
    } finally {
      loading = false;
    }
  }

  async function setActivePrompt(promptId: number) {
    saving = true;
    error = '';
    
    try {
      await PromptsApi.setActivePrompt({
        prompt_id: promptId
      });
      
      selectedPromptId = promptId;
      activePrompt = allPrompts.find(p => p.id === promptId) || null;
      success = 'Active prompt updated successfully';
      
      if (onSettingsChange) {
        onSettingsChange();
      }
    } catch (err: any) {
      console.error('Error setting active prompt:', err);
      error = err.response?.data?.detail || 'Failed to set active prompt';
    } finally {
      saving = false;
    }
  }

  function openCreateForm() {
    showCreateForm = true;
    editingPrompt = null;
    formData = {
      name: '',
      description: '',
      prompt_text: '',
      content_type: 'general'
    };
    originalFormData = { ...formData };
  }

  function openEditForm(prompt: SummaryPrompt) {
    if (prompt.is_system_default) {
      error = 'System prompts cannot be edited';
      return;
    }
    
    showCreateForm = true;
    editingPrompt = prompt;
    formData = {
      name: prompt.name,
      description: prompt.description || '',
      prompt_text: prompt.prompt_text,
      content_type: prompt.content_type || 'general'
    };
    originalFormData = { ...formData };
  }

  function closeForm(force: boolean = false) {
    if (!force && isDirty) {
      // Show professional confirmation modal instead of browser alert
      pendingCloseAction = () => executeCloseForm();
      showUnsavedChangesModal = true;
      return;
    }
    
    executeCloseForm();
  }

  function executeCloseForm() {
    showCreateForm = false;
    editingPrompt = null;
    formData = {
      name: '',
      description: '',
      prompt_text: '',
      content_type: 'general'
    };
    originalFormData = { ...formData };
    error = '';
    success = '';
  }

  function handleUnsavedChangesConfirm() {
    if (pendingCloseAction) {
      pendingCloseAction();
      pendingCloseAction = null;
    }
    showUnsavedChangesModal = false;
  }

  function handleUnsavedChangesCancel() {
    pendingCloseAction = null;
    showUnsavedChangesModal = false;
  }

  async function savePrompt() {
    if (!formData.name.trim() || !formData.prompt_text.trim()) {
      error = 'Name and prompt text are required';
      return;
    }

    saving = true;
    error = '';
    success = '';

    try {
      if (editingPrompt) {
        // Update existing prompt
        const updatedPrompt = await PromptsApi.updatePrompt(editingPrompt.id, formData);
        
        // Update in the list
        const index = allPrompts.findIndex(p => p.id === updatedPrompt.id);
        if (index >= 0) {
          allPrompts[index] = updatedPrompt;
          allPrompts = [...allPrompts]; // Trigger reactivity
        }
        
        success = 'Prompt updated successfully';
      } else {
        // Create new prompt
        const newPrompt = await PromptsApi.createPrompt(formData);
        
        allPrompts = [...allPrompts, newPrompt];
        success = 'Prompt created successfully';
      }
      
      // Force close after successful save (no dirty check needed)
      closeForm(true);
      
      if (onSettingsChange) {
        onSettingsChange();
      }
    } catch (err: any) {
      console.error('Error saving prompt:', err);
      error = err.response?.data?.detail || 'Failed to save prompt';
    } finally {
      saving = false;
    }
  }

  function confirmDeletePrompt(prompt: SummaryPrompt) {
    if (prompt.is_system_default) {
      error = 'System prompts cannot be deleted';
      return;
    }
    
    promptToDelete = prompt;
    showDeleteModal = true;
  }

  async function deletePrompt() {
    if (!promptToDelete) return;

    saving = true;
    error = '';
    
    try {
      await PromptsApi.deletePrompt(promptToDelete.id);
      
      // Remove from list
      allPrompts = allPrompts.filter(p => p.id !== promptToDelete.id);
      
      // If this was the active prompt, clear selection
      if (selectedPromptId === promptToDelete.id) {
        selectedPromptId = null;
        activePrompt = null;
      }
      
      success = 'Prompt deleted successfully';
      
      if (onSettingsChange) {
        onSettingsChange();
      }
    } catch (err: any) {
      console.error('Error deleting prompt:', err);
      error = err.response?.data?.detail || 'Failed to delete prompt';
    } finally {
      saving = false;
      promptToDelete = null;
      showDeleteModal = false;
    }
  }

  // Separate prompts by type - exclude speaker_identification from UI
  $: systemPrompts = allPrompts.filter(p => p.is_system_default && p.content_type !== 'speaker_identification');
  $: userPrompts = allPrompts.filter(p => !p.is_system_default);
  
  function viewPrompt(prompt: SummaryPrompt) {
    viewingPrompt = prompt;
    showViewModal = true;
  }
  
  function closeViewModal() {
    showViewModal = false;
    viewingPrompt = null;
  }
  
  $: isFormValid = !!(formData.name && formData.name.trim() && formData.prompt_text && formData.prompt_text.trim());
  
  // Track form changes for dirty state
  $: isDirty = JSON.stringify(formData) !== JSON.stringify(originalFormData);
  
  // Prevent body scrolling when modals are open
  $: {
    if (showCreateForm || showViewModal || showUnsavedChangesModal) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
  }
  
  // Handle keyboard shortcuts for modals
  let keydownHandler: ((event: KeyboardEvent) => void) | null = null;
  
  $: {
    // Clean up previous listener if exists
    if (keydownHandler) {
      document.removeEventListener('keydown', keydownHandler);
      keydownHandler = null;
    }
    
    // Add new listener if modal is open
    if (showCreateForm || showViewModal || showUnsavedChangesModal) {
      keydownHandler = (event: KeyboardEvent) => {
        if (event.key === 'Escape') {
          if (showUnsavedChangesModal) {
            handleUnsavedChangesCancel();
          } else if (showCreateForm) {
            closeForm();
          } else if (showViewModal) {
            closeViewModal();
          }
        }
      };
      document.addEventListener('keydown', keydownHandler);
    }
  }
  
</script>

<div class="prompt-settings">
  <div class="settings-header">
    <h3>AI Summarization Prompts</h3>
    <p>Manage your AI summarization prompts to customize how transcripts are analyzed and summarized.</p>
  </div>

  {#if success}
    <div class="message success">
      {success}
    </div>
  {/if}

  {#if error}
    <div class="message error">
      {error}
    </div>
  {/if}

  {#if loading}
    <div class="loading">Loading prompts...</div>
  {:else}
    <!-- Active Prompt Section -->
    <div class="active-prompt-section">
      <h4>Currently Active Prompt</h4>
      {#if activePrompt}
        <div class="active-prompt-card">
          <div class="prompt-info">
            <div class="prompt-name">{activePrompt.name}</div>
            <div class="prompt-meta">
              {activePrompt.is_system_default ? 'System' : 'Custom'} • 
              {activePrompt.content_type || 'General'}
            </div>
            {#if activePrompt.description}
              <div class="prompt-description">{activePrompt.description}</div>
            {/if}
          </div>
        </div>
      {:else}
        <div class="no-active-prompt">
          No active prompt selected. Please select a prompt below.
        </div>
      {/if}
    </div>

    <!-- System Prompts -->
    {#if systemPrompts.length > 0}
      <div class="prompt-section">
        <h4>System Prompts</h4>
        <div class="prompts-grid">
          {#each systemPrompts as prompt}
            <div class="prompt-card" class:active={selectedPromptId === prompt.id}>
              <div class="prompt-info">
                <div class="prompt-name">{prompt.name}</div>
                <div class="prompt-meta">
                  {prompt.content_type || 'General'}
                </div>
                {#if prompt.description}
                  <div class="prompt-description">{prompt.description}</div>
                {/if}
              </div>
              <div class="prompt-actions">
                <button
                  class="action-button secondary"
                  on:click={() => viewPrompt(prompt)}
                  title="View prompt text"
                >
                  View Prompt
                </button>
                {#if selectedPromptId !== prompt.id}
                  <button
                    class="action-button primary"
                    on:click={() => setActivePrompt(prompt.id)}
                    disabled={saving}
                  >
                    Use This Prompt
                  </button>
                {:else}
                  <div class="active-badge">Active</div>
                {/if}
              </div>
            </div>
          {/each}
        </div>
      </div>
    {/if}

    <!-- Custom Prompts -->
    <div class="prompt-section">
      <div class="section-header">
        <h4>Your Custom Prompts</h4>
        <button
          class="action-button primary"
          on:click={openCreateForm}
          disabled={saving}
        >
          Create New Prompt
        </button>
      </div>

      {#if userPrompts.length > 0}
        <div class="prompts-grid">
          {#each userPrompts as prompt}
            <div class="prompt-card" class:active={selectedPromptId === prompt.id}>
              <div class="prompt-info">
                <div class="prompt-name">{prompt.name}</div>
                <div class="prompt-meta">
                  {prompt.content_type || 'General'}
                </div>
                {#if prompt.description}
                  <div class="prompt-description">{prompt.description}</div>
                {/if}
              </div>
              <div class="prompt-actions">
                <button
                  class="action-button secondary"
                  on:click={() => viewPrompt(prompt)}
                  title="View prompt text"
                >
                  View Prompt
                </button>
                {#if selectedPromptId !== prompt.id}
                  <button
                    class="action-button primary"
                    on:click={() => setActivePrompt(prompt.id)}
                    disabled={saving}
                  >
                    Use This Prompt
                  </button>
                {:else}
                  <div class="active-badge">Active</div>
                {/if}
                <button
                  class="action-button secondary"
                  on:click={() => openEditForm(prompt)}
                  disabled={saving}
                >
                  Edit
                </button>
                <button
                  class="action-button danger"
                  on:click={() => confirmDeletePrompt(prompt)}
                  disabled={saving}
                >
                  Delete
                </button>
              </div>
            </div>
          {/each}
        </div>
      {:else}
        <div class="no-prompts">
          You don't have any custom prompts yet. Create one to customize your AI summarization.
        </div>
      {/if}
    </div>
  {/if}

  <!-- Create/Edit Form Modal -->
  {#if showCreateForm}
    <div class="modal-overlay">
      <div class="modal-content" on:click|stopPropagation>
        <div class="modal-header">
          <h3>
            {editingPrompt ? 'Edit Prompt' : 'Create New Prompt'}
            {#if isDirty}
              <span class="unsaved-indicator" title="You have unsaved changes">•</span>
            {/if}
          </h3>
          <button class="close-button" on:click={() => closeForm()} title={isDirty ? 'Close (unsaved changes will be lost)' : 'Close'}>×</button>
        </div>
        
        <form on:submit|preventDefault={savePrompt} class="prompt-form">
          <div class="form-group">
            <label for="name">Prompt Name *</label>
            <input
              type="text"
              id="name"
              bind:value={formData.name}
              disabled={saving}
              class="form-control"
              placeholder="e.g., Meeting Summary Pro"
              required
            />
          </div>

          <div class="form-group">
            <label for="content_type">Content Type</label>
            <select
              id="content_type"
              bind:value={formData.content_type}
              disabled={saving}
              class="form-control"
            >
              {#each contentTypes as type}
                <option value={type.value}>{type.label}</option>
              {/each}
            </select>
          </div>

          <div class="form-group">
            <label for="description">Description</label>
            <input
              type="text"
              id="description"
              bind:value={formData.description}
              disabled={saving}
              class="form-control"
              placeholder="Brief description of this prompt's purpose"
            />
          </div>

          <div class="form-group">
            <label for="prompt_text">Prompt Text *</label>
            <textarea
              id="prompt_text"
              bind:value={formData.prompt_text}
              disabled={saving}
              class="form-control textarea"
              rows="8"
              placeholder="Enter your custom prompt text here. Use &#123;transcript&#125; and &#123;speaker_data&#125; placeholders where needed."
              required
            ></textarea>
            <small class="form-text">
              Use <code>&#123;transcript&#125;</code> and <code>&#123;speaker_data&#125;</code> as placeholders for the actual transcript and speaker information.
            </small>
            <div class="llm-hint">
              <strong>
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="tip-icon">
                  <circle cx="12" cy="12" r="5"></circle>
                  <line x1="12" y1="1" x2="12" y2="3"></line>
                  <line x1="12" y1="21" x2="12" y2="23"></line>
                  <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
                  <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
                  <line x1="1" y1="12" x2="3" y2="12"></line>
                  <line x1="21" y1="12" x2="23" y2="12"></line>
                  <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
                  <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
                </svg>
                Tip:
              </strong> Consider using any LLM to help craft effective prompts for your needs.
            </div>
          </div>

          <div class="modal-actions">
            <button
              type="button"
              class="action-button secondary"
              on:click={() => closeForm()}
              disabled={saving}
            >
              Cancel
            </button>
            <button
              type="submit"
              class="action-button primary"
              disabled={saving || !isFormValid}
            >
              {#if saving}
                <div class="spinner"></div>
                Saving...
              {:else}
                {editingPrompt ? 'Update Prompt' : 'Create Prompt'}
              {/if}
            </button>
          </div>
        </form>
      </div>
    </div>
  {/if}

  <!-- View Prompt Modal -->
  {#if showViewModal && viewingPrompt}
    <div class="modal-overlay" on:click={closeViewModal}>
      <div class="modal-content view-modal" on:click|stopPropagation>
        <div class="modal-header">
          <h3>View Prompt: {viewingPrompt.name}</h3>
          <button class="close-button" on:click={closeViewModal}>×</button>
        </div>
        <div class="modal-body">
          <div class="prompt-details">
            <div class="detail-row">
              <strong>Type:</strong> {viewingPrompt.content_type || 'General'}
            </div>
            {#if viewingPrompt.description}
              <div class="detail-row">
                <strong>Description:</strong> {viewingPrompt.description}
              </div>
            {/if}
            <div class="detail-row">
              <strong>System Prompt:</strong> {viewingPrompt.is_system_default ? 'Yes' : 'No'}
            </div>
          </div>
          <div class="prompt-text-container">
            <strong>Prompt Text:</strong>
            <div class="prompt-text-display">{viewingPrompt.prompt_text}</div>
          </div>
        </div>
      </div>
    </div>
  {/if}

  <!-- Delete Confirmation Modal -->
  <ConfirmationModal
    bind:isOpen={showDeleteModal}
    title="Delete Prompt"
    message={promptToDelete ? `Are you sure you want to delete the prompt "${promptToDelete.name}"? This action cannot be undone.` : ''}
    confirmText="Delete"
    cancelText="Cancel"
    confirmButtonClass="modal-delete-button"
    cancelButtonClass="modal-cancel-button"
    on:confirm={deletePrompt}
    on:cancel={() => { promptToDelete = null; showDeleteModal = false; }}
    on:close={() => { promptToDelete = null; showDeleteModal = false; }}
  />

  <!-- Unsaved Changes Confirmation Modal -->
  <ConfirmationModal
    bind:isOpen={showUnsavedChangesModal}
    title="Unsaved Changes"
    message="You have unsaved changes that will be lost. Are you sure you want to continue without saving?"
    confirmText="Discard Changes"
    cancelText="Keep Editing"
    confirmButtonClass="modal-warning-button"
    cancelButtonClass="modal-primary-button"
    on:confirm={handleUnsavedChangesConfirm}
    on:cancel={handleUnsavedChangesCancel}
    on:close={handleUnsavedChangesCancel}
  />
</div>

<style>
  .prompt-settings {
    max-width: 800px;
  }

  .settings-header h3 {
    margin: 0 0 0.5rem 0;
    color: var(--text-color);
  }

  .settings-header p {
    margin: 0 0 1.5rem 0;
    color: var(--text-light);
    font-size: 0.9rem;
  }

  .message {
    padding: 0.75rem 1rem;
    border-radius: 4px;
    margin-bottom: 1rem;
    font-size: 0.9rem;
  }

  .message.success {
    background-color: rgba(16, 185, 129, 0.1);
    color: var(--success-color);
    border: 1px solid rgba(16, 185, 129, 0.2);
  }

  .message.error {
    background-color: rgba(239, 68, 68, 0.1);
    color: var(--error-color);
    border: 1px solid rgba(239, 68, 68, 0.2);
  }

  .loading {
    text-align: center;
    padding: 2rem;
    color: var(--text-light);
  }

  .active-prompt-section,
  .prompt-section {
    margin-bottom: 2rem;
  }

  .active-prompt-section h4,
  .prompt-section h4 {
    margin: 0 0 1rem 0;
    color: var(--text-color);
    font-size: 1.1rem;
  }

  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
  }

  .active-prompt-card,
  .prompt-card {
    background-color: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 1rem;
  }

  .prompt-card {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 1rem;
  }

  .prompt-card.active {
    border-color: var(--primary-color);
    background-color: rgba(59, 130, 246, 0.05);
  }

  .prompts-grid {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .prompt-info {
    flex: 1;
  }

  .prompt-name {
    font-weight: 500;
    font-size: 1rem;
    color: var(--text-color);
    margin-bottom: 0.25rem;
  }

  .prompt-meta {
    font-size: 0.8rem;
    color: var(--text-light);
    margin-bottom: 0.5rem;
  }

  .prompt-description {
    font-size: 0.9rem;
    color: var(--text-color);
    line-height: 1.4;
  }


  .prompt-actions {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
    align-items: center;
  }

  .active-badge {
    padding: 0.25rem 0.75rem;
    background-color: var(--success-color);
    color: white;
    border-radius: 12px;
    font-size: 0.8rem;
    font-weight: 500;
  }

  .action-button {
    padding: 0.5rem 1rem;
    border-radius: 4px;
    font-size: 0.8rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    border: 1px solid;
  }

  .action-button.primary {
    background-color: var(--primary-color);
    border-color: var(--primary-color);
    color: white;
  }

  .action-button.primary:hover:not(:disabled) {
    background-color: var(--primary-dark);
  }

  .action-button.secondary {
    background-color: transparent;
    border-color: var(--border-color);
    color: var(--text-color);
  }

  .action-button.secondary:hover:not(:disabled) {
    background-color: var(--primary-color);
    border-color: var(--primary-color);
    color: white;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }

  .action-button.secondary:active:not(:disabled) {
    transform: translateY(0);
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }

  .action-button.danger {
    background-color: transparent;
    border-color: var(--error-color);
    color: var(--error-color);
  }

  .action-button.danger:hover:not(:disabled) {
    background-color: var(--error-color);
    border-color: var(--error-color);
    color: white;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(239, 68, 68, 0.25);
  }

  .action-button.danger:active:not(:disabled) {
    transform: translateY(0);
    box-shadow: 0 2px 4px rgba(239, 68, 68, 0.2);
  }

  .action-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  /* Modal button styling to match app design */
  :global(.modal-delete-button) {
    background-color: #ef4444 !important;
    color: white !important;
    border: none !important;
    padding: 0.6rem 1.2rem !important;
    border-radius: 10px !important;
    font-size: 0.95rem !important;
    font-weight: 500 !important;
    cursor: pointer !important;
    transition: all 0.2s ease !important;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1) !important;
  }

  :global(.modal-delete-button:hover) {
    background-color: #dc2626 !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15) !important;
  }

  :global(.modal-delete-button:active) {
    transform: translateY(0) !important;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1) !important;
  }

  :global(.modal-delete-button:focus) {
    outline: 2px solid #fca5a5 !important;
    outline-offset: 2px !important;
  }

  :global(.modal-cancel-button) {
    background-color: var(--surface-color) !important;
    color: var(--text-color) !important;
    border: 1px solid var(--border-color) !important;
    padding: 0.6rem 1.2rem !important;
    border-radius: 10px !important;
    font-size: 0.95rem !important;
    font-weight: 500 !important;
    cursor: pointer !important;
    transition: all 0.2s ease !important;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1) !important;
  }

  :global(.modal-cancel-button:hover) {
    background-color: #3b82f6 !important;
    color: white !important;
    border-color: #3b82f6 !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25) !important;
  }

  :global(.modal-cancel-button:active) {
    transform: translateY(0) !important;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2) !important;
  }

  /* Warning button for unsaved changes */
  :global(.modal-warning-button) {
    background-color: #f59e0b !important;
    color: white !important;
    border: none !important;
    padding: 0.6rem 1.2rem !important;
    border-radius: 10px !important;
    font-size: 0.95rem !important;
    font-weight: 500 !important;
    cursor: pointer !important;
    transition: all 0.2s ease !important;
    box-shadow: 0 2px 4px rgba(245, 158, 11, 0.2) !important;
  }

  :global(.modal-warning-button:hover) {
    background-color: #d97706 !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 8px rgba(245, 158, 11, 0.25) !important;
  }

  :global(.modal-warning-button:active) {
    transform: translateY(0) !important;
    box-shadow: 0 2px 4px rgba(245, 158, 11, 0.2) !important;
  }

  :global(.modal-warning-button:focus) {
    outline: 2px solid #fcd34d !important;
    outline-offset: 2px !important;
  }

  /* Primary button for keeping editing */
  :global(.modal-primary-button) {
    background-color: #3b82f6 !important;
    color: white !important;
    border: none !important;
    padding: 0.6rem 1.2rem !important;
    border-radius: 10px !important;
    font-size: 0.95rem !important;
    font-weight: 500 !important;
    cursor: pointer !important;
    transition: all 0.2s ease !important;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2) !important;
  }

  :global(.modal-primary-button:hover) {
    background-color: #2563eb !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25) !important;
  }

  :global(.modal-primary-button:active) {
    transform: translateY(0) !important;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2) !important;
  }

  :global(.modal-primary-button:focus) {
    outline: 2px solid #93c5fd !important;
    outline-offset: 2px !important;
  }

  .no-active-prompt,
  .no-prompts {
    text-align: center;
    padding: 2rem;
    color: var(--text-light);
    background-color: var(--surface-color);
    border: 1px dashed var(--border-color);
    border-radius: 8px;
  }

  /* Modal styles */
  .modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    padding: 1rem;
  }

  .modal-content {
    background-color: var(--background-color);
    border-radius: 8px;
    max-width: 600px;
    width: 100%;
    max-height: 90vh;
    overflow-y: auto;
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.3);
  }

  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1.5rem 1.5rem 1rem 1.5rem;
    border-bottom: 1px solid var(--border-color);
  }

  .modal-header h3 {
    margin: 0;
    color: var(--text-color);
  }

  .close-button {
    background: none;
    border: none;
    font-size: 1.5rem;
    cursor: pointer;
    color: var(--text-light);
    padding: 0;
    width: 30px;
    height: 30px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .close-button:hover {
    color: var(--text-color);
  }

  .prompt-form {
    padding: 1.5rem;
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
  }

  .form-group {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  label {
    font-weight: 500;
    font-size: 0.9rem;
    color: var(--text-color);
  }

  .form-control {
    padding: 0.75rem;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    font-size: 0.9rem;
    background-color: var(--background-color);
    color: var(--text-color);
    transition: border-color 0.2s ease;
  }

  .form-control.textarea {
    resize: vertical;
    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
    font-size: 0.8rem;
    line-height: 1.5;
  }

  .form-control:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.1);
  }

  .form-control:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .form-text {
    font-size: 0.8rem;
    color: var(--text-light);
  }

  .form-text code {
    background-color: var(--surface-color);
    padding: 0.125rem 0.25rem;
    border-radius: 2px;
    font-family: monospace;
  }

  .modal-actions {
    display: flex;
    gap: 1rem;
    justify-content: flex-end;
    padding-top: 1rem;
    border-top: 1px solid var(--border-color);
  }

  .spinner {
    width: 16px;
    height: 16px;
    border: 2px solid rgba(255, 255, 255, 0.3);
    border-top: 2px solid currentColor;
    border-radius: 50%;
    animation: spin 1s linear infinite;
    margin-right: 0.5rem;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  @media (max-width: 768px) {
    .section-header {
      flex-direction: column;
      align-items: stretch;
      gap: 1rem;
    }

    .prompt-card {
      flex-direction: column;
      gap: 1rem;
    }

    .prompt-actions {
      justify-content: flex-start;
    }

    .modal-content {
      margin: 0.5rem;
      max-height: 95vh;
    }

    .modal-actions {
      flex-direction: column;
    }
  }

  /* LLM Hint Styling */
  .llm-hint {
    margin-top: 0.75rem;
    padding: 0.75rem;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    border-radius: 6px;
    font-size: 0.8rem;
    line-height: 1.3;
  }

  .llm-hint strong {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.25rem;
  }
  
  .tip-icon {
    flex-shrink: 0;
  }

  /* View Modal Styling */
  .view-modal {
    max-width: 700px;
    max-height: 80vh;
  }

  .prompt-details {
    margin-bottom: 1.5rem;
  }

  .detail-row {
    margin-bottom: 0.75rem;
    font-size: 0.9rem;
  }

  .detail-row strong {
    color: var(--primary-color, #3b82f6);
    margin-right: 0.5rem;
  }

  .prompt-text-container {
    margin-top: 1.5rem;
  }

  .prompt-text-container strong {
    display: block;
    margin-bottom: 0.75rem;
    color: var(--primary-color, #3b82f6);
  }

  .prompt-text-display {
    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
    font-size: 0.9rem;
    line-height: 1.6;
    color: var(--text-color);
    white-space: pre-wrap;
    word-wrap: break-word;
    background-color: var(--surface-color);
    padding: 1rem;
    border-radius: 6px;
    border: 1px solid var(--border-color);
    max-height: 400px;
    overflow-y: auto;
  }

  /* Unsaved changes indicator */
  .unsaved-indicator {
    color: #f59e0b;
    font-size: 1.2em;
    margin-left: 0.5rem;
    animation: pulse 2s infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }

  /* Enhanced close button with warning state */
  .close-button:hover {
    background-color: var(--danger-color, #ef4444);
    color: white;
  }
</style>