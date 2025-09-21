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
      
      // Check if we deleted the active prompt
      const wasActivePrompt = selectedPromptId === promptToDelete.id;
      
      // Check if we have any remaining user prompts after deletion
      const remainingUserPrompts = allPrompts.filter(p => !p.is_system_default);
      
      // If no user prompts remain, automatically activate Universal Content Analyzer (regardless of which prompt was active)
      if (remainingUserPrompts.length === 0) {
        try {
          // Load fresh active prompt data - backend will automatically fall back to Universal Content Analyzer
          const activeResponse = await PromptsApi.getActivePrompt();
          selectedPromptId = activeResponse.active_prompt_id;
          activePrompt = activeResponse.active_prompt;
          
          if (activePrompt && activePrompt.name) {
            success = `Prompt deleted successfully. ${activePrompt.name} is now active and will be used for all future summaries.`;
          } else {
            success = 'Prompt deleted successfully. Default system prompt is now active.';
          }
        } catch (activeErr: any) {
          console.error('Error getting fallback active prompt:', activeErr);
          selectedPromptId = null;
          activePrompt = null;
          success = 'Prompt deleted successfully';
        }
      } else if (wasActivePrompt) {
        // Just clear the selection if it was active but we still have user prompts
        selectedPromptId = null;
        activePrompt = null;
        success = 'Prompt deleted successfully';
      } else {
        success = 'Prompt deleted successfully';
      }
      
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
  
  // Function to prevent native tooltip flicker and position tooltip
  function removeTitle(event) {
    // Remove title attribute to prevent native tooltip
    if (event.target.hasAttribute('title')) {
      event.target.removeAttribute('title');
    }
    // Check parent elements too
    let element = event.target.closest('[title]');
    if (element) {
      element.removeAttribute('title');
    }
    
    // Position the tooltip dynamically
    const rect = event.target.closest('.info-tooltip').getBoundingClientRect();
    const tooltip = event.target.closest('.info-tooltip');
    
    tooltip.style.setProperty('--tooltip-left', `${rect.left + rect.width / 2}px`);
    tooltip.style.setProperty('--tooltip-top', `${rect.bottom}px`);
  }

  // Copy functionality - matches SummaryModal pattern
  let copyButtonText = 'Copy';
  
  function copyPromptText(text: string) {
    if (!text) return;
    
    navigator.clipboard.writeText(text).then(() => {
      copyButtonText = 'Copied!';
      setTimeout(() => {
        copyButtonText = 'Copy';
      }, 2000);
    }).catch(err => {
      console.error('Failed to copy:', err);
      // Fallback for browsers that don't support clipboard API
      try {
        const textArea = document.createElement('textarea');
        textArea.value = text;
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
        copyButtonText = 'Copied!';
        setTimeout(() => {
          copyButtonText = 'Copy';
        }, 2000);
      } catch (fallbackError) {
        console.error('Fallback copy failed:', fallbackError);
        copyButtonText = 'Copy failed';
        setTimeout(() => {
          copyButtonText = 'Copy';
        }, 2000);
      }
    });
  }
  
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

    <!-- System Prompts -->
    {#if systemPrompts.length > 0}
      <div class="saved-configs-section">
        <div class="section-header">
          <h4>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
            </svg>
            System Prompts
          </h4>
        </div>
        
        <div class="config-list">
          {#each systemPrompts as prompt}
            <div class="config-item" class:active={selectedPromptId === prompt.id}>
              <div class="config-info">
                <div class="config-name">
                  {prompt.name}
                  <span 
                    class="info-tooltip" 
                    data-tooltip="This system prompt cannot be deleted or edited. Create custom prompts to suit your specific needs."
                    on:mouseenter={removeTitle}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <circle cx="12" cy="12" r="10"/>
                      <path d="M12 16v-4"/>
                      <path d="M12 8h.01"/>
                    </svg>
                  </span>
                </div>
                <div class="config-provider">{prompt.content_type || 'General'}</div>
                {#if prompt.description}
                  <div class="config-url">{prompt.description}</div>
                {/if}
              </div>
              <div class="prompt-actions">
                {#if selectedPromptId === prompt.id}
                  <div class="config-status currently-active">
                    <div class="status-indicator">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="20,6 9,17 4,12"/>
                      </svg>
                    </div>
                    <span class="status-text">Currently Active</span>
                  </div>
                {:else}
                  <button
                    class="activate-button"
                    on:click={() => setActivePrompt(prompt.id)}
                    disabled={saving}
                    title="Make this prompt active"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <circle cx="12" cy="12" r="3"/>
                      <circle cx="12" cy="1" r="1"/>
                      <circle cx="12" cy="23" r="1"/>
                      <circle cx="4.22" cy="4.22" r="1"/>
                      <circle cx="19.78" cy="19.78" r="1"/>
                      <circle cx="1" cy="12" r="1"/>
                      <circle cx="23" cy="12" r="1"/>
                      <circle cx="4.22" cy="19.78" r="1"/>
                      <circle cx="19.78" cy="4.22" r="1"/>
                    </svg>
                    Activate
                  </button>
                {/if}
                
                <button 
                  class="view-button"
                  on:click={() => viewPrompt(prompt)}
                  title="View prompt text"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                    <circle cx="12" cy="12" r="3"/>
                  </svg>
                </button>
              </div>
            </div>
          {/each}
        </div>
      </div>
    {/if}

    <!-- Custom Prompts -->
    <div class="saved-configs-section">
      <div class="section-header">
        <h4>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14,2 14,8 20,8"/>
            <line x1="16" y1="13" x2="8" y2="13"/>
            <line x1="16" y1="17" x2="8" y2="17"/>
            <polyline points="10,9 9,9 8,9"/>
          </svg>
          Your Custom Prompts
        </h4>
        {#if userPrompts.length > 0}
          <button class="create-config-button" on:click={openCreateForm} title="Create new prompt">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="12" y1="5" x2="12" y2="19"/>
              <line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            Create Prompt
          </button>
        {/if}
      </div>

      {#if userPrompts.length > 0}
        <div class="config-list">
          {#each userPrompts as prompt}
            <div class="config-item" class:active={selectedPromptId === prompt.id}>
              <div class="config-info">
                <div class="config-name">{prompt.name}</div>
                <div class="config-provider">{prompt.content_type || 'General'}</div>
                {#if prompt.description}
                  <div class="config-url">{prompt.description}</div>
                {/if}
              </div>
              <div class="prompt-actions">
                {#if selectedPromptId === prompt.id}
                  <div class="config-status currently-active">
                    <div class="status-indicator">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="20,6 9,17 4,12"/>
                      </svg>
                    </div>
                    <span class="status-text">Currently Active</span>
                  </div>
                {:else}
                  <button
                    class="activate-button"
                    on:click={() => setActivePrompt(prompt.id)}
                    disabled={saving}
                    title="Make this prompt active"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <circle cx="12" cy="12" r="3"/>
                      <circle cx="12" cy="1" r="1"/>
                      <circle cx="12" cy="23" r="1"/>
                      <circle cx="4.22" cy="4.22" r="1"/>
                      <circle cx="19.78" cy="19.78" r="1"/>
                      <circle cx="1" cy="12" r="1"/>
                      <circle cx="23" cy="12" r="1"/>
                      <circle cx="4.22" cy="19.78" r="1"/>
                      <circle cx="19.78" cy="4.22" r="1"/>
                    </svg>
                    Activate
                  </button>
                {/if}
                
                <button 
                  class="view-button"
                  on:click={() => viewPrompt(prompt)}
                  title="View prompt text"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                    <circle cx="12" cy="12" r="3"/>
                  </svg>
                </button>
                <button 
                  class="edit-button"
                  on:click={() => openEditForm(prompt)}
                  disabled={saving}
                  title="Edit this prompt"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                    <path d="m18.5 2.5 a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                  </svg>
                </button>
                <button 
                  class="delete-config-button"
                  on:click={() => confirmDeletePrompt(prompt)}
                  disabled={saving}
                  title={`Delete prompt: ${prompt.name}`}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="3,6 5,6 21,6"/>
                    <path d="m19,6v14a2,2 0 0,1 -2,2H7a2,2 0 0,1 -2,-2V6m3,0V4a2,2 0 0,1 2,-2h4a2,2 0 0,1 2,2v2"/>
                    <line x1="10" y1="11" x2="10" y2="17"/>
                    <line x1="14" y1="11" x2="14" y2="17"/>
                  </svg>
                </button>
              </div>
            </div>
          {/each}
        </div>
      {:else}
        <div class="empty-state">
          <div class="empty-icon">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14,2 14,8 20,8"/>
              <line x1="16" y1="13" x2="8" y2="13"/>
              <line x1="16" y1="17" x2="8" y2="17"/>
              <polyline points="10,9 9,9 8,9"/>
            </svg>
          </div>
          <h4>No Custom Prompts</h4>
          <p>Create your first custom prompt to personalize your AI summarization experience.</p>
          <button class="create-first-config-btn" on:click={openCreateForm}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="12" y1="5" x2="12" y2="19"/>
              <line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            Create First Prompt
          </button>
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
            <div class="textarea-header">
              <label for="prompt_text">Prompt Text *</label>
              {#if formData.prompt_text.trim()}
                <button
                  type="button"
                  class="copy-button-header"
                  class:copied={copyButtonText === 'Copied!'}
                  on:click={() => copyPromptText(formData.prompt_text)}
                  aria-label="Copy prompt text"
                  title={copyButtonText === 'Copied!' ? 'Prompt text copied to clipboard!' : 'Copy prompt text'}
                >
                  {#if copyButtonText === 'Copied!'}
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                      <path d="M10.97 4.97a.75.75 0 0 1 1.07 1.05l-3.99 4.99a.75.75 0 0 1-1.08.02L4.324 8.384a.75.75 0 1 1 1.06-1.06l2.094 2.093 3.473-4.425a.267.267 0 0 1 .02-.022z"/>
                    </svg>
                    Copied!
                  {:else}
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                      <path d="M4 1.5H3a2 2 0 0 0-2 2V14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V3.5a2 2 0 0 0-2-2h-1v1h1a1 1 0 0 1 1 1V14a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1h1v-1z"/>
                      <path d="M9.5 1a.5.5 0 0 1 .5.5v1a.5.5 0 0 1-.5.5h-3a.5.5 0 0 1-.5-.5v-1a.5.5 0 0 1 .5-.5h3zm-3-1A1.5 1.5 0 0 0 5 1.5v1A1.5 1.5 0 0 0 6.5 4h3A1.5 1.5 0 0 0 11 2.5v-1A1.5 1.5 0 0 0 9.5 0h-3z"/>
                    </svg>
                    Copy
                  {/if}
                </button>
              {/if}
            </div>
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
            <div class="prompt-text-header">
              <strong>Prompt Text:</strong>
              <button
                type="button"
                class="copy-button-header"
                class:copied={copyButtonText === 'Copied!'}
                on:click={() => copyPromptText(viewingPrompt.prompt_text)}
                aria-label="Copy prompt text"
                title={copyButtonText === 'Copied!' ? 'Prompt text copied to clipboard!' : 'Copy prompt text'}
              >
                {#if copyButtonText === 'Copied!'}
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M10.97 4.97a.75.75 0 0 1 1.07 1.05l-3.99 4.99a.75.75 0 0 1-1.08.02L4.324 8.384a.75.75 0 1 1 1.06-1.06l2.094 2.093 3.473-4.425a.267.267 0 0 1 .02-.022z"/>
                  </svg>
                  Copied!
                {:else}
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M4 1.5H3a2 2 0 0 0-2 2V14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V3.5a2 2 0 0 0-2-2h-1v1h1a1 1 0 0 1 1 1V14a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1h1v-1z"/>
                    <path d="M9.5 1a.5.5 0 0 1 .5.5v1a.5.5 0 0 1-.5.5h-3a.5.5 0 0 1-.5-.5v-1a.5.5 0 0 1 .5-.5h3zm-3-1A1.5 1.5 0 0 0 5 1.5v1A1.5 1.5 0 0 0 6.5 4h3A1.5 1.5 0 0 0 11 2.5v-1A1.5 1.5 0 0 0 9.5 0h-3z"/>
                  </svg>
                  Copy
                {/if}
              </button>
            </div>
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
    padding: 0.6rem 1.2rem;
    border-radius: 10px;
    font-size: 0.95rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    border: 1px solid;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
  }

  .action-button.primary {
    background-color: #3b82f6;
    border-color: #3b82f6;
    color: white;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }

  .action-button.primary:hover:not(:disabled) {
    background-color: #2563eb;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }
  
  .action-button.primary:active:not(:disabled) {
    transform: translateY(0);
  }

  .action-button.secondary {
    background-color: var(--surface-color);
    border-color: var(--border-color);
    color: var(--text-color);
  }

  .action-button.secondary:hover:not(:disabled) {
    background-color: #3b82f6;
    border-color: #3b82f6;
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

  /* New button styles to match LLM provider page */
  .create-config-button {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: #3b82f6;
    color: white;
    border: none;
    padding: 0.6rem 1.2rem;
    border-radius: 10px;
    cursor: pointer;
    font-size: 0.95rem;
    font-weight: 500;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }

  .create-config-button:hover {
    background: #2563eb;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }
  
  .create-config-button:active {
    transform: translateY(0);
  }

  .config-status {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.375rem 0.75rem;
    border-radius: 4px;
    font-size: 0.8rem;
    font-weight: 500;
    width: fit-content;
  }

  .config-status.currently-active {
    background-color: var(--success-bg);
    color: var(--success-color);
    border: 1px solid var(--success-border);
  }

  .status-indicator {
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .activate-button, .view-button, .edit-button, .delete-config-button {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.5rem 0.75rem;
    border-radius: 4px;
    font-size: 0.8rem;
    cursor: pointer;
    transition: all 0.2s ease;
    border: 1px solid;
    height: 32px;
    box-sizing: border-box;
  }

  .activate-button {
    background-color: var(--success-color);
    border-color: var(--success-color);
    color: white;
    padding: 0.5rem 0.5rem;
  }

  .activate-button:hover:not(:disabled) {
    background-color: #059669;
    border-color: #059669;
  }

  .view-button {
    background-color: transparent;
    border-color: #3b82f6;
    color: #3b82f6;
  }

  .view-button:hover:not(:disabled) {
    background-color: #3b82f6;
    border-color: #3b82f6;
    color: white;
  }

  .edit-button {
    background-color: transparent;
    border-color: var(--border-color);
    color: var(--text-color);
  }

  .edit-button:hover:not(:disabled) {
    background-color: #3b82f6;
    border-color: #3b82f6;
    color: white;
  }

  .delete-config-button {
    background-color: transparent;
    border-color: var(--error-color);
    color: var(--error-color);
  }

  .delete-config-button:hover:not(:disabled) {
    background-color: var(--error-color);
    border-color: var(--error-color);
    color: white;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(239, 68, 68, 0.25);
  }

  .delete-config-button:active:not(:disabled) {
    transform: translateY(0);
    box-shadow: 0 2px 4px rgba(239, 68, 68, 0.2);
  }

  .saved-configs-section {
    margin-bottom: 2rem;
  }

  .section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border-color);
  }

  .section-header h4 {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin: 0;
    font-size: 1.1rem;
    font-weight: 500;
    color: var(--text-color);
  }

  button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  /* Additional styles to match LLM provider structure */
  .config-list {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .config-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    background: var(--card-bg);
    transition: all 0.2s ease;
  }

  .config-item.active {
    border-color: var(--primary-color);
    background: var(--primary-bg);
  }

  .config-item:hover:not(.active) {
    border-color: var(--border-hover);
    background: var(--hover-color);
  }

  .config-info {
    flex: 1;
    min-width: 0;
  }

  .config-name {
    font-weight: 500;
    color: var(--text-color);
    font-size: 0.95rem;
    margin-bottom: 0.25rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .info-tooltip {
    display: inline-flex;
    align-items: center;
    color: var(--text-muted);
    opacity: 0.6;
    cursor: help;
    transition: opacity 0.2s ease;
    position: relative;
  }

  .info-tooltip:hover {
    opacity: 1;
    color: var(--primary-color);
  }

  .info-tooltip[data-tooltip]:hover::after {
    content: attr(data-tooltip);
    position: fixed;
    left: var(--tooltip-left, 50%);
    top: var(--tooltip-top, 50%);
    background: #1a1a1a;
    color: white;
    padding: 8px 12px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: normal;
    max-width: 320px;
    white-space: normal;
    z-index: 9999;
    line-height: 1.4;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
    text-align: left;
    pointer-events: none;
    transform: translate(-50%, 8px);
  }

  /* Disable native browser tooltip completely */
  .info-tooltip[data-tooltip] {
    /* Remove any title attribute behavior */
  }
  
  .info-tooltip[data-tooltip]:hover {
    /* Prevent native tooltip from showing */
  }

  .config-provider {
    font-size: 0.8rem;
    color: var(--text-muted);
    margin-bottom: 0.25rem;
  }

  .config-url {
    font-size: 0.75rem;
    color: var(--text-muted);
    opacity: 0.7;
    max-width: 400px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    text-overflow: ellipsis;
    line-height: 1.4;
  }

  .config-actions {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-shrink: 0;
  }

  .empty-state {
    text-align: center;
    padding: 3rem 2rem;
    border: 2px dashed var(--border-color);
    border-radius: 8px;
    background: var(--card-bg);
  }

  .empty-icon {
    margin-bottom: 1rem;
    color: var(--text-muted);
    opacity: 0.6;
  }

  .empty-state h4 {
    margin: 0 0 0.5rem;
    color: var(--text-color);
    font-size: 1.1rem;
    font-weight: 500;
  }

  .empty-state p {
    margin: 0 0 1.5rem;
    color: var(--text-muted);
    font-size: 0.9rem;
    line-height: 1.5;
  }

  .create-first-config-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    background: #3b82f6;
    color: white;
    border: none;
    padding: 0.6rem 1.2rem;
    border-radius: 10px;
    cursor: pointer;
    font-size: 0.95rem;
    font-weight: 500;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }

  .create-first-config-btn:hover {
    background: #2563eb;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }
  
  .create-first-config-btn:active {
    transform: translateY(0);
  }

  /* Copy button styles - matches SummaryModal */
  .textarea-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.5rem;
  }

  .prompt-text-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.75rem;
  }

  .copy-button-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    color: var(--text-secondary);
    padding: 0.5rem 0.75rem;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s ease;
    font-size: 0.85rem;
  }

  .copy-button-header:hover {
    background-color: var(--hover-bg);
    color: var(--primary-color);
    border-color: var(--primary-color);
  }

  .copy-button-header.copied {
    background-color: var(--success-bg);
    border-color: var(--success-color);
    color: var(--success-color);
  }

  .copy-button-header.copied:hover {
    background-color: var(--success-bg);
    border-color: var(--success-color);
    color: var(--success-color);
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
    background-color: #2563eb !important;
    color: white !important;
    border-color: #2563eb !important;
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