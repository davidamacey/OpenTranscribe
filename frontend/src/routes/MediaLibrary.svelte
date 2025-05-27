<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { Link, useNavigate } from 'svelte-navigator';
  import { setupWebsocketConnection, fileStatusUpdates, lastNotification } from "$lib/websocket";
  
  // Explicitly declare props to prevent warnings
  export const location = null;
  export const condition = true;
  const navigate = useNavigate();
  
  // Modal state
  let showUploadModal = false;
  
  // Define types
  interface MediaFile {
    id: number;
    filename: string;
    status: 'pending' | 'processing' | 'completed' | 'error';
    upload_time: string;
    duration?: number;
    file_size?: number;
    content_type?: string;
    tags?: string[];
    summary?: string;
    
    // Technical metadata
    media_format?: string;
    codec?: string;
    resolution_width?: number;
    resolution_height?: number;
    frame_rate?: number;
    frame_count?: number;
    aspect_ratio?: string;
    
    // Audio specs
    audio_channels?: number;
    audio_sample_rate?: number;
    audio_bit_depth?: number;
    
    // Creation info
    creation_date?: string;
    last_modified_date?: string;
    device_make?: string;
    device_model?: string;
    
    // Content info
    title?: string;
    author?: string;
    description?: string;
  }
  
  interface DurationRange {
    min: number | null;
    max: number | null;
  }
  
  interface ResolutionRange {
    minWidth: number | null;
    maxWidth: number | null;
    minHeight: number | null;
    maxHeight: number | null;
  }
  
  interface FilterEvent {
    detail: {
      search: string;
      tags: string[];
      speaker: string | null;
      dates: DateRange;
      durationRange?: DurationRange;
      formats?: string[];
      codecs?: string[];
      resolution?: ResolutionRange;
    };
  }
  
  interface DateRange {
    from: Date | null;
    to: Date | null;
  }
  
  interface DeleteResult {
    success: boolean;
    id: number;
  }
  
  import axiosInstance from '../lib/axios';
  import { format } from 'date-fns';
  import { formatDuration } from '$lib/utils/formatting';
  
  // Import components
  import FileUploader from '../components/FileUploader.svelte';
  import FilterSidebar from '../components/FilterSidebar.svelte';
  
  // Media files state
  let files: MediaFile[] = [];
  let loading: boolean = true;
  let error: string | null = null;
  
  // Selection state
  let selectedFiles = new Set<number>();
  let isSelecting: boolean = false;
  
  // WebSocket subscription
  let unsubscribeFileStatus: () => void;
  
  // Define WebSocket update type
  interface FileStatusUpdate {
    file_id: number;
    status: 'pending' | 'processing' | 'completed' | 'error';
    progress?: number;
  }
  
  interface FileStatusUpdates {
    [key: string]: FileStatusUpdate;
  }
  
  interface Notification {
    type: string;
    data: any;
  }
  
  // Filter state
  let searchQuery: string = '';
  let selectedTags: string[] = [];
  let selectedSpeaker: string | null = null;
  let dateRange = { from: null as Date | null, to: null as Date | null };
  let durationRange = { min: null as number | null, max: null as number | null };
  let selectedFormats: string[] = [];
  let selectedCodecs: string[] = [];
  let resolutionRange = { 
    minWidth: null as number | null, 
    maxWidth: null as number | null, 
    minHeight: null as number | null, 
    maxHeight: null as number | null 
  };
  let showFilters: boolean = false; // For mobile
  
  // Fetch media files
  async function fetchFiles() {
    loading = true;
    error = null;
    
    try {
      // Build query parameters
      let params = new URLSearchParams();
      
      if (searchQuery) {
        params.append('search', searchQuery);
      }
      
      if (selectedTags.length > 0) {
        selectedTags.forEach(tag => params.append('tag', tag));
      }
      
      if (selectedSpeaker) {
        params.append('speaker', selectedSpeaker);
      }
      
      if (dateRange.from) {
        params.append('from_date', dateRange.from.toISOString());
      }
      
      if (dateRange.to) {
        params.append('to_date', dateRange.to.toISOString());
      }
      
      // Add metadata filter parameters
      if (durationRange.min !== null) {
        params.append('min_duration', durationRange.min.toString());
      }
      
      if (durationRange.max !== null) {
        params.append('max_duration', durationRange.max.toString());
      }
      
      if (selectedFormats.length > 0) {
        selectedFormats.forEach(format => params.append('format', format));
      }
      
      if (selectedCodecs.length > 0) {
        selectedCodecs.forEach(codec => params.append('codec', codec));
      }
      
      // Resolution filters
      if (resolutionRange.minWidth !== null) {
        params.append('min_width', resolutionRange.minWidth.toString());
      }
      
      if (resolutionRange.maxWidth !== null) {
        params.append('max_width', resolutionRange.maxWidth.toString());
      }
      
      if (resolutionRange.minHeight !== null) {
        params.append('min_height', resolutionRange.minHeight.toString());
      }
      
      if (resolutionRange.maxHeight !== null) {
        params.append('max_height', resolutionRange.maxHeight.toString());
      }
      
      const response = await axiosInstance.get('/files', { params });
      files = response.data;
    } catch (err) {
      console.error('Error fetching files:', err);
      error = 'Failed to load media files. Please try again.';
    } finally {
      loading = false;
    }
  }
  
  // Handle filter changes
  function applyFilters(event: FilterEvent) {
    const { search, tags, speaker, dates, durationRange: duration, formats, codecs, resolution } = event.detail;
    
    searchQuery = search;
    selectedTags = tags;
    selectedSpeaker = speaker;
    dateRange = dates;
    
    // Handle advanced filters if provided
    if (duration) durationRange = duration;
    if (formats) selectedFormats = formats;
    if (codecs) selectedCodecs = codecs;
    if (resolution) resolutionRange = resolution;
    
    fetchFiles();
  }
  
  // Toggle file selection
  function toggleFileSelection(fileId: number, event: Event) {
    if (event) {
      event.stopPropagation();
      event.preventDefault();
    }
    
    const newSelection = new Set(selectedFiles);
    if (newSelection.has(fileId)) {
      newSelection.delete(fileId);
    } else {
      newSelection.add(fileId);
    }
    
    selectedFiles = newSelection;
    isSelecting = newSelection.size > 0;
  }
  
  // Select all files
  function selectAllFiles() {
    if (selectedFiles.size === files.length) {
      // If all are selected, deselect all but stay in selection mode
      selectedFiles = new Set();
    } else {
      // Select all visible files
      selectedFiles = new Set(files.map(file => file.id));
    }
  }
  
  // Clear selection
  function clearSelection() {
    selectedFiles = new Set();
    isSelecting = false;
  }
  
  // Delete selected files
  async function deleteSelectedFiles() {
    if (selectedFiles.size === 0) return;
    
    if (!confirm(`Are you sure you want to delete ${selectedFiles.size} selected file(s)? This action cannot be undone.`)) {
      return;
    }
    
    try {
      loading = true;
      
      // Delete files in parallel
      const deletePromises = Array.from(selectedFiles).map(async (fileId) => {
        try {
          await axiosInstance.delete(`/files/${fileId}`);
          return { success: true, id: fileId } as DeleteResult;
        } catch (err) {
          console.error(`Error deleting file ${fileId}:`, err);
          return { success: false, id: fileId } as DeleteResult;
        }
      });
      
      const results = await Promise.all(deletePromises);
      
      // Check for any failures
      const failedDeletions = results.filter(result => !result.success);
      
      if (failedDeletions.length > 0) {
        alert(`Failed to delete ${failedDeletions.length} file(s). Please try again.`);
      } else {
        alert(`Successfully deleted ${selectedFiles.size} file(s).`);
      }
      
      // Refresh the file list
      await fetchFiles();
      clearSelection();
      
    } catch (err) {
      console.error('Error deleting files:', err);
      alert('An error occurred while deleting files. Please try again.');
    } finally {
      loading = false;
    }
  }
  
  // Toggle filter sidebar for mobile
  function toggleFilters() {
    showFilters = !showFilters;
  }
  
  // Toggle upload modal
  function toggleUploadModal() {
    showUploadModal = !showUploadModal;
  }
  
  // Handle search input
  function handleSearch() {
    fetchFiles();
  }
  
  // Reset all filters
  function resetFilters() {
    searchQuery = '';
    selectedTags = [];
    selectedSpeaker = null;
    dateRange = { from: null, to: null };
    
    fetchFiles();
  }
  
  // File upload completed handler
  function handleUploadComplete() {
    // Refresh the file list and close the modal
    fetchFiles();
    showUploadModal = false;
  }
  
  // Subscribe to WebSocket file status updates to update file status in real-time
  function setupWebSocketUpdates() {
    unsubscribeFileStatus = fileStatusUpdates.subscribe((updates: FileStatusUpdates) => {
      if (files.length > 0 && Object.keys(updates).length > 0) {
        let updatedFile = false;
        
        // Update the status of files that have been processed
        files = files.map(file => {
          // Convert file id to string for comparison since our updates keys are strings
          const fileIdStr = file.id.toString();
          
          // Check if this file has an update in the updates object
          if (updates[fileIdStr]) {
            const update = updates[fileIdStr];
            updatedFile = true;
            
            // Return updated file object with new status
            return {
              ...file,
              status: update.status
            };
          }
          return file;
        });
        
        // Force a UI update by creating a new array
        if (updatedFile) {
          files = [...files];
        }
      }
    });
    
    // Also listen for general notifications that might affect files
    unsubscribeNotifications = lastNotification.subscribe((notification: Notification | null) => {
      if (notification) {
        // Check if this is a completion notification that requires refreshing files
        if (notification.type === 'transcription_status' && notification.data && notification.data.status === 'completed') {
          // Wait a brief moment to allow backend processing to complete
          setTimeout(() => fetchFiles(), 1000);
        } else if (notification.type === 'file_update') {
          setTimeout(() => fetchFiles(), 1000);
        }
      }
    });
  }
  
  let unsubscribeNotifications: () => void;
  
  onMount(() => {
    // Update document title
    document.title = 'Gallery | OpenTranscribe';
    
    // Setup WebSocket connection
    setupWebsocketConnection(window.location.origin);
    setupWebSocketUpdates();
    
    fetchFiles();
  });
  
  onDestroy(() => {
    // Clean up subscriptions when component is destroyed
    if (unsubscribeFileStatus) {
      unsubscribeFileStatus();
    }
    
    if (unsubscribeNotifications) {
      unsubscribeNotifications();
    }
  });
