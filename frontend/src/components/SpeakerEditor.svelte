<script lang="ts">
  import { onMount } from 'svelte';
  import axiosInstance from '$lib/axios';
  import { createEventDispatcher } from 'svelte';

  /**
   * @typedef {object} Speaker
   * @property {number} id
   * @property {string} name
   * @property {string} [display_name]
   * @property {string} uuid
   * @property {boolean} verified
   * @property {number} [confidence]
   * @property {string} [suggested_name]
   */

  // Props
  /** @type {number} */
  export let fileId;
  /** @type {Array<Speaker>} */
  export let speakers = [];
  /** @type {boolean} */
  export let isLoading = false;

  const dispatch = createEventDispatcher();
  
  /** @type {boolean} */
  let savingChanges = false;
  /** @type {string|null} */
  let errorMessage = null;
  /** @type {string|null} */
  let successMessage = null;
  /** @type {Array<{id: number, name: string, display_name: string|null, verified: boolean, changed: boolean, confidence?: number, suggested_name?: string}>} */
  let editableSpeakers = [];

  onMount(() => {
    loadSpeakers();
  });

  /**
   * Load speakers for the current file only
   */
  async function loadSpeakers() {
    try {
      isLoading = true;
      const response = await axiosInstance.get(`/api/speakers/?file_id=${fileId}`);
      speakers = response.data;
      updateEditableSpeakers();
    } catch (error) {
      console.error('Error loading speakers:', error);
      errorMessage = 'Failed to load speakers';
    } finally {
      isLoading = false;
    }
  }

  /**
   * Initialize the editable speakers list
   */
  function updateEditableSpeakers() {
    editableSpeakers = speakers.map(speaker => ({
      id: speaker.id,
      name: speaker.name,
      display_name: speaker.display_name || speaker.suggested_name || '',
      verified: speaker.verified,
      changed: false,
      confidence: speaker.confidence,
      suggested_name: speaker.suggested_name
    }));
  }

  /**
   * Mark a speaker as changed when its display name is edited
   * @param {number} id - The speaker ID
   */
  function handleInputChange(id) {
    const index = editableSpeakers.findIndex(s => s.id === id);
    if (index !== -1) {
      editableSpeakers[index].changed = true;
    }
  }

  /**
   * Save only changed speakers with meaningful names
   */
  async function saveChanges() {
    savingChanges = true;
    errorMessage = null;
    successMessage = null;
    
    try {
      const changedSpeakers = editableSpeakers.filter(s => 
        s.changed && 
        s.display_name.trim() !== "" && 
        !s.display_name.startsWith('SPEAKER_')
      );
      
      if (changedSpeakers.length === 0) {
        successMessage = 'No meaningful speaker names to save';
        return;
      }
      
      // Save each changed speaker with a meaningful name
      for (const speaker of changedSpeakers) {
        await axiosInstance.put(`/api/speakers/${speaker.id}`, {
          display_name: speaker.display_name.trim()
        });
      }
      
      // Reload speakers to get updated data
      await loadSpeakers();
      successMessage = `${changedSpeakers.length} speaker(s) updated successfully`;
      dispatch('speakersUpdated', { speakers });
    } catch (error) {
      console.error('Error saving speakers:', error);
      errorMessage = 'Failed to save changes';
    } finally {
      savingChanges = false;
    }
  }
</script>

