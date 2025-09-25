<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { fade, slide } from 'svelte/transition';
  import ConfirmationModal from './ConfirmationModal.svelte';
  import { getSpeakerColor } from '$lib/utils/speakerColors';

  export let speaker: {
    id: number;
    name: string;
    display_name?: string;
    verified: boolean;
    confidence?: number;
  };
  export let suggestions: {
    profile_id?: number;
    profile_name: string;
    confidence: number;
    confidence_level: string;
    auto_accept: boolean;
    reason: string;
    source: string;
    create_new?: boolean;
  }[] = [];
  export let crossMediaOccurrences: {
    media_file_id: number;
    filename: string;
    title: string;
    upload_time: string;
    speaker_label: string;
    confidence?: number;
    verified: boolean;
    same_speaker: boolean;
  }[] = [];

  const dispatch = createEventDispatcher();

  let showNewProfileModal = false;
  let showConfirmModal = false;
  let newProfileName = '';
  let selectedAction = '';
  let selectedProfileId: number | null = null;
  let confirmMessage = '';

  // Props are validated through TypeScript interfaces
  
  function getConfidenceColor(confidence: number): string {
    if (confidence >= 0.75) return 'var(--success-color)';
    if (confidence >= 0.50) return 'var(--warning-color)';
    return 'var(--error-color)';
  }
  
  function getConfidenceBadgeClass(confidenceLevel: string): string {
    switch (confidenceLevel) {
      case 'high': return 'confidence-badge confidence-high';
      case 'medium': return 'confidence-badge confidence-medium';
      case 'low': return 'confidence-badge confidence-low';
      default: return 'confidence-badge confidence-unknown';
    }
  }
  
  function handleAcceptSuggestion(suggestion: typeof suggestions[0]) {
    if (suggestion.create_new) {
      // Handle LLM suggestion to create new profile
      selectedAction = 'create_profile';
      newProfileName = suggestion.profile_name;
      confirmMessage = `Create new profile "${suggestion.profile_name}" and assign this speaker?`;
    } else {
      // Handle existing profile assignment
      selectedAction = 'accept';
      selectedProfileId = suggestion.profile_id || null;
      confirmMessage = `Assign this speaker to "${suggestion.profile_name}"?`;
    }
    showConfirmModal = true;
  }
  
  function handleRejectSuggestions() {
    selectedAction = 'reject';
    confirmMessage = 'Reject all speaker identification suggestions?';
    showConfirmModal = true;
  }
  
  function handleCreateNewProfile() {
    if (newProfileName.trim()) {
      selectedAction = 'create_profile';
      confirmMessage = `Create new profile "${newProfileName}" and assign this speaker?`;
      showConfirmModal = true;
    }
  }
  
  function confirmAction() {
    const actionData: {
      action: string;
      speaker_id: number;
      profile_id?: number;
      profile_name?: string;
    } = {
      action: selectedAction,
      speaker_id: speaker.id
    };
    
    if (selectedAction === 'accept' && selectedProfileId !== null) {
      actionData.profile_id = selectedProfileId;
    } else if (selectedAction === 'create_profile') {
      actionData.profile_name = newProfileName.trim();
    }
    
    dispatch('verify', actionData);
    
    // Reset state
    showConfirmModal = false;
    showNewProfileModal = false;
    newProfileName = '';
    selectedAction = '';
    selectedProfileId = null;
  }
  
  function showCreateProfileModal() {
    showNewProfileModal = true;
  }
</script>

