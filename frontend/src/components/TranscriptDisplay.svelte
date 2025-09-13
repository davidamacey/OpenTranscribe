<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { slide } from 'svelte/transition';
  import { getSpeakerColor } from '$lib/utils/speakerColors';
  import ReprocessButton from './ReprocessButton.svelte';
  import ScrollbarIndicator from './ScrollbarIndicator.svelte';
  import TranscriptSearch from './TranscriptSearch.svelte';
  import { type TranscriptSegment } from '$lib/utils/scrollbarCalculations';
  import { downloadStore } from '$stores/downloads';
  import { toastStore } from '$stores/toast';
  import { highlightTextWithMatches, highlightSpeakerName, type SearchMatch } from '$lib/utils/searchHighlight';
  
  export let file: any = null;
  export let isEditingTranscript: boolean = false;
  export let editedTranscript: string = '';
  export let savingTranscript: boolean = false;
  export let savingSpeakers: boolean = false;
  export let transcriptError: string = '';
  export let editingSegmentId: string | number | null = null;
  export let editingSegmentText: string = '';
  export let isEditingSpeakers: boolean = false;
  export let speakerList: any[] = [];
  export let reprocessing: boolean = false;
  export let currentTime: number = 0;

  const dispatch = createEventDispatcher();
  
  // Download state management
  let downloadState = $downloadStore;
  $: downloadState = $downloadStore;
  $: currentDownload = downloadState[file?.id];
  $: isDownloading = currentDownload && ['preparing', 'processing', 'downloading'].includes(currentDownload.status);

  // Scrollbar indicator state
  let transcriptContainer: HTMLElement | null = null;
  let scrollbarIndicatorEnabled: boolean = true;

  // Reactive transcript segments for scrollbar calculations
  $: transcriptSegments = (file?.transcript_segments || []) as TranscriptSegment[];

  // Search functionality state
  let searchMatches: SearchMatch[] = [];
  let currentMatchIndex = -1;
  let totalMatches = 0;
  let searchQuery = '';

  // Handle scrollbar indicator click to seek to playhead
  function handleSeekToPlayhead(event: CustomEvent) {
    const { currentTime: seekTime, targetSegment } = event.detail;
    
    if (targetSegment) {
      // Scroll to the current segment
      const segmentElement = document.querySelector(`[data-segment-id="${targetSegment.id || `${targetSegment.start_time}-${targetSegment.end_time}`}"]`);
      if (segmentElement) {
        segmentElement.scrollIntoView({ 
          behavior: 'smooth', 
          block: 'center',
          inline: 'nearest'
        });
      }
    }
    
    // Also dispatch to parent for potential video seeking
    dispatch('seekToPlayhead', { time: seekTime, segment: targetSegment });
  }

  // Check if scrollbar indicator should be enabled
  $: {
    scrollbarIndicatorEnabled = !!(
      transcriptSegments && 
      transcriptSegments.length > 10 && // Only show for transcripts with substantial content
      currentTime >= 0 &&
      !isEditingTranscript // Hide during transcript editing
    );
  }

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

  // Search event handlers
  function handleSearchResults(event: CustomEvent) {
    const { matches, currentMatch, totalMatches: total, query } = event.detail;
    searchMatches = matches;
    currentMatchIndex = currentMatch - 1; // Convert to 0-based index
    totalMatches = total;
    searchQuery = query;
  }

  function handleNavigateToMatch(event: CustomEvent) {
    const { match, segment, segmentIndex, autoSeek } = event.detail;
    
    // Only seek if explicitly requested (e.g., user clicks on a segment)
    // Don't auto-seek when just navigating through search results
    if (autoSeek && match.type === 'text') {
      handleSegmentClick(segment.start_time);
    }
    
    // The scrolling and highlighting is handled by the search component
  }

  async function downloadFile() {
    if (!file || !file.id) {
      toastStore.error('File information not available');
      return;
    }
    
    const fileId = file.id.toString();
    const filename = file.filename;
    
    // Check if download is already in progress
    if (isDownloading) {
      toastStore.warning(`${filename} is already being processed. Please wait for it to complete.`);
      return;
    }
    
    // Start download tracking
    const canStart = downloadStore.startDownload(fileId, filename);
    if (!canStart) return;
    
    try {
      // Get auth token from localStorage
      const token = localStorage.getItem('token');
      
      if (!token) {
        downloadStore.updateStatus(fileId, 'error', undefined, 'No authentication token found. Please log in again.');
        return;
      }
      
      downloadStore.updateStatus(fileId, 'processing');
      
      // Determine if this is a video with subtitles for enhanced processing
      const isVideo = file.content_type?.startsWith('video/');
      const hasSubtitles = file.status === 'completed' && file.transcript_segments?.length > 0;
      
      // For cached videos, add a small delay to ensure download state is properly initialized
      // before WebSocket 'completed' message arrives
      if (isVideo && hasSubtitles) {
        await new Promise(resolve => setTimeout(resolve, 100));
      }
      
      // Build download URL
      let downloadUrl = `/api/files/${fileId}/download-with-token?token=${encodeURIComponent(token)}`;
      let downloadFilename = filename;
      
      // For videos with subtitles, include subtitle embedding parameters
      if (isVideo && hasSubtitles) {
        downloadUrl += '&include_speakers=true';
        // Generate filename with subtitles suffix
        const baseName = filename.includes('.') ? filename.substring(0, filename.lastIndexOf('.')) : filename;
        const extension = filename.includes('.') ? filename.substring(filename.lastIndexOf('.')) : '.mp4';
        downloadFilename = `${baseName}_with_subtitles${extension}`;
      }
      
      downloadStore.updateStatus(fileId, 'downloading');
      
      // Create download link
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = downloadFilename;
      link.style.display = 'none';
      document.body.appendChild(link);
      
      // Trigger download
      link.click();
      
      // Clean up
      document.body.removeChild(link);
      
      // For non-video files or videos without subtitles, mark as completed quickly
      if (!isVideo || !hasSubtitles) {
        setTimeout(() => {
          downloadStore.updateStatus(fileId, 'completed');
        }, 2000);
      } else {
        // For videos with subtitles, monitor the download progress
        // Set up an interval to check if the browser has started downloading
        let checkCount = 0;
        const checkInterval = setInterval(() => {
          checkCount++;
          const currentStatus = downloadStore.getDownloadStatus(fileId);
          
          // If status changed to completed or error, clear the interval
          if (!currentStatus || currentStatus.status === 'completed' || currentStatus.status === 'error') {
            clearInterval(checkInterval);
            return;
          }
          
          // For cached videos, the download starts almost immediately
          // If we're still in processing after 3 seconds, it's likely done
          if (checkCount >= 3 && ['processing', 'downloading'].includes(currentStatus.status)) {
            downloadStore.updateStatus(fileId, 'completed');
            clearInterval(checkInterval);
            return;
          }
          
          // For actual processing, give it more time (up to 60 seconds)
          if (checkCount >= 60 && ['processing', 'downloading'].includes(currentStatus.status)) {
            downloadStore.updateStatus(fileId, 'completed');
            clearInterval(checkInterval);
          }
        }, 1000); // Check every second
      }
      
    } catch (error) {
      console.error('Download error:', error);
      const errorMessage = error instanceof Error ? error.message : 'Download failed';
      downloadStore.updateStatus(fileId, 'error', undefined, errorMessage);
    }
  }