<div class="speaker-editor">
  <h3>Speaker Identification</h3>
  
  {#if isLoading}
    <div class="loading">Loading speakers...</div>
  {:else}
    {#if errorMessage}
      <div class="error-message">{errorMessage}</div>
    {/if}
    
    {#if successMessage}
      <div class="success-message">{successMessage}</div>
    {/if}
    
    <div class="speaker-list">
      {#if editableSpeakers.length === 0}
        <p>No speakers found for this recording.</p>
      {:else}
        <p class="helper-text">Provide names for the speakers detected in this recording.</p>
        
        {#each editableSpeakers as speaker (speaker.id)}
          <div class="speaker-item">
            <div class="speaker-original">
              {speaker.name}
            </div>
            <div class="speaker-edit">
              <div class="input-wrapper">
                <input 
                  type="text" 
                  placeholder="Enter real name" 
                  bind:value={speaker.display_name}
                  on:input={() => handleInputChange(speaker.id)}
                  title="Enter a custom name for {speaker.name} (e.g., 'John Smith', 'Interviewer', etc.)"
                  class:suggested={speaker.confidence && speaker.confidence >= 0.5}
                />
                {#if speaker.confidence && speaker.confidence >= 0.5 && speaker.suggested_name && !speaker.changed}
                  <div class="suggestion-info">
                    <span class="confidence-badge" 
                          style="background-color: {speaker.confidence >= 0.75 ? 'var(--success-color)' : 'var(--warning-color)'}">
                      {Math.round(speaker.confidence * 100)}% match
                    </span>
                    <span class="suggested-label">Suggested: {speaker.suggested_name}</span>
                  </div>
                {/if}
              </div>
              {#if speaker.verified}
                <span class="verified-badge" title="This speaker has been verified">✓</span>
              {/if}
            </div>
          </div>
        {/each}
        
        <div class="speaker-actions">
          <button 
            on:click={saveChanges} 
            disabled={savingChanges}
            title="Save all speaker name changes and update the transcript"
          >
            {savingChanges ? 'Saving...' : 'Save Speaker Names'}
          </button>
        </div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .speaker-editor {
    background-color: var(--background-alt);
    padding: 1rem;
    border-radius: var(--border-radius);
    margin-bottom: 1.5rem;
    border: 1px solid var(--border-color);
  }
  
  h3 {
    margin-top: 0;
    margin-bottom: 1rem;
    font-size: 1.2rem;
    color: var(--primary-color);
    border-bottom: 1px solid var(--border-color-soft);
    padding-bottom: 0.5rem;
  }
  
  .helper-text {
    margin-bottom: 1rem;
    font-size: 0.9rem;
    color: var(--text-color-secondary);
  }
  
  .speaker-item {
    display: flex;
    align-items: center;
    margin-bottom: 0.75rem;
    padding: 0.5rem;
    background-color: var(--background-main);
    border-radius: var(--border-radius-sm);
  }
  
  .speaker-original {
    flex: 0 0 120px;
    font-weight: 500;
    color: var(--text-color-secondary);
  }
  
  .speaker-edit {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  
  .input-wrapper {
    flex: 1;
    position: relative;
  }
  
  input {
    width: 100%;
    padding: 0.5rem;
    border: 1px solid var(--border-color);
    border-radius: var(--border-radius-sm);
    background-color: var(--background-main);
  }
  
  input.suggested {
    border-color: var(--warning-color);
  }
  
  .suggestion-info {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-top: 0.25rem;
    font-size: 0.8rem;
  }
  
  .confidence-badge {
    padding: 0.2rem 0.4rem;
    border-radius: 4px;
    color: white;
    font-weight: 500;
    font-size: 0.75rem;
  }
  
  .suggested-label {
    color: var(--text-color-secondary);
  }
  
  .verified-badge {
    margin-left: 0.5rem;
    color: var(--success-color);
    font-weight: bold;
  }
  
  .speaker-actions {
    margin-top: 1rem;
    display: flex;
    justify-content: flex-end;
  }
  
  button {
    padding: 0.5rem 1rem;
    background-color: var(--primary-color);
    color: white;
    border: none;
    border-radius: var(--border-radius-sm);
    cursor: pointer;
    font-weight: 500;
  }
  
  button:hover {
    background-color: var(--primary-color-dark);
  }
  
  button:disabled {
    background-color: var(--text-color-disabled);
    cursor: not-allowed;
  }
  
  .error-message {
    padding: 0.5rem;
    background-color: var(--error-bg);
    color: var(--error-color);
    border-radius: var(--border-radius-sm);
    margin-bottom: 1rem;
  }
  
  .success-message {
    padding: 0.5rem;
    background-color: var(--success-bg);
    color: var(--success-color);
    border-radius: var(--border-radius-sm);
    margin-bottom: 1rem;
  }
  
  .loading {
    font-style: italic;
    color: var(--text-color-secondary);
  }
</style>