</script>

<div class="media-library">
  <div class="library-header">
    <div class="header-row">
      <h1>Gallery</h1>
      
      <div class="header-actions">
        {#if isSelecting}
          <div class="selection-controls">
            <button class="select-all-btn" on:click={selectAllFiles}>
              {selectedFiles.size === files.length ? 'Deselect all' : 'Select all'}
            </button>
            <button class="cancel-selection-btn" on:click={clearSelection}>
              Cancel
            </button>
            <button class="delete-selected-btn" on:click={deleteSelectedFiles}>
              Delete {selectedFiles.size} selected
            </button>
          </div>
        {:else}
          <div class="normal-actions">
            <button class="upload-button" on:click={toggleUploadModal}>
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="17 8 12 3 7 8"></polyline>
                <line x1="12" y1="3" x2="12" y2="15"></line>
              </svg>
              Upload Media
            </button>
            <button class="select-files-btn" on:click={() => isSelecting = true}>
              Select Files
            </button>
          </div>
        {/if}
      </div>
    </div>
    
    <div class="mobile-filter-toggle">
      <button on:click={toggleFilters}>
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"></polygon>
        </svg>
        Filters
      </button>
    </div>
  </div>

  <div class="library-content">
    <div class="filter-sidebar {showFilters ? 'show' : ''}">
      <FilterSidebar 
        {searchQuery}
        {selectedTags}
        {selectedSpeaker}
        {dateRange}
        on:filter={applyFilters}
        on:reset={resetFilters}
      />
    </div>
    
    <div class="file-list-container">
      
      {#if loading}
        <div class="loading-state">
          <p>Loading files...</p>
        </div>
      {:else if error}
        <div class="error-state">
          <p>Unable to connect to the server. Please check your connection and try again.</p>
          <button class="retry-button" on:click={fetchFiles}>Retry</button>
        </div>
      {:else if files.length === 0}
        <div class="empty-state">
          <p>Your media library is empty.</p>
          <p>Use the uploader above to add your first media file!</p>
        </div>
      {:else}
        <div class="file-grid">
          {#each files as file (file.id)}
              <div 
                class="file-card {selectedFiles.has(file.id) ? 'selected' : ''}"
              >
                {#if isSelecting}
                  <label class="file-selector">
                    <input 
                      type="checkbox" 
                      class="file-checkbox" 
                      checked={selectedFiles.has(file.id)} 
                      on:change={(e) => toggleFileSelection(file.id, e)}
                    />
                    <span class="checkmark"></span>
                  </label>
                {/if}
                <Link 
                  to={isSelecting ? '#' : `/files/${file.id}`} 
                  class="file-card-link"
                  on:click={(e) => {
                    if (isSelecting) {
                      e.preventDefault();
                      toggleFileSelection(file.id, e);
                    }
                  }}
                >
                <div class="file-status status-{file.status}">
                  {#if file.status === 'pending' || file.status === 'processing'}
                    <span class="status-dot"></span>
                    Processing
                  {:else if file.status === 'completed'}
                    <span class="status-dot"></span>
                    Completed
                  {:else if file.status === 'error'}
                    <span class="status-dot"></span>
                    Error
                  {/if}
                </div>
                
                <div class="file-info">
                  <h2 class="file-name">{file.filename}</h2>
                  <div class="file-meta">
                    <span class="file-date">{format(new Date(file.upload_time), 'MMM d, yyyy')}</span>
                    {#if file.duration}
                      <span class="file-duration">{formatDuration(file.duration)}</span>
                    {/if}
                  </div>
                  
                  {#if file.tags && file.tags.length > 0}
                    <div class="file-tags">
                      {#each file.tags as tag}
                        <span class="tag">{tag}</span>
                      {/each}
                    </div>
                  {/if}
                  
                  {#if file.summary}
                    <p class="file-summary">{file.summary.substring(0, 100)}...</p>
                  {/if}
                </div>
              </Link>
            </div>
          {/each}
        </div>
      {/if}
    </div>
  </div>
</div>

<!-- Upload Modal -->
{#if showUploadModal}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- The modal backdrop that closes on click -->
  <div 
    class="modal-backdrop" 
    role="presentation"
    on:click|self={toggleUploadModal}
    on:keydown={(e) => e.key === 'Escape' && toggleUploadModal()}
  >
    <!-- The actual modal dialog -->
    <div 
      class="modal-container" 
      role="dialog"
      aria-labelledby="upload-modal-title"
      aria-modal="true"
      tabindex="-1"
      on:click|stopPropagation
      on:keydown|stopPropagation>
      <div class="modal-content">
        <div class="modal-header">
          <h2 id="upload-modal-title">Upload Media</h2>
          <button 
            class="modal-close" 
            on:click={toggleUploadModal}
            aria-label="Close upload dialog">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>
        <div class="modal-body">
          <FileUploader on:uploadComplete={handleUploadComplete} />
        </div>
      </div>
    </div>
  </div>
{/if}

<style>
  /* Selection controls */
  .header-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    width: 100%;
    margin-bottom: 1rem;
  }
  
  .header-actions {
    display: flex;
    gap: 0.75rem;
  }
  
  .select-files-btn {
    background-color: #3b82f6;
    color: white;
    border: none;
    padding: 0.6rem 1.2rem;
    border-radius: 10px;
    font-size: 0.95rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }
  
  .select-files-btn:hover:not(:disabled) {
    background-color: #2563eb;
    color: white;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
    text-decoration: none;
  }
  
  .select-files-btn:active:not(:disabled) {
    transform: translateY(0);
  }
  
  .selection-controls {
    display: flex;
    gap: 0.75rem;
    align-items: center;
    background: var(--background-alt);
    padding: 0.5rem 1rem;
    border-radius: 6px;
    animation: fadeIn 0.2s ease;
  }
  
  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(-10px); }
    to { opacity: 1; transform: translateY(0); }
  }
  
  .select-all-btn,
  .cancel-selection-btn {
    padding: 0.6rem 1.2rem;
    border: 1px solid var(--border-color);
    background-color: var(--surface-color);
    color: var(--text-color);
    border-radius: 10px;
    cursor: pointer;
    font-size: 0.95rem;
    font-weight: 500;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }
  
  .select-all-btn {
    background-color: #3b82f6;
    color: white;
    border: none;
  }
  
  .select-all-btn:hover:not(:disabled) {
    background-color: #2563eb;
    color: white;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
    text-decoration: none;
  }
  
  .select-all-btn:active:not(:disabled) {
    transform: translateY(0);
  }
  
  .cancel-selection-btn {
    background-color: var(--surface-color);
    color: var(--text-color);
    border: 1px solid var(--border-color);
  }
  
  .cancel-selection-btn:hover:not(:disabled) {
    background-color: var(--button-hover);
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
    text-decoration: none;
  }
  
  .cancel-selection-btn:active:not(:disabled) {
    transform: translateY(0);
  }
  
  .delete-selected-btn {
    padding: 0.6rem 1.2rem;
    background-color: var(--error-color);
    color: white;
    border: none;
    border-radius: 10px;
    cursor: pointer;
    font-size: 0.95rem;
    font-weight: 500;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(239, 68, 68, 0.2);
  }
  
  .delete-selected-btn:hover:not(:disabled) {
    background-color: #d32f2f; /* Slightly darker red on hover */
    color: white;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(239, 68, 68, 0.25);
    text-decoration: none;
  }
  
  .delete-selected-btn:active:not(:disabled) {
    transform: translateY(0);
  }
  
  .selection-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.3);
    opacity: 0;
    pointer-events: none;
    z-index: 10;
    transition: opacity 0.2s ease;
  }
  
  .selection-overlay.active {
    opacity: 1;
    pointer-events: auto;
  }
  
  /* File card selection */
  .file-card {
    position: relative;
    transition: all 0.2s ease;
    border: 2px solid transparent;
    border-radius: 8px;
    background: var(--background-color);
    overflow: hidden;
  }
  
  .file-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  }
  
  .file-card.selected {
    border-color: var(--primary-color);
    background-color: rgba(var(--primary-rgb), 0.05);
  }
  
  .file-selector {
    position: absolute;
    top: 0.75rem;
    left: 0.75rem;
    z-index: 10;
    width: 20px;
    height: 20px;
    cursor: pointer;
    pointer-events: auto;
  }
  
  .file-checkbox {
    position: absolute;
    opacity: 0;
    width: 0;
    height: 0;
  }
  
  .checkmark {
    position: absolute;
    top: 0;
    left: 0;
    width: 20px;
    height: 20px;
    background-color: var(--background-color);
    border: 2px solid var(--border-color);
    border-radius: 4px;
    transition: all 0.2s ease;
    pointer-events: none;
  }
  
  .file-selector:hover .checkmark {
    border-color: var(--primary-color);
  }
  
  .file-checkbox:checked ~ .checkmark {
    background-color: var(--primary-color);
    border-color: var(--primary-color);
  }
  
  .file-checkbox {
    position: absolute;
    opacity: 0;
    width: 100%;
    height: 100%;
    margin: 0;
    cursor: pointer;
  }
  
  .checkmark:after {
    content: "";
    position: absolute;
    display: none;
    left: 6px;
    top: 2px;
    width: 5px;
    height: 10px;
    border: solid white;
    border-width: 0 2px 2px 0;
    transform: rotate(45deg);
  }
  
  .file-checkbox:checked ~ .checkmark:after {
    display: block;
  }
  
  .file-card-link {
    display: block;
    text-decoration: none;
    color: inherit;
    padding: 1rem;
  }
  
  .media-library {
    display: flex;
    flex-direction: column;
    height: 100%;
  }
  
  .library-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 1rem;
    margin-bottom: 1.5rem;
  }
  
  .library-header h1 {
    font-size: 1.5rem;
    margin: 0;
  }
  
  /* Search functionality is now handled in the FilterSidebar component */
  
  .library-content {
    display: flex;
    gap: 2rem;
    height: 100%;
  }
  
  .filter-sidebar {
    width: 250px;
    flex-shrink: 0;
  }
  
  .file-list-container {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
  }
  
  /* Upload Button in Header */
  .normal-actions {
    display: flex;
    gap: 0.5rem;
  }
  
  .upload-button {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background-color: #3b82f6;
    color: white;
    padding: 0.6rem 1.2rem;
    border: none;
    border-radius: 10px;
    cursor: pointer;
    font-size: 0.95rem;
    font-weight: 500;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }
  
  .upload-button:hover:not(:disabled) {
    background-color: #2563eb;
    color: white;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
    text-decoration: none;
  }
  
  .upload-button:active:not(:disabled) {
    transform: translateY(0);
  }

  /* Modal Styles */
  .modal-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: rgba(0, 0, 0, 0.5);
    z-index: 1000;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  
  .modal-container {
    position: relative;
    width: 100%;
    max-width: 600px;
    margin: 1rem;
  }
  
  .modal-content {
    background-color: var(--surface-color);
    border-radius: 12px;
    width: 100%;
    max-height: 90vh;
    overflow-y: auto;
    box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1);
    display: flex;
    flex-direction: column;
    position: relative;
  }
  
  .modal-header {
    position: relative;
    padding: 1.25rem 1.5rem;
    border-bottom: 1px solid var(--border-color);
  }
  
  .modal-header h2 {
    margin: 0;
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--text-color);
  }
  
  .modal-close {
    position: absolute;
    top: 1rem;
    right: 1rem;
    background: transparent;
    border: none;
    border-radius: 50%;
    width: 2rem;
    height: 2rem;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    color: var(--text-light);
    cursor: pointer;
    transition: all 0.2s ease;
  }
  
  .modal-close:hover {
    background-color: var(--background-alt);
    color: var(--text-color);
  }
  
  .modal-close svg {
    width: 1.25rem;
    height: 1.25rem;
  }
  
  .modal-body {
    padding: 1.5rem 1.5rem 2rem;
  }
  
  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
  }
  
  .file-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    grid-gap: 1.5rem;
  }
  
  .file-card {
    background-color: var(--surface-color);
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    overflow: hidden;
    transition: transform 0.2s, box-shadow 0.2s;
    text-decoration: none;
    color: inherit;
    position: relative;
    height: 100%;
    display: flex;
    flex-direction: column;
  }
  
  .file-card:not(.selected):hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  }
  
  .file-card.selected {
    border: 2px solid var(--primary-color);
  }
  
  .file-status {
    padding: 0.5rem;
    font-size: 0.8rem;
    font-weight: 500;
    text-align: right;
  }
  
  .status-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    margin-right: 5px;
  }
  
  .status-pending .status-dot,
  .status-processing .status-dot {
    background-color: var(--warning-color);
    animation: pulse 1.5s infinite;
  }
  
  .status-completed .status-dot {
    background-color: var(--success-color);
  }
  
  .status-error .status-dot {
    background-color: var(--error-color);
  }
  
  .file-info {
    padding: 1rem;
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  
  .file-name {
    font-size: 1.1rem;
    margin: 0;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  
  .file-meta {
    display: flex;
    gap: 1rem;
    font-size: 0.8rem;
    color: var(--text-light);
  }
  
  .file-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-top: 0.5rem;
  }
  
  .tag {
    background-color: var(--background-color);
    color: var(--text-light);
    font-size: 0.7rem;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
  }
  
  .file-summary {
    font-size: 0.9rem;
    color: var(--text-light);
    margin: 0;
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    line-clamp: 3;
    -webkit-box-orient: vertical;
  }
  
  .loading-state,
  .error-state,
  .empty-state {
    padding: 2rem;
    text-align: center;
    background-color: var(--surface-color);
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    color: var(--text-light);
  }
  
  .retry-button {
    margin-top: 1rem;
    background: var(--primary-light);
    color: var(--primary-dark);
    border: 2px solid var(--primary-color);
    border-radius: 6px;
    padding: 0.5rem 1rem;
    font-size: 0.9rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
  }
  
  .retry-button:hover {
    background: var(--primary-color);
    color: white;
    transform: translateY(-1px);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  }
  
  .retry-button:active {
    transform: translateY(0);
  }
  
  .mobile-filter-toggle {
    display: none;
  }
  
  @keyframes pulse {
    0% {
      opacity: 0.6;
    }
    50% {
      opacity: 1;
    }
    100% {
      opacity: 0.6;
    }
  }
  
  @media (max-width: 768px) {
    .library-header {
      flex-direction: column;
      align-items: flex-start;
    }
    
    .search-container {
      max-width: 100%;
    }
    
    .filter-sidebar {
      display: none;
      position: fixed;
      top: 60px;
      left: 0;
      bottom: 0;
      width: 80%;
      max-width: 300px;
      background-color: var(--surface-color);
      z-index: 10;
      box-shadow: 2px 0 5px rgba(0, 0, 0, 0.1);
      overflow-y: auto;
      padding: 1rem;
    }
    
    .filter-sidebar.show {
      display: block;
    }
    
    .mobile-filter-toggle {
      display: block;
    }
    
    .mobile-filter-toggle button {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      background-color: #3b82f6;
      color: white;
      border: none;
      border-radius: 10px;
      padding: 0.6rem 1.2rem;
      cursor: pointer;
      font-size: 0.95rem;
      font-weight: 500;
      transition: all 0.2s ease;
      box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
    }
    
    .mobile-filter-toggle button:hover:not(:disabled) {
      background-color: #2563eb;
      color: white;
      transform: translateY(-1px);
      box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
      text-decoration: none;
    }
    
    .mobile-filter-toggle button:active:not(:disabled) {
      transform: translateY(0);
    }
    
    .library-content {
      flex-direction: column;
      gap: 1rem;
    }
    
    .file-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