</script>

<section class="transcript-column">
  <div class="transcript-header">
    <!-- Search component moved to header -->
    <TranscriptSearch 
      {transcriptSegments}
      {speakerList}
      disabled={!file?.transcript_segments?.length}
      on:searchResults={handleSearchResults}
      on:navigateToMatch={handleNavigateToMatch}
    />
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
      <div bind:this={transcriptContainer} class="transcript-display-container">
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
                      class="cancel-button" 
                      on:click={cancelEditSegment}
                      title="Cancel editing this segment and discard changes"
                    >Cancel</button>
                    <button 
                      class="save-button" 
                      on:click={() => saveSegment(segment)} 
                      disabled={savingTranscript}
                      title="Save changes to this segment"
                    >
                      {savingTranscript ? 'Saving...' : 'Save'}
                    </button>
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
                    {@html highlightSpeakerName(
                      segment.speaker?.display_name || segment.speaker?.name || segment.speaker_label || 'Unknown',
                      searchQuery,
                      file.transcript_segments.indexOf(segment),
                      searchMatches,
                      currentMatchIndex
                    )}
                  </div>
                  <div class="segment-text">
                    {@html highlightTextWithMatches(
                      segment.text,
                      searchQuery,
                      file.transcript_segments.indexOf(segment),
                      searchMatches,
                      currentMatchIndex
                    )}
                  </div>
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
        
        <!-- Scrollbar Position Indicator - Inside transcript-display-container for proper positioning -->
        {#if scrollbarIndicatorEnabled}
          <ScrollbarIndicator 
            {currentTime}
            {transcriptSegments}
            containerElement={transcriptContainer?.querySelector('.transcript-display')}
            disabled={isEditingTranscript || !file?.transcript_segments?.length}
            on:seekToPlayhead={handleSeekToPlayhead}
          />
        {/if}
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
            class:downloading={isDownloading}
            class:processing={currentDownload?.status === 'processing'}
            disabled={isDownloading}
            on:click={downloadFile}
            title={isDownloading ? 
              `Processing video with subtitles (may take 1-2 minutes for large files)...` : 
              (file.content_type?.startsWith('video/') && file.status === 'completed' ? 'Download video (subtitles will be embedded if transcript exists)' : 'Download media file')}
          >
            {#if isDownloading}
              {#if currentDownload?.status === 'preparing'}
                <svg class="spinner" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M21 12a9 9 0 11-6.219-8.56"/>
                </svg>
                Preparing...
              {:else if currentDownload?.status === 'processing'}
                <svg class="spinner" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M21 12a9 9 0 11-6.219-8.56"/>
                </svg>
                Processing...
              {:else if currentDownload?.status === 'downloading'}
                <svg class="spinner" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M21 12a9 9 0 11-6.219-8.56"/>
                </svg>
                Processing...
              {/if}
            {:else}
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
            {/if}
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
                      placeholder={speaker.confidence && speaker.confidence >= 0.75 && speaker.suggested_name && !speaker.display_name ? speaker.suggested_name : (speaker.suggested_name ? `Suggested: ${speaker.suggested_name}` : `Label ${speaker.name}`)}
                      title="Enter a custom name for {speaker.name} (e.g., 'John Smith', 'Interviewer', etc.)"
                      class:suggested-high={speaker.confidence && speaker.confidence >= 0.75 && speaker.suggested_name && !speaker.display_name}
                      class:suggested-medium={speaker.confidence && speaker.confidence >= 0.5 && speaker.confidence < 0.75 && speaker.suggested_name && !speaker.display_name}
                      data-speaker-id={speaker.id}
                      on:focus={() => {
                        if (speaker.confidence && speaker.confidence >= 0.75 && speaker.suggested_name && !speaker.display_name) {
                          speaker.display_name = speaker.suggested_name;
                        }
                      }}
                    />
                    
                    <!-- Unified Suggestions Section -->
                    {#if speaker.suggested_name || (speaker.cross_video_matches && speaker.cross_video_matches.length > 0)}
                      {@const hasLLMSuggestion = speaker.suggested_name && speaker.confidence}
                      {@const validEmbeddingMatches = speaker.cross_video_matches ? speaker.cross_video_matches.filter(match => {
                        const suggestedName = match.display_name || match.speaker_name;
                        return suggestedName && suggestedName.trim() && !suggestedName.startsWith('SPEAKER_');
                      }) : []}
                      {@const totalSuggestions = (hasLLMSuggestion ? 1 : 0) + validEmbeddingMatches.length}
                      
                      {#if totalSuggestions > 0}
                      <div class="suggestions-section">
                        <button 
                          class="suggestions-toggle"
                          on:click={() => speaker.showSuggestions = !speaker.showSuggestions}
                          title="View available suggestions for speaker identification"
                        >
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class:rotated={speaker.showSuggestions}>
                            <polyline points="6 9 12 15 18 9"></polyline>
                          </svg>
                          {totalSuggestions} suggestion{totalSuggestions !== 1 ? 's' : ''} available
                          {#if !speaker.display_name}
                            <span class="expand-hint">(click to expand)</span>
                          {/if}
                        </button>
                        
                        {#if speaker.showSuggestions}
                          <div class="suggestions-dropdown" transition:slide={{ duration: 200 }}>
                            <!-- Horizontal chip layout -->
                            <div class="suggestion-chips-container">
                              {#if hasLLMSuggestion}
                                <div class="chip-row">
                                  <span class="chip-label">AI:</span>
                                  <button 
                                    class="suggestion-chip llm-chip"
                                    class:high-confidence={speaker.confidence >= 0.85}
                                    class:medium-confidence={speaker.confidence >= 0.7 && speaker.confidence < 0.85}
                                    class:low-confidence={speaker.confidence < 0.7}
                                    on:click={() => { speaker.display_name = speaker.suggested_name; }}
                                    title="AI suggested based on conversation context"
                                  >
                                    {speaker.suggested_name}
                                    <span class="chip-confidence">{Math.round(speaker.confidence * 100)}%</span>
                                  </button>
                                </div>
                              {/if}
                              
                              {#if validEmbeddingMatches.length > 0}
                                <div class="chip-row">
                                  <span class="chip-label">Voice:</span>
                                  <div class="chips-wrap">
                                    {#each validEmbeddingMatches.slice(0, 6) as match}
                                      {@const suggestedName = match.display_name || match.speaker_name}
                                      <button 
                                        class="suggestion-chip voice-chip"
                                        class:high-confidence={match.confidence >= 0.85}
                                        class:medium-confidence={match.confidence >= 0.7 && match.confidence < 0.85}
                                        class:low-confidence={match.confidence < 0.7}
                                        on:click={() => { speaker.display_name = suggestedName; }}
                                        title="Voice match from: {match.media_file_title}"
                                      >
                                        {suggestedName}
                                        <span class="chip-confidence">{Math.round(match.confidence * 100)}%</span>
                                      </button>
                                    {/each}
                                    {#if validEmbeddingMatches.length > 6}
                                      <span class="more-chips">+{validEmbeddingMatches.length - 6}</span>
                                    {/if}
                                  </div>
                                </div>
                              {/if}
                            </div>
                          </div>
                        {/if}
                      </div>
                      {/if}
                    {/if}
                    
                    <!-- Cross-video speaker detection - Below text input -->
                    {#if speaker.cross_video_matches && speaker.cross_video_matches.length > 0}
                      <div class="cross-video-compact">
                        <div class="compact-header" role="button" tabindex="0" on:click={() => speaker.showMatches = !speaker.showMatches} on:keydown={(e) => e.key === 'Enter' && (speaker.showMatches = !speaker.showMatches)}>
                          <span class="compact-text">
                            {#if speaker.display_name && speaker.display_name.trim() !== '' && !speaker.display_name.startsWith('SPEAKER_')}
                              "{speaker.display_name}" appears in {speaker.cross_video_matches.length + 1} video{speaker.cross_video_matches.length > 0 ? 's' : ''}
                            {:else}
                              {speaker.name} matches {speaker.cross_video_matches.length} other speaker{speaker.cross_video_matches.length > 1 ? 's' : ''}
                            {/if}
                          </span>
                          <div class="compact-controls">
                            <button 
                              class="info-btn-consistent"
                              title="Click for details"
                              on:click|stopPropagation={() => speaker.showMatches = !speaker.showMatches}
                            >
                              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <circle cx="12" cy="12" r="10"></circle>
                                <line x1="12" y1="16" x2="12" y2="12"></line>
                                <line x1="12" y1="8" x2="12.01" y2="8"></line>
                              </svg>
                            </button>
                            <button 
                              class="dropdown-arrow"
                              title="Show/hide matches"
                              on:click|stopPropagation={() => speaker.showMatches = !speaker.showMatches}
                            >
                              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class:rotated={speaker.showMatches}>
                                <polyline points="6 9 12 15 18 9"></polyline>
                              </svg>
                            </button>
                          </div>
                        </div>
                        
                        {#if speaker.showMatches}
                          <div class="compact-dropdown" transition:slide={{ duration: 200 }}>
                            {#if speaker.display_name && speaker.display_name.trim() !== '' && !speaker.display_name.startsWith('SPEAKER_')}
                              {@const sortedMatches = speaker.cross_video_matches.sort((a, b) => b.confidence - a.confidence)}
                              {@const highConfidence = sortedMatches.filter(m => m.confidence >= 0.90)}
                              {@const mediumConfidence = sortedMatches.filter(m => m.confidence >= 0.75 && m.confidence < 0.90)}
                              {@const visibleMatches = [...highConfidence.slice(0, 5), ...mediumConfidence.slice(0, 3)].slice(0, 8)}
                              {@const remainingCount = sortedMatches.length - visibleMatches.length}
                              
                              <!-- After labeling: Show file list -->
                              <div class="matches-help">
                                Files where "{speaker.display_name}" appears:
                              </div>
                              <div class="compact-matches">
                                <!-- Current file -->
                                <div class="compact-match current-file">
                                  <span class="match-text">This video (current)</span>
                                  <span class="match-confidence">✓ Labeled</span>
                                </div>
                                
                                <div class="matches-scroll-container">
                                {#each visibleMatches as match}
                                  <div class="compact-match" title={match.media_file_title}>
                                    <span class="match-text">{match.media_file_title.length > 20 ? match.media_file_title.substring(0, 20) + '...' : match.media_file_title}</span>
                                    <span class="match-confidence">
                                      ✓ {Math.round(match.confidence * 100)}%
                                    </span>
                                  </div>
                                {/each}
                              </div>
                                
                                {#if remainingCount > 0}
                                  <div class="more-matches-compact">
                                    {#if remainingCount < 10}
                                      +{remainingCount} more ({highConfidence.length} high confidence, {mediumConfidence.length} medium)
                                    {:else if remainingCount < 50}
                                      +{remainingCount} more matches (showing top by confidence)
                                    {:else}
                                      +{remainingCount} more matches (showing most relevant)
                                    {/if}
                                  </div>
                                {/if}
                              </div>
                            {:else}
                              {@const sortedMatches = speaker.cross_video_matches.sort((a, b) => b.confidence - a.confidence)}
                              {@const topMatches = sortedMatches.slice(0, 5)}
                              {@const remainingCount = sortedMatches.length - topMatches.length}
                              
                              <!-- Embedding-based Speaker Suggestions -->
                              <div class="embedding-suggestion-info">
                                <div class="embedding-badge">
                                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                    <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
                                  </svg>
                                  Voice Embedding Matches
                                </div>
                                <div class="embedding-suggestions">
                                  {#each topMatches as match}
                                    {@const suggestedName = match.display_name || match.speaker_name}
                                    {#if suggestedName && suggestedName.trim() && !suggestedName.startsWith('SPEAKER_')}
                                      <button 
                                        class="embedding-suggestion-button"
                                        class:high-confidence={match.confidence >= 0.85}
                                        class:medium-confidence={match.confidence >= 0.7 && match.confidence < 0.85}
                                        class:low-confidence={match.confidence < 0.7}
                                        on:click={() => {
                                          speaker.display_name = suggestedName;
                                        }}
                                        title="Use voice embedding match: {suggestedName} from {match.media_file_title}"
                                      >
                                        <span class="suggestion-name">"{suggestedName}"</span>
                                        <span class="embedding-confidence">{Math.round(match.confidence * 100)}%</span>
                                      </button>
                                    {/if}
                                  {/each}
                                </div>
                                {#if topMatches.some(match => {
                                  const suggestedName = match.display_name || match.speaker_name;
                                  return suggestedName && suggestedName.trim() && !suggestedName.startsWith('SPEAKER_');
                                })}
                                  <div class="embedding-help">
                                    Click a name above to use voice-based speaker matching from other videos
                                  </div>
                                {:else}
                                  <div class="no-matches-message">
                                    No labeled speakers found in other videos. 
                                    Label speakers in other videos first to enable cross-video matching.
                                  </div>
                                {/if}
                              </div>
                              
                              {#if remainingCount > 0}
                                <div class="more-matches-compact">
                                  {#if remainingCount < 10}
                                    +{remainingCount} more embedding matches available
                                  {:else if remainingCount < 50}
                                    +{remainingCount} more matches (showing highest confidence)
                                  {:else}
                                    +{remainingCount} more matches (top confidence shown)
                                  {/if}
                                </div>
                              {/if}
                            {/if}
                          </div>
                        {/if}
                      </div>
                    {/if}
                  </div>
                </div>
              {/each}
              <button 
                class="save-speakers-button" 
                on:click={saveSpeakerNames}
                disabled={savingSpeakers}
                title="Save all speaker name changes and update the transcript"
              >
                {#if savingSpeakers}
                  <svg class="spinner" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21 12a9 9 0 11-6.219-8.56"/>
                  </svg>
                  Saving...
                {:else}
                  Save Speaker Names
                {/if}
              </button>
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
    position: relative; /* Enable positioning for external indicator */
  }

  .transcript-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;
    min-height: 32px;
  }

  .transcript-column h4 {
    margin: 0;
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
    background: var(--surface-color);
    color: var(--text-color);
    border: 1px solid var(--border-color);
    padding: 0.6rem 1.2rem;
    border-radius: 10px;
    cursor: pointer;
    font-weight: 500;
    transition: all 0.2s ease;
    font-size: 0.95rem;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }

  .cancel-button:hover {
    background: #3b82f6;
    color: white;
    border-color: #3b82f6;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }
  
  .cancel-button:active {
    transform: translateY(0);
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }

  .transcript-display-container {
    position: relative;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    background: var(--surface-color);
  }

  .transcript-display {
    max-height: 600px;
    overflow-y: auto;
    position: relative;
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
    justify-content: flex-end;
    gap: 0.5rem;
    margin-top: 8px;
  }

  .segment-edit-actions .save-button, 
  .segment-edit-actions .cancel-button {
    padding: 0.4rem 0.8rem;
    border-radius: 10px;
    font-size: 0.85rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    border: none;
    min-width: 60px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  .segment-edit-actions .save-button {
    background: #3b82f6;
    color: white;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }

  .segment-edit-actions .save-button:hover:not(:disabled) {
    background: #2563eb;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }

  .segment-edit-actions .save-button:active:not(:disabled) {
    transform: translateY(0);
  }

  .segment-edit-actions .save-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .segment-edit-actions .cancel-button {
    background: var(--surface-color);
    color: var(--text-color);
    border: 1px solid var(--border-color);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }

  .segment-edit-actions .cancel-button:hover {
    background: #3b82f6;
    color: white;
    border-color: #3b82f6;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }
  
  .segment-edit-actions .cancel-button:active {
    transform: translateY(0);
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
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


  .speaker-item input.suggested-high {
    border-color: var(--success-color);
    border-width: 2px;
  }

  .speaker-item input.suggested-medium {
    border-color: var(--warning-color);
    border-width: 2px;
  }

  /* LLM Suggestion Interface */
  .llm-suggestion-info {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-top: 0.5rem;
    padding: 0.75rem;
    background: var(--surface-color, #f8fafc);
    border: 1px solid var(--border-color, #e2e8f0);
    border-radius: 8px;
    border-left: 4px solid var(--primary-color, #3b82f6);
  }

  :global(.dark) .llm-suggestion-info {
    background: var(--surface-color, #1e293b);
    border-color: var(--border-color, #475569);
  }

  .llm-badge {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--primary-color, #3b82f6);
    text-transform: uppercase;
    letter-spacing: 0.025em;
  }

  .llm-badge svg {
    color: var(--primary-color, #3b82f6);
  }

  .suggestion-button {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.5rem 0.75rem;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-weight: 500;
    transition: all 0.2s ease;
    position: relative;
    color: white;
  }

  .suggestion-button:hover {
    transform: translateY(-1px);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }

  /* Color coding for LLM suggestions based on confidence */
  .suggestion-button.high-confidence {
    background: #059669;
  }

  .suggestion-button.high-confidence:hover {
    background: #047857;
  }

  .suggestion-button.medium-confidence {
    background: #0891b2;
  }

  .suggestion-button.medium-confidence:hover {
    background: #0e7490;
  }

  .suggestion-button.low-confidence {
    background: #7c3aed;
  }

  .suggestion-button.low-confidence:hover {
    background: #6d28d9;
  }

  .confidence-score {
    font-size: 0.75rem;
    background: rgba(255, 255, 255, 0.2);
    padding: 0.125rem 0.375rem;
    border-radius: 12px;
    font-weight: 600;
  }

  .cross-video-note {
    font-size: 0.7rem;
    color: var(--text-secondary-color, #6b7280);
    font-style: italic;
  }

  /* Embedding Suggestion Interface */
  .embedding-suggestion-info {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-top: 0.75rem;
    padding: 0.75rem;
    background: var(--surface-color, #f1f5f9);
    border: 1px solid var(--border-color, #e2e8f0);
    border-radius: 8px;
    border-left: 4px solid var(--accent-color, #8b5cf6);
  }

  :global(.dark) .embedding-suggestion-info {
    background: var(--surface-color, #1e293b);
    border-color: var(--border-color, #475569);
  }

  .embedding-badge {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--accent-color, #8b5cf6);
    text-transform: uppercase;
    letter-spacing: 0.025em;
  }

  .embedding-badge svg {
    color: var(--accent-color, #8b5cf6);
  }

  .embedding-suggestions {
    display: flex;
    flex-direction: column;
    gap: 0.375rem;
  }

  .embedding-suggestion-button {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.5rem 0.75rem;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-weight: 500;
    transition: all 0.2s ease;
    color: white;
  }

  .embedding-suggestion-button:hover {
    transform: translateY(-1px);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }

  /* Color coding based on confidence */
  .embedding-suggestion-button.high-confidence {
    background: #059669;
  }

  .embedding-suggestion-button.high-confidence:hover {
    background: #047857;
  }

  .embedding-suggestion-button.medium-confidence {
    background: #0891b2;
  }

  .embedding-suggestion-button.medium-confidence:hover {
    background: #0e7490;
  }

  .embedding-suggestion-button.low-confidence {
    background: #7c3aed;
  }

  .embedding-suggestion-button.low-confidence:hover {
    background: #6d28d9;
  }

  .embedding-confidence {
    font-size: 0.75rem;
    background: rgba(255, 255, 255, 0.2);
    padding: 0.125rem 0.375rem;
    border-radius: 12px;
    font-weight: 600;
  }

  .embedding-help {
    font-size: 0.7rem;
    color: var(--text-secondary-color, #6b7280);
    text-align: center;
    font-style: italic;
  }

  .no-matches-message {
    font-size: 0.75rem;
    color: var(--warning-color, #f59e0b);
    text-align: center;
    font-style: italic;
    padding: 8px;
    background: var(--warning-bg, rgba(245, 158, 11, 0.1));
    border-radius: 4px;
    border: 1px solid var(--warning-border, rgba(245, 158, 11, 0.3));
  }
  
  


  .confidence-badge {
    padding: 0.2rem 0.4rem;
    border-radius: 4px;
    color: white;
    font-weight: 500;
    font-size: 0.75rem;
  }


  .match-confidence {
    font-size: 0.75rem;
    font-weight: normal;
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

  .suggestion-help-text {
    font-size: 0.7rem;
    color: var(--text-color-secondary);
    background: rgba(59, 130, 246, 0.05);
    padding: 0.4rem;
    border-radius: 4px;
    margin-top: 0.4rem;
    border-left: 3px solid var(--primary-color);
  }

  .cross-video-reference {
    font-size: 0.7rem;
    color: var(--text-color-secondary);
    font-style: italic;
    margin-top: 0.2rem;
  }

  .save-speakers-button {
    margin-top: 16px;
    padding: 0.6rem 1.2rem;
    background: #3b82f6;
    color: white;
    border: none;
    border-radius: 10px;
    font-size: 0.95rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }

  .save-speakers-button:hover {
    background: #2563eb;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }
  
  .save-speakers-button:active {
    transform: translateY(0);
  }
  
  .save-speakers-button:disabled {
    background: #94a3b8;
    cursor: not-allowed;
    transform: none;
    box-shadow: none;
  }
  
  .save-speakers-button:disabled:hover {
    background: #94a3b8;
    transform: none;
    box-shadow: none;
  }
  
  .save-speakers-button .spinner {
    margin-right: 0.5rem;
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
  
  /* Enhanced download button styles */
  .download-button:disabled {
    opacity: 0.7;
    cursor: not-allowed;
  }
  
  .download-button.downloading {
    background: var(--primary-color);
    color: white;
    border-color: var(--primary-color);
  }
  
  .download-button.processing {
    background: var(--warning-color, #f59e0b);
    color: white;
    border-color: var(--warning-color, #f59e0b);
  }
  
  .spinner {
    animation: spin 1s linear infinite;
  }
  
  @keyframes spin {
    from {
      transform: rotate(0deg);
    }
    to {
      transform: rotate(360deg);
    }
  }
  
  /* Compact cross-video UI styles */
  .cross-video-compact {
    margin-top: 0.3rem;
    padding: 0.5rem;
    background-color: var(--background-main);
    border: 1px solid var(--border-color);
    border-radius: 4px;
    font-size: 0.75rem;
  }
  
  .compact-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    cursor: pointer;
    user-select: none;
  }
  
  .compact-text {
    color: var(--text-color);
    flex: 1;
    font-size: 0.7rem;
  }
  
  .compact-controls {
    display: flex;
    align-items: center;
    gap: 0.25rem;
  }
  
  .info-btn-consistent, .dropdown-arrow {
    background: none;
    border: none;
    cursor: pointer;
    padding: 0.15rem;
    border-radius: 3px;
    color: var(--text-color-secondary);
    transition: background-color 0.2s ease;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  
  .info-btn-consistent:hover, .dropdown-arrow:hover {
    background-color: var(--border-color-soft);
  }
  
  .dropdown-arrow svg {
    transition: transform 0.2s ease;
  }
  
  .dropdown-arrow svg.rotated {
    transform: rotate(180deg);
  }
  
  .compact-dropdown {
    margin-top: 0.5rem;
    padding-top: 0.5rem;
    border-top: 1px solid var(--border-color-soft);
  }
  
  .matches-help {
    font-size: 0.65rem;
    color: var(--text-color-secondary);
    margin-bottom: 0.3rem;
    font-style: italic;
  }
  
  .compact-matches {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
  }
  
  .compact-match {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.15rem 0.35rem;
    background-color: var(--background-alt);
    border: 1px solid var(--border-color-soft);
    border-radius: 3px;
    font-size: 0.65rem;
    cursor: help;
    transition: background-color 0.2s ease;
  }
  
  .compact-match:hover {
    background-color: var(--background-main);
    border-color: var(--border-color);
  }
  
  .compact-match.current-file {
    background-color: rgba(34, 197, 94, 0.1);
    border-color: var(--success-color);
    font-weight: 500;
  }
  
  .match-text {
    flex: 1;
    color: var(--text-color);
  }
  
  .match-confidence {
    font-weight: 500;
    font-size: 0.65rem;
    color: var(--success-color);
  }
  
  .more-matches-compact {
    padding: 0.2rem 0.4rem;
    text-align: center;
    font-size: 0.65rem;
    color: var(--text-color-secondary);
    font-style: italic;
  }
  
  /* Scrollable container for large match sets */
  .matches-scroll-container {
    max-height: 200px;
    overflow-y: auto;
    border: 1px solid var(--border-color-soft);
    border-radius: 3px;
    padding: 0.2rem;
  }
  
  .matches-scroll-container::-webkit-scrollbar {
    width: 6px;
  }
  
  .matches-scroll-container::-webkit-scrollbar-track {
    background: var(--background-alt);
    border-radius: 3px;
  }
  
  .matches-scroll-container::-webkit-scrollbar-thumb {
    background: var(--border-color);
    border-radius: 3px;
  }
  
  .matches-scroll-container::-webkit-scrollbar-thumb:hover {
    background: var(--text-color-secondary);
  }

  /* New Combined Suggestions Styling */
  .embedding-quick-suggestions {
    margin-top: 0.4rem;
    padding: 0.4rem;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    background: var(--surface-color);
  }

  .embedding-pills {
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem;
    align-items: center;
    margin-top: 0.3rem;
  }

  .suggestion-pill.embedding-pill.high-confidence {
    background: #059669;
    color: white;
  }

  .suggestion-pill.embedding-pill.medium-confidence {
    background: #0891b2;
    color: white;
  }

  .suggestion-pill.embedding-pill.low-confidence {
    background: #7c3aed;
    color: white;
  }

  .more-suggestions {
    font-size: 0.7rem;
    color: var(--text-secondary-color);
    font-style: italic;
  }

  /* Collapsible suggestions styling */
  .suggestions-collapsed {
    margin-top: 0.4rem;
  }

  .suggestions-toggle {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.3rem 0.5rem;
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 4px;
    color: var(--text-secondary-color);
    font-size: 0.75rem;
    cursor: pointer;
    transition: all 0.2s ease;
    width: 100%;
    text-align: left;
  }

  .suggestions-toggle:hover {
    background: var(--surface-hover);
    color: var(--text-primary);
  }

  .suggestions-toggle svg {
    transition: transform 0.2s ease;
    flex-shrink: 0;
  }

  .suggestions-toggle svg.rotated {
    transform: rotate(180deg);
  }

  .suggestions-dropdown {
    margin-top: 0.3rem;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    background: var(--surface-color);
    padding: 0.4rem;
  }

  .suggestion-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.3rem;
  }

  .suggestion-item:last-child {
    margin-bottom: 0;
  }

  .suggestion-type {
    font-size: 0.7rem;
    font-weight: 600;
    color: var(--text-secondary-color);
    min-width: 40px;
  }

  .suggestion-pill-small {
    padding: 0.2rem 0.4rem;
    border: none;
    border-radius: 12px;
    font-size: 0.7rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    color: white;
  }

  .suggestion-pill-small.llm-pill {
    background: var(--primary-color);
  }

  .suggestion-pill-small.embedding-pill.high-confidence {
    background: #059669;
  }

  .suggestion-pill-small.embedding-pill.medium-confidence {
    background: #0891b2;
  }

  .suggestion-pill-small.embedding-pill.low-confidence {
    background: #7c3aed;
  }

  .suggestion-pill-small:hover {
    transform: translateY(-1px);
    opacity: 0.9;
  }

  /* Unified Suggestions Section */
  .suggestions-section {
    margin-top: 0.4rem;
  }

  .expand-hint {
    font-size: 0.65rem;
    color: var(--text-secondary-color);
    font-style: italic;
    margin-left: 0.3rem;
  }

  /* Chip-based layout */
  .suggestion-chips-container {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .chip-row {
    display: flex;
    align-items: flex-start;
    gap: 0.5rem;
  }

  .chip-label {
    font-size: 0.7rem;
    font-weight: 600;
    color: var(--text-secondary-color);
    min-width: 35px;
    padding-top: 0.25rem;
    flex-shrink: 0;
  }

  .chips-wrap {
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem;
    align-items: center;
    flex: 1;
  }

  .suggestion-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.25rem 0.5rem;
    border: none;
    border-radius: 16px;
    font-size: 0.7rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    color: white;
    white-space: nowrap;
  }

  .suggestion-chip:hover {
    transform: translateY(-1px);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.15);
  }

  .suggestion-chip.llm-chip {
    background: var(--primary-color);
  }

  .suggestion-chip.llm-chip:hover {
    background: #2563eb;
  }

  /* Voice chip colors based on confidence */
  .suggestion-chip.voice-chip.high-confidence {
    background: #059669;
  }

  .suggestion-chip.voice-chip.high-confidence:hover {
    background: #047857;
  }

  .suggestion-chip.voice-chip.medium-confidence {
    background: #0891b2;
  }

  .suggestion-chip.voice-chip.medium-confidence:hover {
    background: #0e7490;
  }

  .suggestion-chip.voice-chip.low-confidence {
    background: #7c3aed;
  }

  .suggestion-chip.voice-chip.low-confidence:hover {
    background: #6d28d9;
  }

  .chip-confidence {
    font-size: 0.65rem;
    background: rgba(255, 255, 255, 0.25);
    padding: 0.1rem 0.3rem;
    border-radius: 8px;
    font-weight: 600;
  }

  .more-chips {
    font-size: 0.65rem;
    color: var(--text-secondary-color);
    font-style: italic;
    padding: 0.25rem 0.5rem;
  }
</style>