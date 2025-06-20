<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { slide } from 'svelte/transition';
  import { getSpeakerColor } from '$lib/utils/speakerColors';
  import ReprocessButton from './ReprocessButton.svelte';
  import axiosInstance from '$lib/axios';
  
  export let file: any = null;
  export let isEditingTranscript: boolean = false;
  export let editedTranscript: string = '';
  export let savingTranscript: boolean = false;
  export let transcriptError: string = '';
  export let editingSegmentId: string | number | null = null;
  export let editingSegmentText: string = '';
  export let isEditingSpeakers: boolean = false;
  export let speakerList: any[] = [];
  export let reprocessing: boolean = false;

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

  function handleReprocess(event: any) {
    dispatch('reprocess', event.detail);
  }

  function downloadFile() {
    if (!file || !file.id) return;
    
    try {
      // Get the auth token from localStorage
      const token = localStorage.getItem('token');
      if (!token) {
        console.error('No authentication token found');
        return;
      }

      // Create a direct download link with token parameter
      // This will use the browser's native download with progress bar
      const downloadUrl = `/api/files/${file.id}/download-with-token?token=${encodeURIComponent(token)}`;
      
      // Create a temporary link and click it
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = file.filename;
      link.style.display = 'none';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (error) {
      console.error('Error downloading file:', error);
    }
  }

  function labelAllSimilarSpeakers(speaker) {
    // Focus the input field for this speaker so user can enter a name
    // Once they save, the retroactive matching will handle updating all similar speakers
    const inputElement = document.querySelector(`input[data-speaker-id="${speaker.id}"]`);
    if (inputElement) {
      inputElement.focus();
      inputElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    
    // Show a helpful message
    console.log(`Please enter a name for ${speaker.name} to label all similar speakers across videos`);
  }

  function applySuggestion(speaker, suggestedName) {
    // Apply the suggested name to the speaker
    speaker.display_name = suggestedName;
    
    // Trigger the save speakers action to propagate the changes
    dispatch('saveSpeakerNames');
    
    // Update the UI immediately
    speakerList = speakerList.map(s => 
      s.id === speaker.id ? { ...s, display_name: suggestedName, verified: true } : s
    );
  }
</script>

<section class="transcript-column">
  <div class="transcript-header">
    <h4>Transcript</h4>
    <ReprocessButton {file} {reprocessing} on:reprocess={handleReprocess} class="reprocess-button" />
  </div>
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
          <button 
            class="action-button download-button" 
            on:click={downloadFile}
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
          </button>
        {/if}

      </div>
      
      {#if isEditingSpeakers}
        <div class="speaker-editor-container" transition:slide={{ duration: 200 }}>
          <div class="speaker-editor-header">
            <h4>Edit Speaker Names</h4>
            
            <!-- Confidence Legend - Compact Info Icon -->
            <div class="legend-info-container">
              <span class="legend-title">Color Legend</span>
              <div class="legend-info-wrapper">
                <button class="legend-info-icon" title="Click to see confidence color coding">
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="12" r="10"></circle>
                    <line x1="12" y1="16" x2="12" y2="12"></line>
                    <line x1="12" y1="8" x2="12.01" y2="8"></line>
                  </svg>
                </button>
                <div class="legend-tooltip">
                  <div class="legend-item">
                    <span class="legend-color" style="background-color: var(--success-color);"></span>
                    ≥75% High (auto-suggested)
                  </div>
                  <div class="legend-item">
                    <span class="legend-color" style="background-color: var(--warning-color);"></span>
                    50-74% Medium (verify)
                  </div>
                  <div class="legend-item">
                    <span class="legend-color" style="background-color: var(--error-color);"></span>
                    &lt;50% Low (manual)
                  </div>
                </div>
              </div>
            </div>
          </div>
          
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
                  <div class="speaker-input-wrapper">
                    <input 
                      type="text" 
                      bind:value={speaker.display_name} 
                      placeholder={speaker.confidence && speaker.confidence >= 0.75 && speaker.suggested_name && !speaker.display_name ? speaker.suggested_name : (speaker.suggested_name ? `Suggested: ${speaker.suggested_name}` : "Enter display name")}
                      title="Enter a custom name for {speaker.name} (e.g., 'John Smith', 'Interviewer', etc.)"
                      class:suggested-high={speaker.confidence && speaker.confidence >= 0.75 && speaker.suggested_name}
                      class:suggested-medium={speaker.confidence && speaker.confidence >= 0.5 && speaker.confidence < 0.75 && speaker.suggested_name}
                      data-speaker-id={speaker.id}
                      on:focus={() => {
                        if (speaker.confidence && speaker.confidence >= 0.75 && speaker.suggested_name && !speaker.display_name) {
                          speaker.display_name = speaker.suggested_name;
                        }
                      }}
                    />
                    <!-- Auto-suggestion for high confidence matches when user hasn't manually edited -->
                    {#if speaker.confidence && speaker.confidence >= 0.75 && speaker.suggested_name && !speaker.display_name}
                      <div class="auto-suggestion-info">
                        <span class="auto-suggestion-text">Auto-suggested: "{speaker.suggested_name}"</span>
                        <span class="confidence-badge" style="background-color: var(--success-color);">
                          {Math.round(speaker.confidence * 100)}% match
                        </span>
                      </div>
                    {/if}
                    
                    <!-- Manual verification needed for medium confidence -->
                    {#if speaker.confidence && speaker.confidence >= 0.5 && speaker.confidence < 0.75 && speaker.suggested_name}
                      <div class="suggestion-info">
                        <span class="suggestion-text">
                          {!speaker.display_name ? 'Suggested:' : 'Matches:'} "{speaker.suggested_name}"
                        </span>
                        <span class="confidence-badge" style="background-color: var(--warning-color);">
                          {Math.round(speaker.confidence * 100)}% match - {!speaker.display_name ? 'verify' : 'verified'}
                        </span>
                        {#if speaker.cross_video_matches && speaker.cross_video_matches.length > 0}
                          {#each speaker.cross_video_matches as match}
                            {#if match.display_name === speaker.suggested_name}
                              <span class="from-video">from "{match.media_file_title.length > 25 ? match.media_file_title.substring(0, 25) + '...' : match.media_file_title}"</span>
                            {/if}
                          {/each}
                        {/if}
                      </div>
                    {/if}
                    
                    <!-- Clickable suggestions below input -->
                    {#if speaker.suggested_name && !speaker.display_name}
                      <div class="clickable-suggestions">
                        <div class="suggestion-label">Quick select:</div>
                        <button 
                          class="suggestion-pill"
                          on:click={() => applySuggestion(speaker, speaker.suggested_name)}
                          title="Click to apply this suggestion"
                        >
                          {speaker.suggested_name}
                          <span class="pill-confidence">
                            {Math.round(speaker.confidence * 100)}%
                          </span>
                        </button>
                        {#if speaker.cross_video_matches && speaker.cross_video_matches.length > 1}
                          {#if speaker.cross_video_matches}
                            {@const autoApplyCount = speaker.cross_video_matches.filter(m => m.confidence >= 0.75).length}
                            <span class="suggestion-note">
                              Will apply to {autoApplyCount} other video{autoApplyCount !== 1 ? 's' : ''} automatically
                            </span>
                          {/if}
                        {/if}
                      </div>
                    {/if}
                    
                    <!-- Cross-video speaker detection for unlabeled speakers -->
                    {#if speaker.cross_video_matches && speaker.cross_video_matches.length > 0 && !speaker.suggested_name && !speaker.verified}
                      <div class="cross-video-suggestion-card">
                        <div class="suggestion-header">
                          <svg class="suggestion-icon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                            <polyline points="22 4 12 14.01 9 11.01"></polyline>
                          </svg>
                          <span class="suggestion-title">Similar Speaker Detected</span>
                          <button 
                            class="expand-toggle"
                            on:click={() => speaker.showMatches = !speaker.showMatches}
                            title="Click to see details"
                          >
                            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class:rotated={speaker.showMatches}>
                              <polyline points="6 9 12 15 18 9"></polyline>
                            </svg>
                          </button>
                        </div>
                        
                        <div class="suggestion-summary">
                          {speaker.name} appears to be the same speaker in 
                          <strong>{speaker.cross_video_matches.length}</strong> 
                          other video{speaker.cross_video_matches.length > 1 ? 's' : ''}
                          {#if speaker.confidence}
                            <span class="confidence-pill" style="background-color: {speaker.confidence >= 0.75 ? 'var(--success-color)' : 'var(--warning-color)'};">
                              up to {Math.round(speaker.confidence * 100)}%
                            </span>
                          {/if}
                        </div>
                        
                        {#if speaker.showMatches}
                          <div class="matches-dropdown" transition:slide={{ duration: 200 }}>
                            {#if speaker.cross_video_matches && speaker.cross_video_matches.length > 0}
                              {@const highConfidenceMatches = speaker.cross_video_matches.filter(m => m.confidence >= 0.75)}
                              {@const mediumConfidenceMatches = speaker.cross_video_matches.filter(m => m.confidence >= 0.5 && m.confidence < 0.75)}
                              
                              <div class="matches-summary">
                                <div class="confidence-breakdown">
                                  {#if highConfidenceMatches.length > 0}
                                    <div class="confidence-group high">
                                      <span class="confidence-count" style="color: var(--success-color);">
                                        {highConfidenceMatches.length} high confidence (75%+)
                                      </span>
                                      <span class="auto-apply-note">Will auto-apply</span>
                                    </div>
                                  {/if}
                                  
                                  {#if mediumConfidenceMatches.length > 0}
                                    <div class="confidence-group medium">
                                      <span class="confidence-count" style="color: var(--warning-color);">
                                        {mediumConfidenceMatches.length} medium confidence (50-74%)
                                      </span>
                                      <span class="suggest-note">Will suggest for review</span>
                                    </div>
                                  {/if}
                                </div>
                              </div>
                            {/if}
                            
                            <div class="matches-list">
                              {#each speaker.cross_video_matches.slice(0, 5) as match}
                                <div class="match-item">
                                  <div class="match-info">
                                    <span class="match-speaker-name">{match.speaker_name}</span>
                                    <span class="match-video-title">in "{match.media_file_title.length > 30 ? match.media_file_title.substring(0, 30) + '...' : match.media_file_title}"</span>
                                  </div>
                                  <span class="match-confidence-badge" style="color: {match.confidence >= 0.75 ? 'var(--success-color)' : 'var(--warning-color)'};">
                                    {Math.round(match.confidence * 100)}%
                                    {#if match.confidence >= 0.75}
                                      <small>auto</small>
                                    {:else}
                                      <small>suggest</small>
                                    {/if}
                                  </span>
                                </div>
                              {/each}
                              
                              {#if speaker.cross_video_matches.length > 5}
                                <div class="more-matches-note">
                                  and {speaker.cross_video_matches.length - 5} more matches...
                                </div>
                              {/if}
                            </div>
                            
                            <div class="suggestion-actions">
                              <button 
                                class="label-all-btn"
                                on:click={() => labelAllSimilarSpeakers(speaker)}
                                title="Give this speaker a name and apply it to all similar matches"
                              >
                                Label This Speaker
                                <small>({highConfidenceMatches.length} auto, {mediumConfidenceMatches.length} suggest)</small>
                              </button>
                            </div>
                          </div>
                        {/if}
                      </div>
                    {/if}
                    
                    <!-- Cross-video matches info icon (show when there are matches but no suggestion display) -->
                    {#if speaker.cross_video_matches && speaker.cross_video_matches.length > 0 && (speaker.suggested_name || speaker.verified)}
                      <div class="cross-video-info-wrapper">
                        <button class="cross-video-info-icon" title="Click to see cross-video matches">
                          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <circle cx="12" cy="12" r="10"></circle>
                            <line x1="12" y1="16" x2="12" y2="12"></line>
                            <line x1="12" y1="8" x2="12.01" y2="8"></line>
                          </svg>
                        </button>
                        <div class="cross-video-tooltip">
                          <div class="tooltip-header">{speaker.name} also appears in:</div>
                          {#each speaker.cross_video_matches.slice(0, 3) as match}
                            <div class="match-detail">
                              <span class="match-speaker">{match.speaker_name}</span> in 
                              <span class="match-video">"{match.media_file_title.length > 25 ? match.media_file_title.substring(0, 25) + '...' : match.media_file_title}"</span>
                              <span class="match-confidence" style="color: {match.confidence >= 0.75 ? 'var(--success-color)' : 'var(--warning-color)'}">
                                ({Math.round(match.confidence * 100)}%)
                              </span>
                            </div>
                          {/each}
                          {#if speaker.cross_video_matches.length > 3}
                            <div class="more-matches">and {speaker.cross_video_matches.length - 3} more...</div>
                          {/if}
                        </div>
                      </div>
                    {/if}
                    
                    <!-- Fallback explanation for any colored border without visible info -->
                    {#if (speaker.confidence && speaker.confidence >= 0.5) && !speaker.suggested_name && speaker.cross_video_matches && speaker.cross_video_matches.length > 0}
                      <div class="fallback-info">
                        <span class="info-icon-inline">ℹ️</span>
                        <span class="fallback-text">This speaker matches speakers in other videos. Click the info icon above for details.</span>
                      </div>
                    {/if}
                  </div>
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

  .transcript-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
  }

  .transcript-column h4 {
    margin: 0;
    font-size: 18px;
    font-weight: 600;
    color: var(--text-primary);
  }
  
  .reprocess-button {
    margin: 0;
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
  
  .speaker-editor-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
  }
  
  .legend-info-container {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.9rem;
  }
  
  .legend-title {
    font-weight: 600;
    color: var(--text-primary);
  }
  
  .legend-info-wrapper {
    position: relative;
    display: inline-block;
  }
  
  .legend-info-icon {
    background: none;
    border: none;
    color: var(--primary-color);
    cursor: pointer;
    padding: 2px;
    border-radius: 50%;
    transition: all 0.2s ease;
  }
  
  .legend-info-icon:hover {
    background-color: var(--surface-hover);
  }
  
  .legend-info-wrapper:hover .legend-tooltip {
    display: block;
  }
  
  .legend-tooltip {
    display: none;
    position: absolute;
    top: 100%;
    left: 50%;
    transform: translateX(-50%);
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    z-index: 1000;
    padding: 0.75rem;
    min-width: 200px;
    margin-top: 4px;
  }
  
  .legend-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: var(--text-color-secondary);
    margin-bottom: 0.5rem;
    font-size: 0.8rem;
  }
  
  .legend-item:last-child {
    margin-bottom: 0;
  }
  
  .legend-color {
    width: 12px;
    height: 12px;
    border-radius: 3px;
    display: inline-block;
  }

  .speaker-editor-header h4 {
    margin: 0;
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
    align-items: flex-start;
    gap: 12px;
    padding: 16px;
    background: var(--surface-color);
    border-radius: 8px;
    border: 1px solid var(--border-color);
    margin-bottom: 4px;
  }

  .speaker-original {
    font-weight: 700;
    min-width: 120px;
    padding: 6px 12px;
    border-radius: 12px;
    border: 1px solid;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    font-size: 12px;
    text-align: center;
    transition: all 0.2s ease;
    color: var(--speaker-light);
    margin-top: 2px;
    flex-shrink: 0;
  }

  /* Dark mode speaker-original colors */
  :global([data-theme='dark']) .speaker-original {
    color: var(--speaker-dark);
  }

  .speaker-input-wrapper {
    flex: 1;
    position: relative;
    min-width: 0; /* Allow flex shrinking */
  }

  .speaker-item input {
    width: 100%;
    padding: 8px 12px;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    background: var(--surface-color);
    color: var(--text-primary);
    font-size: 14px;
  }

  .speaker-item input.suggested {
    border-color: var(--warning-color);
  }

  .speaker-item input.suggested-high {
    border-color: var(--success-color);
    border-width: 2px;
  }

  .speaker-item input.suggested-medium {
    border-color: var(--warning-color);
    border-width: 2px;
  }

  .auto-suggestion-info {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-top: 0.5rem;
    margin-bottom: 0.25rem;
    font-size: 0.8rem;
    padding: 0.5rem 0.75rem;
    background-color: rgba(34, 197, 94, 0.1);
    border-radius: 6px;
    border-left: 3px solid var(--success-color);
  }
  
  .auto-suggestion-text {
    color: var(--text-primary);
    font-weight: 500;
  }
  
  .suggestion-info {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-top: 0.5rem;
    margin-bottom: 0.25rem;
    font-size: 0.8rem;
    padding: 0.5rem 0.75rem;
    background-color: rgba(245, 158, 11, 0.1);
    border-radius: 6px;
    border-left: 3px solid var(--warning-color);
    flex-wrap: wrap;
  }
  
  .suggestion-text {
    color: var(--text-primary);
    font-weight: 500;
  }
  
  .cross-video-info-wrapper {
    position: relative;
    display: inline-block;
    margin-top: 0.75rem;
    margin-bottom: 0.25rem;
  }
  
  .cross-video-info-icon {
    background: none;
    border: none;
    color: var(--primary-color);
    cursor: pointer;
    padding: 2px;
    border-radius: 50%;
    transition: all 0.2s ease;
  }
  
  .cross-video-info-icon:hover {
    background-color: var(--surface-hover);
  }
  
  .cross-video-info-wrapper:hover .cross-video-tooltip {
    display: block;
  }
  
  .cross-video-tooltip {
    display: none;
    position: absolute;
    top: 100%;
    left: 0;
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    z-index: 1000;
    padding: 0.75rem;
    min-width: 300px;
    margin-top: 4px;
  }
  
  .tooltip-header {
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 0.5rem;
    font-size: 0.85rem;
  }
  
  .match-speaker {
    font-weight: 500;
    color: var(--primary-color);
  }
  
  .match-video {
    font-style: italic;
    color: var(--text-color-secondary);
  }

  .confidence-badge {
    padding: 0.2rem 0.4rem;
    border-radius: 4px;
    color: white;
    font-weight: 500;
    font-size: 0.75rem;
  }

  .match-detail {
    margin-bottom: 0.4rem;
    font-size: 0.8rem;
    line-height: 1.3;
  }

  .match-confidence {
    font-size: 0.75rem;
    font-weight: normal;
  }

  .more-matches {
    font-style: italic;
    color: var(--text-color-secondary);
    font-size: 0.75rem;
    margin-top: 0.25rem;
  }

  .from-video {
    color: var(--text-color-secondary);
    font-style: italic;
    font-size: 0.75rem;
  }

  .fallback-info {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-top: 0.75rem;
    margin-bottom: 0.25rem;
    padding: 0.5rem 0.75rem;
    background-color: rgba(156, 163, 175, 0.1);
    border-radius: 6px;
    border-left: 3px solid var(--border-color);
    font-size: 0.8rem;
  }

  .info-icon-inline {
    font-size: 1rem;
  }

  .fallback-text {
    color: var(--text-color-secondary);
  }

  .cross-video-suggestion-card {
    margin-top: 0.75rem;
    margin-bottom: 0.25rem;
    padding: 0.75rem;
    background-color: rgba(59, 130, 246, 0.1);
    border-radius: 8px;
    border-left: 4px solid var(--primary-color);
  }

  .suggestion-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
  }

  .suggestion-icon {
    color: var(--primary-color);
    flex-shrink: 0;
  }

  .suggestion-title {
    font-weight: 600;
    color: var(--text-primary);
    flex: 1;
    font-size: 0.9rem;
  }

  .expand-toggle {
    background: none;
    border: none;
    color: var(--text-color-secondary);
    cursor: pointer;
    transition: all 0.2s ease;
    padding: 2px;
    border-radius: 4px;
  }

  .expand-toggle:hover {
    background-color: var(--surface-hover);
    color: var(--text-primary);
  }

  .expand-toggle svg {
    transition: transform 0.2s ease;
  }

  .expand-toggle svg.rotated {
    transform: rotate(180deg);
  }

  .suggestion-summary {
    font-size: 0.85rem;
    color: var(--text-color-secondary);
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
  }

  .confidence-pill {
    padding: 0.15rem 0.4rem;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 600;
    color: white;
  }

  .matches-dropdown {
    margin-top: 0.75rem;
    padding-top: 0.75rem;
    border-top: 1px solid var(--border-light);
  }

  .matches-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
  }

  .match-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.5rem;
    background-color: var(--surface-color);
    border-radius: 6px;
    border: 1px solid var(--border-light);
  }

  .match-info {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    flex: 1;
    min-width: 0;
  }

  .match-speaker-name {
    font-weight: 600;
    color: var(--primary-color);
    font-size: 0.85rem;
  }

  .match-video-title {
    font-size: 0.8rem;
    color: var(--text-color-secondary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .match-confidence-badge {
    font-size: 0.8rem;
    font-weight: 600;
    flex-shrink: 0;
  }

  .suggestion-actions {
    display: flex;
    justify-content: center;
  }

  .label-all-btn {
    background: var(--primary-color);
    color: white;
    border: none;
    padding: 0.5rem 1rem;
    border-radius: 6px;
    font-size: 0.85rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .label-all-btn:hover {
    background: var(--primary-hover);
    transform: translateY(-1px);
  }

  .clickable-suggestions {
    margin-top: 0.5rem;
    padding: 0.5rem 0.75rem;
    background-color: rgba(99, 102, 241, 0.05);
    border-radius: 6px;
    border: 1px dashed var(--primary-color);
  }

  .suggestion-label {
    font-size: 0.75rem;
    color: var(--text-color-secondary);
    margin-bottom: 0.4rem;
    font-weight: 500;
  }

  .suggestion-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.3rem 0.6rem;
    background: var(--primary-color);
    color: white;
    border: none;
    border-radius: 16px;
    font-size: 0.8rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    margin-bottom: 0.3rem;
  }

  .suggestion-pill:hover {
    background: var(--primary-hover);
    transform: translateY(-1px);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }

  .pill-confidence {
    background: rgba(255, 255, 255, 0.2);
    padding: 0.1rem 0.3rem;
    border-radius: 8px;
    font-size: 0.7rem;
  }

  .suggestion-note {
    font-size: 0.75rem;
    color: var(--text-color-secondary);
    font-style: italic;
    display: block;
    margin-top: 0.2rem;
  }

  .matches-summary {
    margin-bottom: 0.75rem;
    padding: 0.5rem;
    background-color: var(--background-alt);
    border-radius: 6px;
  }

  .confidence-breakdown {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }

  .confidence-group {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.8rem;
  }

  .confidence-count {
    font-weight: 600;
  }

  .auto-apply-note,
  .suggest-note {
    font-size: 0.7rem;
    padding: 0.1rem 0.4rem;
    border-radius: 8px;
    font-weight: 500;
  }

  .auto-apply-note {
    background-color: rgba(34, 197, 94, 0.1);
    color: var(--success-color);
  }

  .suggest-note {
    background-color: rgba(245, 158, 11, 0.1);
    color: var(--warning-color);
  }

  .more-matches-note {
    text-align: center;
    font-style: italic;
    color: var(--text-color-secondary);
    font-size: 0.8rem;
    padding: 0.5rem;
    border-top: 1px solid var(--border-light);
    margin-top: 0.5rem;
  }

  .label-all-btn small {
    display: block;
    font-size: 0.7rem;
    opacity: 0.8;
    margin-top: 0.2rem;
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