<div class="verification-container" transition:fade>
  <!-- Speaker Info Header -->
  <div class="verification-header">
    <div class="header-content">
      <h3 class="verification-title">
        Speaker Verification:
        <span
          class="speaker-chip"
          style="background-color: {getSpeakerColor(speaker.name).bg}; border-color: {getSpeakerColor(speaker.name).border}; color: var(--text-color, {getSpeakerColor(speaker.name).textLight});"
        >
          {speaker.name}
        </span>
      </h3>
      <p class="verification-subtitle">
        Please verify the speaker identification for this audio segment
      </p>
    </div>
    
    {#if speaker.confidence}
      <span class="{getConfidenceBadgeClass('low')}">
        {Math.round(speaker.confidence * 100)}% confidence
      </span>
    {/if}
  </div>

  <!-- Suggestions Section -->
  {#if suggestions && suggestions.length > 0}
    <div class="suggestions-section" transition:slide>
      <h4 class="section-title">
        Suggested Matches
      </h4>
      
      <div class="suggestions-list">
        {#each suggestions as suggestion}
          <div class="suggestion-item">
            <div class="suggestion-content">
              <div class="suggestion-header">
                <span class="profile-name">
                  {suggestion.profile_name}
                </span>

                <span class="{getConfidenceBadgeClass(suggestion.confidence_level)}">
                  {Math.round(suggestion.confidence * 100)}%
                </span>

                <!-- Source indicator -->
                {#if suggestion.source === 'voice_embedding'}
                  <span class="source-badge voice-embedding">
                    <svg class="source-icon" xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/>
                      <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
                      <line x1="12" x2="12" y1="19" y2="22"/>
                      <line x1="8" x2="16" y1="22" y2="22"/>
                    </svg>
                    Voice Match
                  </span>
                {:else if suggestion.source === 'llm_analysis'}
                  <span class="source-badge llm-analysis">
                    <svg class="source-icon" xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M9.663 17h4.673M12 3v1m6.364 1.636-.707.707M21 12h-1M4 12H3m3.343-5.657-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/>
                    </svg>
                    AI Analysis
                  </span>
                {:else if suggestion.source === 'profile_embedding'}
                  <span class="source-badge profile-embedding">
                    <svg class="source-icon" xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>
                      <circle cx="9" cy="7" r="4"/>
                      <path d="M22 21v-2a4 4 0 0 0-3-3.87"/>
                      <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
                    </svg>
                    Profile Match
                  </span>
                {/if}

                {#if suggestion.auto_accept}
                  <span class="auto-accept-badge">
                    Auto-Accept
                  </span>
                {/if}
              </div>

              <div class="suggestion-details">
                <p class="suggestion-reason">
                  {suggestion.reason || 'Based on voice characteristics'}
                </p>

                <!-- Additional metadata for different suggestion types -->
                {#if suggestion.source === 'voice_embedding'}
                  <p class="suggestion-metadata">
                    Based on voice characteristics analysis
                  </p>
                {:else if suggestion.source === 'llm_analysis'}
                  <p class="suggestion-metadata">
                    AI identified speaker from context
                  </p>
                {/if}
              </div>
            </div>
            
            <div class="suggestion-actions">
              <button
                on:click={() => handleAcceptSuggestion(suggestion)}
                class="accept-button"
              >
                ✓ Accept
              </button>
            </div>
          </div>
        {/each}
      </div>
    </div>
  {/if}

  <!-- Cross-Media Occurrences -->
  {#if crossMediaOccurrences && crossMediaOccurrences.length > 0}
    <div class="cross-media-section" transition:slide>
      <h4 class="section-title">
        This Speaker Appears In
        <span class="occurrence-count">
          {crossMediaOccurrences.length}
        </span>
      </h4>
      
      <div class="occurrences-list">
        {#each crossMediaOccurrences as occurrence}
          <div class="occurrence-item">
            <div class="occurrence-content">
              <span class="occurrence-title">
                {occurrence.title}
              </span>
              <span class="occurrence-label">
                as
                <span
                  class="speaker-chip speaker-chip-small"
                  style="background-color: {getSpeakerColor(occurrence.speaker_label).bg}; border-color: {getSpeakerColor(occurrence.speaker_label).border}; color: var(--text-color, {getSpeakerColor(occurrence.speaker_label).textLight});"
                >
                  {occurrence.speaker_label}
                </span>
              </span>
              {#if occurrence.same_speaker}
                <span class="current-badge">
                  Current
                </span>
              {/if}
            </div>
            
            <div class="occurrence-meta">
              {#if occurrence.verified}
                <span class="verified-icon">✓</span>
              {/if}
              
              {#if occurrence.confidence}
                <span class="confidence-text" style="color: {getConfidenceColor(occurrence.confidence)}">
                  {Math.round(occurrence.confidence * 100)}%
                </span>
              {/if}
            </div>
          </div>
        {/each}
      </div>
    </div>
  {/if}

  <!-- Action Buttons -->
  <div class="action-buttons">
    <button
      on:click={showCreateProfileModal}
      class="primary-button"
    >
      + Create New Profile
    </button>
    
    <button
      on:click={handleRejectSuggestions}
      class="secondary-button"
    >
      Keep Unassigned
    </button>
    
    <button
      on:click={() => dispatch('cancel')}
      class="cancel-button-action"
    >
      Cancel
    </button>
  </div>
</div>

<!-- New Profile Modal -->
{#if showNewProfileModal}
  <div
    class="modal-backdrop"
    role="dialog"
    aria-modal="true"
    tabindex="-1"
    transition:fade
    on:click={() => { showNewProfileModal = false; newProfileName = ''; }}
    on:keydown={(e) => e.key === 'Escape' && (showNewProfileModal = false, newProfileName = '')}
  >
    <div class="modal-container" role="document" on:click|stopPropagation>
      <div class="modal-content">
        <div class="modal-header">
          <h3 class="modal-title">
            Create New Speaker Profile
          </h3>
          <button 
            class="modal-close-button" 
            on:click={() => { showNewProfileModal = false; newProfileName = ''; }}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>
        
        <div class="modal-body">
          <label for="profileName" class="input-label">
            Profile Name
          </label>
          <input
            id="profileName"
            type="text"
            bind:value={newProfileName}
            placeholder="Enter speaker name..."
            class="profile-name-input"
          />
        </div>
        
        <div class="modal-footer">
          <button
            on:click={() => { showNewProfileModal = false; newProfileName = ''; }}
            class="modal-button cancel-button"
          >
            Cancel
          </button>
          <button
            on:click={handleCreateNewProfile}
            disabled={!newProfileName.trim()}
            class="modal-button confirm-button"
          >
            Create Profile
          </button>
        </div>
      </div>
    </div>
  </div>
{/if}

<!-- Confirmation Modal -->
{#if showConfirmModal}
  <ConfirmationModal
    isOpen={showConfirmModal}
    title="Confirm Action"
    message={confirmMessage}
    confirmText="Confirm"
    cancelText="Cancel"
    on:confirm={confirmAction}
    on:cancel={() => { showConfirmModal = false; }}
  />
{/if}

<style>
  .verification-container {
    background: var(--card-background);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    padding: 1.5rem;
    box-shadow: var(--card-shadow);
    transition: all 0.3s ease;
  }

  .verification-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    margin-bottom: 1.5rem;
    gap: 1rem;
  }

  .header-content {
    flex: 1;
  }

  .verification-title {
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--text-color);
    margin: 0 0 0.5rem 0;
    line-height: 1.4;
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex-wrap: wrap;
  }

  .speaker-chip {
    padding: 0.25rem 0.75rem;
    border: 1px solid;
    border-radius: 20px;
    font-size: 0.875rem;
    font-weight: 500;
    white-space: nowrap;
  }

  .speaker-chip-small {
    padding: 0.125rem 0.5rem;
    font-size: 0.75rem;
    border-radius: 12px;
  }

  .verification-subtitle {
    font-size: 0.875rem;
    color: var(--text-secondary);
    margin: 0;
    line-height: 1.5;
  }

  .section-title {
    font-size: 1.125rem;
    font-weight: 500;
    color: var(--text-color);
    margin: 0 0 1rem 0;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .suggestions-section, .cross-media-section {
    margin-bottom: 1.5rem;
  }

  .suggestions-list {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .suggestion-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem;
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 10px;
    transition: all 0.2s ease;
  }

  .suggestion-item:hover {
    border-color: var(--primary-color);
    box-shadow: 0 2px 8px rgba(var(--primary-color-rgb), 0.1);
  }

  .suggestion-content {
    flex: 1;
  }

  .suggestion-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 0.5rem;
    flex-wrap: wrap;
  }

  .profile-name {
    font-weight: 500;
    color: var(--text-color);
    font-size: 0.95rem;
  }

  .suggestion-reason {
    font-size: 0.875rem;
    color: var(--text-secondary);
    margin: 0;
    line-height: 1.4;
  }

  .suggestion-actions {
    display: flex;
    gap: 0.5rem;
  }

  .accept-button {
    padding: 0.5rem 1rem;
    background: var(--success-color);
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    gap: 0.25rem;
  }

  .accept-button:hover {
    background: color-mix(in srgb, var(--success-color) 85%, black);
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(16, 185, 129, 0.25);
  }

  .occurrences-list {
    max-height: 10rem;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .occurrence-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem;
    background: color-mix(in srgb, var(--primary-color) 5%, var(--surface-color));
    border: 1px solid color-mix(in srgb, var(--primary-color) 15%, var(--border-color));
    border-radius: 8px;
    transition: all 0.2s ease;
  }

  .occurrence-content {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
  }

  .occurrence-title {
    font-weight: 500;
    color: var(--text-color);
    font-size: 0.875rem;
  }

  .occurrence-label {
    font-size: 0.8rem;
    color: var(--text-secondary);
  }

  .occurrence-meta {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .verified-icon {
    color: var(--success-color);
    font-weight: bold;
  }

  .confidence-text {
    font-size: 0.8rem;
    font-weight: 500;
  }

  .occurrence-count {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.5rem;
    height: 1.5rem;
    font-size: 0.75rem;
    font-weight: bold;
    color: white;
    background: var(--primary-color);
    border-radius: 50%;
  }

  .current-badge, .auto-accept-badge {
    padding: 0.125rem 0.5rem;
    font-size: 0.75rem;
    font-weight: 500;
    border-radius: 12px;
    white-space: nowrap;
  }

  .current-badge {
    background: color-mix(in srgb, var(--primary-color) 15%, var(--surface-color));
    color: var(--primary-color);
  }

  .auto-accept-badge {
    background: color-mix(in srgb, var(--info-color) 15%, var(--surface-color));
    color: var(--info-color);
  }

  .confidence-badge {
    padding: 0.25rem 0.5rem;
    font-size: 0.75rem;
    font-weight: 500;
    border-radius: 12px;
    white-space: nowrap;
  }

  .confidence-high {
    background: color-mix(in srgb, var(--success-color) 15%, var(--surface-color));
    color: var(--success-color);
  }

  .confidence-medium {
    background: color-mix(in srgb, var(--warning-color) 15%, var(--surface-color));
    color: var(--warning-color);
  }

  .confidence-low {
    background: color-mix(in srgb, var(--error-color) 15%, var(--surface-color));
    color: var(--error-color);
  }

  .confidence-unknown {
    background: color-mix(in srgb, var(--text-secondary) 15%, var(--surface-color));
    color: var(--text-secondary);
  }

  .action-buttons {
    display: flex;
    gap: 0.75rem;
    flex-wrap: wrap;
    margin-top: 1rem;
  }

  .primary-button, .secondary-button, .cancel-button-action {
    padding: 0.6rem 1.2rem;
    border: none;
    border-radius: 10px;
    font-size: 0.95rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    min-width: 120px;
  }

  .primary-button {
    background: var(--primary-color);
    color: white;
    box-shadow: 0 2px 4px rgba(var(--primary-color-rgb), 0.2);
  }

  .primary-button:hover {
    background: var(--primary-hover);
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(var(--primary-color-rgb), 0.3);
  }

  .secondary-button {
    background: var(--surface-color);
    color: var(--text-color);
    border: 1px solid var(--border-color);
  }

  .secondary-button:hover {
    background: var(--button-hover);
    border-color: var(--text-secondary);
  }

  .cancel-button-action {
    background: var(--error-color);
    color: white;
  }

  .cancel-button-action:hover {
    background: color-mix(in srgb, var(--error-color) 85%, black);
  }

  /* Modal styles */
  .modal-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: var(--modal-backdrop);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    padding: 1rem;
  }

  .modal-container {
    background: var(--background-color);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    max-width: 500px;
    width: 100%;
    overflow: hidden;
    box-shadow: var(--dropdown-shadow);
  }

  .modal-content {
    display: flex;
    flex-direction: column;
  }

  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1.5rem;
    border-bottom: 1px solid var(--border-color);
  }

  .modal-title {
    margin: 0;
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--text-color);
  }

  .modal-close-button {
    background: none;
    border: none;
    cursor: pointer;
    padding: 0.5rem;
    color: var(--text-secondary);
    transition: color 0.2s ease;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .modal-close-button:hover {
    color: var(--text-color);
    background: var(--button-hover);
  }

  .modal-body {
    padding: 1.5rem;
  }

  .input-label {
    display: block;
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--text-color);
    margin-bottom: 0.5rem;
  }

  .profile-name-input {
    width: 100%;
    padding: 0.75rem;
    border: 1px solid var(--input-border);
    border-radius: 8px;
    background: var(--input-background);
    color: var(--text-color);
    font-size: 0.95rem;
    transition: all 0.2s ease;
  }

  .profile-name-input:focus {
    outline: none;
    border-color: var(--input-focus-border);
    box-shadow: 0 0 0 3px rgba(var(--primary-color-rgb), 0.1);
  }

  .modal-footer {
    display: flex;
    gap: 0.75rem;
    padding: 1rem 1.5rem 1.5rem;
    justify-content: flex-end;
    border-top: 1px solid var(--border-color);
  }

  .modal-button {
    padding: 0.6rem 1.2rem;
    border: none;
    border-radius: 10px;
    font-size: 0.95rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    min-width: 120px;
  }

  .modal-button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .cancel-button {
    background: var(--surface-color);
    color: var(--text-color);
    border: 1px solid var(--border-color);
  }

  .cancel-button:hover:not(:disabled) {
    background: var(--button-hover);
  }

  .confirm-button {
    background: var(--primary-color);
    color: white;
    box-shadow: 0 2px 4px rgba(var(--primary-color-rgb), 0.2);
  }

  .confirm-button:hover:not(:disabled) {
    background: var(--primary-hover);
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(var(--primary-color-rgb), 0.3);
  }

  /* Source Badge Styles */
  .source-badge {
    padding: 0.25rem 0.5rem;
    border-radius: 6px;
    font-size: 0.75rem;
    font-weight: 500;
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
  }

  .source-badge .source-icon {
    width: 12px;
    height: 12px;
    stroke: currentColor;
  }

  .source-badge.voice-embedding {
    background: color-mix(in srgb, var(--success-color) 15%, var(--surface-color));
    color: var(--success-color);
    border: 1px solid color-mix(in srgb, var(--success-color) 25%, transparent);
  }

  .source-badge.llm-analysis {
    background: color-mix(in srgb, var(--primary-color) 15%, var(--surface-color));
    color: var(--primary-color);
    border: 1px solid color-mix(in srgb, var(--primary-color) 25%, transparent);
  }

  .source-badge.profile-embedding {
    background: color-mix(in srgb, var(--warning-color) 15%, var(--surface-color));
    color: var(--warning-color);
    border: 1px solid color-mix(in srgb, var(--warning-color) 25%, transparent);
  }

  /* Suggestion Metadata */
  .suggestion-metadata {
    font-size: 0.8rem;
    color: var(--text-tertiary);
    margin: 0.25rem 0 0 0;
    font-style: italic;
  }

  /* Custom scrollbar */
  .occurrences-list::-webkit-scrollbar {
    width: 6px;
  }

  .occurrences-list::-webkit-scrollbar-track {
    background: var(--surface-color);
    border-radius: 3px;
  }

  .occurrences-list::-webkit-scrollbar-thumb {
    background: var(--border-color);
    border-radius: 3px;
  }

  .occurrences-list::-webkit-scrollbar-thumb:hover {
    background: var(--text-secondary);
  }

  /* Responsive design */
  @media (max-width: 768px) {
    .verification-header {
      flex-direction: column;
      align-items: flex-start;
    }

    .suggestion-item {
      flex-direction: column;
      align-items: flex-start;
      gap: 1rem;
    }

    .suggestion-actions {
      align-self: flex-end;
    }

    .action-buttons {
      flex-direction: column;
    }

    .primary-button, .secondary-button, .cancel-button-action {
      width: 100%;
    }

    .modal-footer {
      flex-direction: column-reverse;
    }

    .modal-button {
      width: 100%;
    }
  }

  /* Reduced motion support */
  @media (prefers-reduced-motion: reduce) {
    * {
      transition: none !important;
      animation: none !important;
    }
  }
</style>