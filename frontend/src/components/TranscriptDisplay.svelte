<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { slide } from 'svelte/transition';
  import { getSpeakerColor } from '$lib/utils/speakerColors';
  
  export let file: any = null;
  export let isEditingTranscript: boolean = false;
  export let editedTranscript: string = '';
  export let savingTranscript: boolean = false;
  export let transcriptError: string = '';
  export let editingSegmentId: string | number | null = null;
  export let editingSegmentText: string = '';
  export let isEditingSpeakers: boolean = false;
  export let speakerList: any[] = [];

  const dispatch = createEventDispatcher();

  // Helper function to get consistent speaker name for color mapping
  function getSpeakerNameForColor(segment: any): string {
    // Use the original speaker name/label for consistent color mapping
    return segment.speaker_label || segment.speaker?.name || 'Unknown';
  }

  function formatSimpleTimestamp(seconds: number): string {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
  }

  function handleSegmentClick(startTime: number) {
    dispatch('segmentClick', { startTime });
  }

  function editSegment(segment: any) {
    dispatch('editSegment', { segment });
  }

  function saveSegment(segment: any) {
    dispatch('saveSegment', { segment });
  }

  function cancelEditSegment() {
    dispatch('cancelEditSegment');
  }

  function saveTranscript() {
    dispatch('saveTranscript');
  }

  function cancelEditTranscript() {
    isEditingTranscript = false;
  }

  function exportTranscript(format: string) {
    dispatch('exportTranscript', { format });
  }

  function toggleSpeakerEditor() {
    isEditingSpeakers = !isEditingSpeakers;
  }

  function saveSpeakerNames() {
    dispatch('saveSpeakerNames');
  }
</script>

<section class="transcript-column">
  <h4>Transcript</h4>
  {#if file.transcript_segments && file.transcript_segments.length > 0}
    {#if isEditingTranscript}
      <textarea bind:value={editedTranscript} rows="20" class="transcript-textarea"></textarea>
      <div class="edit-actions">
        <button 
          on:click={saveTranscript} 
          disabled={savingTranscript}
          title="Save all changes to the transcript"
        >
          {savingTranscript ? 'Saving...' : 'Save Transcript'}
        </button>
        <button 
          class="cancel-button" 
          on:click={cancelEditTranscript}
          title="Cancel editing and discard all changes"
        >Cancel</button>
      </div>
      {#if transcriptError}
        <p class="error-message small">{transcriptError}</p>
      {/if}
    {:else}
      <div class="transcript-display">
        {#each file.transcript_segments as segment}
          <div 
            class="transcript-segment" 
            data-segment-id="{segment.id || `${segment.start_time}-${segment.end_time}`}"
          >
            {#if editingSegmentId === segment.id}
              <div class="segment-edit-container">
                <div class="segment-time">{formatSimpleTimestamp(segment.start_time)}</div>
                <div class="segment-speaker">{segment.speaker?.display_name || segment.speaker?.name || segment.speaker_label || 'Unknown'}</div>
                <div class="segment-edit-input">
                  <textarea bind:value={editingSegmentText} rows="3" class="segment-textarea"></textarea>
                  <div class="segment-edit-actions">
                    <button 
                      class="save-button" 
                      on:click={() => saveSegment(segment)} 
                      disabled={savingTranscript}
                      title="Save changes to this segment"
                    >
                      {savingTranscript ? 'Saving...' : 'Save'}
                    </button>
                    <button 
                      class="cancel-button" 
                      on:click={cancelEditSegment}
                      title="Cancel editing this segment and discard changes"
                    >Cancel</button>
                  </div>
                  {#if transcriptError}
                    <p class="error-message small">{transcriptError}</p>
                  {/if}
                </div>
              </div>
            {:else}
              <div class="segment-row">
                <button 
                  class="segment-content" 
                  on:click={() => handleSegmentClick(segment.start_time)}
                  on:keydown={(e) => e.key === 'Enter' && handleSegmentClick(segment.start_time)}
                  title="Jump to this segment"
                >
                  <div class="segment-time">{formatSimpleTimestamp(segment.start_time)}</div>
                  <div 
                    class="segment-speaker" 
                    style="background-color: {getSpeakerColor(getSpeakerNameForColor(segment)).bg}; border-color: {getSpeakerColor(getSpeakerNameForColor(segment)).border}; --speaker-light: {getSpeakerColor(getSpeakerNameForColor(segment)).textLight}; --speaker-dark: {getSpeakerColor(getSpeakerNameForColor(segment)).textDark};"
                  >
                    {segment.speaker?.display_name || segment.speaker?.name || segment.speaker_label || 'Unknown'}
                  </div>
                  <div class="segment-text">{segment.text}</div>
                </button>
                <button 
                  class="edit-button" 
                  on:click|stopPropagation={() => editSegment(segment)} 
                  title="Edit segment"
                >
                  Edit
                </button>
              </div>
            {/if}
          </div>
        {/each}
      </div>
      
      <div class="transcript-actions">
        <div class="export-dropdown">
          <button 
            class="export-transcript-button"
            title="Export transcript in various formats including text, JSON, CSV, SRT, and WebVTT"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
              <polyline points="7 10 12 15 17 10"></polyline>
              <line x1="12" y1="15" x2="12" y2="3"></line>
            </svg>
            Export
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="4" y="4" width="16" height="16" rx="2" ry="2"></rect>
              <line x1="9" y1="9" x2="15" y2="9"></line>
              <line x1="9" y1="13" x2="15" y2="13"></line>
              <line x1="9" y1="17" x2="11" y2="17"></line>
            </svg>
          </button>
          <div class="export-dropdown-content">
            <button 
              on:click={() => exportTranscript('txt')}
              title="Export transcript as plain text file"
            >Plain Text (.txt)</button>
            <button 
              on:click={() => exportTranscript('json')}
              title="Export transcript as JSON file with timestamps and speaker information"
            >JSON Format (.json)</button>
            <button 
              on:click={() => exportTranscript('csv')}
              title="Export transcript as CSV file for spreadsheet applications"
            >CSV Format (.csv)</button>
            <button 
              on:click={() => exportTranscript('srt')}
              title="Export transcript as SRT subtitle file for video players"
            >SubRip Subtitles (.srt)</button>
            <button 
              on:click={() => exportTranscript('vtt')}
              title="Export transcript as WebVTT subtitle file for web video players"
            >WebVTT Subtitles (.vtt)</button>
          </div>
        </div>
        
        <button 
          class="edit-speakers-button" 
          on:click={toggleSpeakerEditor}
          title="Edit speaker names to replace generic labels (SPEAKER_01, etc.) with actual names"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 20h9"></path>
            <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path>
          </svg>
          {isEditingSpeakers ? 'Hide Speaker Editor' : 'Edit Speakers'}
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
            <circle cx="12" cy="7" r="4"></circle>
          </svg>
        </button>
        
        {#if file && file.download_url}
          <a 
            href={file.download_url} 
            class="action-button download-button" 
            download={file.filename}
            title="Download the original media file"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
              <polyline points="7 10 12 15 17 10"></polyline>
              <line x1="12" y1="15" x2="12" y2="3"></line>
            </svg>
            Download
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"></rect>
              <line x1="7" y1="2" x2="7" y2="22"></line>
              <line x1="17" y1="2" x2="17" y2="22"></line>
              <line x1="2" y1="12" x2="22" y2="12"></line>
              <line x1="2" y1="7" x2="7" y2="7"></line>
              <line x1="2" y1="17" x2="7" y2="17"></line>
              <line x1="17" y1="17" x2="22" y2="17"></line>
              <line x1="17" y1="7" x2="22" y2="7"></line>
            </svg>
          </a>
        {/if}
      </div>
      
      {#if isEditingSpeakers}
        <div class="speaker-editor-container" transition:slide={{ duration: 200 }}>
          <h4>Edit Speaker Names</h4>
          {#if speakerList && speakerList.length > 0}
            <div class="speaker-list">
              {#each speakerList as speaker}
                <div class="speaker-item">
                  <span 
                    class="speaker-original"
                    style="background-color: {getSpeakerColor(speaker.name).bg}; border-color: {getSpeakerColor(speaker.name).border}; --speaker-light: {getSpeakerColor(speaker.name).textLight}; --speaker-dark: {getSpeakerColor(speaker.name).textDark};"
                  >
                    {speaker.name}
                  </span>
                  <input 
                    type="text" 
                    bind:value={speaker.display_name} 
                    placeholder="Enter display name"
                    title="Enter a custom name for {speaker.name} (e.g., 'John Smith', 'Interviewer', etc.)"
                  />
                </div>
              {/each}
              <button 
                class="save-speakers-button" 
                on:click={saveSpeakerNames}
                title="Save all speaker name changes and update the transcript"
              >Save Speaker Names</button>
            </div>
          {:else}
            <p>No speakers found in this transcript.</p>
          {/if}
        </div>
      {/if}
    {/if}
  {:else if file.status === 'completed'}
    <p>No transcript available for this file.</p>
  {:else if file.status === 'processing'}
    <p>Transcript is being generated...</p>
  {:else}
    <p>Transcript not available.</p>
  {/if}
</section>

<style>
  .transcript-column {
    flex: 1;
    min-width: 0;
  }

  .transcript-column h4 {
    margin: 0 0 16px 0;
    font-size: 18px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .transcript-textarea {
    width: 100%;
    padding: 16px;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    background: var(--surface-color);
    color: var(--text-primary);
    font-family: monospace;
    font-size: 14px;
    line-height: 1.5;
    resize: vertical;
    min-height: 400px;
  }

  .edit-actions {
    display: flex;
    gap: 12px;
    margin-top: 12px;
  }

  .edit-actions button {
    padding: 8px 16px;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .edit-actions button:first-child {
    background: var(--primary-color);
    color: white;
    border: none;
  }

  .edit-actions button:first-child:hover:not(:disabled) {
    background: var(--primary-hover);
  }

  .edit-actions button:first-child:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .cancel-button {
    background: var(--surface-color, #f8f9fa);
    color: var(--text-primary, #374151);
    border: 1px solid var(--border-color, #d1d5db);
  }

  .cancel-button:hover {
    background: var(--surface-hover, #f3f4f6);
    border-color: var(--border-hover, #9ca3af);
  }

  .transcript-display {
    border: 1px solid var(--border-color);
    border-radius: 8px;
    background: var(--surface-color);
    max-height: 600px;
    overflow-y: auto;
  }

  .transcript-segment {
    border-bottom: 1px solid var(--border-light);
  }

  .transcript-segment:last-child {
    border-bottom: none;
  }

  .segment-row {
    display: flex;
    align-items: stretch;
  }

  .segment-content {
    flex: 1;
    display: grid;
    grid-template-columns: auto auto 1fr;
    gap: 12px;
    align-items: center;
    padding: 8px 12px;
    background: none;
    border: none;
    text-align: left;
    cursor: pointer;
    transition: all 0.2s ease;
    border-radius: 4px;
    margin: 2px 4px;
  }

  .segment-content:hover {
    background: rgba(59, 130, 246, 0.08);
  }

  .segment-time {
    font-size: 12px;
    font-weight: 600;
    color: var(--primary-color);
    font-family: monospace;
    white-space: nowrap;
    min-width: fit-content;
  }

  .segment-speaker {
    font-size: 12px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 12px;
    white-space: nowrap;
    min-width: fit-content;
    max-width: 150px;
    overflow: hidden;
    text-overflow: ellipsis;
    border: 1px solid;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    transition: all 0.2s ease;
    color: var(--speaker-light);
  }

  /* Dark mode speaker colors */
  :global([data-theme='dark']) .segment-speaker {
    color: var(--speaker-dark);
  }

  .segment-text {
    font-size: 14px;
    color: var(--text-primary);
    line-height: 1.4;
    position: relative;
    padding-left: 12px;
  }

  .segment-text::before {
    content: '';
    position: absolute;
    left: 0;
    top: 50%;
    transform: translateY(-50%);
    width: 2px;
    height: 20px;
    background: rgba(107, 114, 128, 0.3);
    border-radius: 1px;
  }

  .edit-button {
    padding: 8px 12px;
    background: none;
    border: none;
    color: #3b82f6;
    cursor: pointer;
    font-size: 12px;
    font-weight: 400;
    transition: all 0.2s ease;
    text-decoration: underline;
    text-decoration-color: transparent;
  }

  .edit-button:hover {
    color: #1d4ed8;
    text-decoration-color: #1d4ed8;
  }

  .segment-edit-container {
    padding: 16px;
    background: var(--background-secondary);
    border-left: 3px solid var(--primary-color);
  }

  .segment-edit-input {
    margin-top: 8px;
  }

  .segment-textarea {
    width: 100%;
    padding: 8px 12px;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    background: var(--surface-color);
    color: var(--text-primary);
    font-size: 14px;
    line-height: 1.4;
    resize: vertical;
  }

  .segment-edit-actions {
    display: flex;
    gap: 8px;
    margin-top: 8px;
  }

  .segment-edit-actions button {
    padding: 6px 12px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .save-button {
    background: var(--primary-color, #3b82f6);
    color: white;
    border: none;
  }

  .save-button:hover:not(:disabled) {
    background: var(--primary-hover, #1d4ed8);
  }

  .save-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .transcript-actions {
    display: flex;
    gap: 12px;
    margin-top: 16px;
    flex-wrap: wrap;
  }

  .export-dropdown {
    position: relative;
    display: inline-block;
  }

  .export-transcript-button,
  .edit-speakers-button,
  .action-button {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 16px;
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    color: var(--text-primary);
    text-decoration: none;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .export-transcript-button:hover,
  .edit-speakers-button:hover,
  .action-button:hover {
    background: var(--surface-hover);
    border-color: var(--border-hover);
  }

  .export-dropdown:hover .export-dropdown-content {
    display: block;
  }

  .export-dropdown-content {
    display: none;
    position: absolute;
    top: 100%;
    left: 0;
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    z-index: 100;
    min-width: 200px;
  }

  .export-dropdown-content button {
    display: block;
    width: 100%;
    padding: 10px 16px;
    background: none;
    border: none;
    text-align: left;
    color: var(--text-primary);
    font-size: 14px;
    cursor: pointer;
    transition: background-color 0.2s ease;
  }

  .export-dropdown-content button:hover {
    background: var(--surface-hover);
  }

  .export-dropdown-content button:first-child {
    border-radius: 6px 6px 0 0;
  }

  .export-dropdown-content button:last-child {
    border-radius: 0 0 6px 6px;
  }

  .speaker-editor-container {
    margin-top: 20px;
    padding: 20px;
    background: var(--background-secondary);
    border-radius: 8px;
    border: 1px solid var(--border-color);
  }

  .speaker-editor-container h4 {
    margin: 0 0 16px 0;
    font-size: 16px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .speaker-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .speaker-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px;
    background: var(--surface-color);
    border-radius: 6px;
    border: 1px solid var(--border-color);
  }

  .speaker-original {
    font-weight: 700;
    min-width: 120px;
    padding: 4px 12px;
    border-radius: 12px;
    border: 1px solid;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    font-size: 12px;
    text-align: center;
    transition: all 0.2s ease;
    color: var(--speaker-light);
  }

  /* Dark mode speaker-original colors */
  :global([data-theme='dark']) .speaker-original {
    color: var(--speaker-dark);
  }

  .speaker-item input {
    flex: 1;
    padding: 8px 12px;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    background: var(--surface-color);
    color: var(--text-primary);
    font-size: 14px;
  }

  .save-speakers-button {
    margin-top: 16px;
    padding: 10px 20px;
    background: var(--primary-color);
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: background-color 0.2s ease;
  }

  .save-speakers-button:hover {
    background: var(--primary-hover);
  }

  .error-message {
    color: var(--error-color);
    font-size: 14px;
    margin: 8px 0;
  }

  .error-message.small {
    font-size: 12px;
    margin: 4px 0;
  }

  @media (max-width: 768px) {
    .segment-content {
      grid-template-columns: auto auto 1fr;
      gap: 8px;
      padding: 8px;
    }

    .segment-speaker {
      font-size: 11px;
      padding: 2px 6px;
    }

    .segment-text {
      padding-left: 8px;
    }

    .segment-text::before {
      height: 16px;
    }

    .segment-time {
      font-size: 11px;
    }

    .segment-speaker {
      font-size: 12px;
    }

    .segment-text {
      font-size: 13px;
    }

    .transcript-actions {
      flex-direction: column;
    }

    .speaker-item {
      flex-direction: column;
      align-items: stretch;
    }

    .speaker-original {
      min-width: auto;
    }
  }
</style>