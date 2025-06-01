<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { Link, useNavigate } from 'svelte-navigator';
  import { websocketStore } from '$stores/websocket';
  import { authStore } from '../stores/auth';
  import { toastStore } from '$stores/toast';
  
  // Define navigate for routing
  const navigateHook = useNavigate();
  
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
    file_hash?: string;
    thumbnail_url?: string;
    
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
      speaker: string[];
      collectionId: number | null;
      dates: DateRange;
      durationRange?: DurationRange;
      fileSizeRange?: { min: number | null; max: number | null };
      fileTypes?: string[];
      statuses?: string[];
      transcriptSearch?: string;
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
  import CollectionsPanel from '../components/CollectionsPanel.svelte';
  import UserFileStatus from '../components/UserFileStatus.svelte';
  
  // Media files state
  let files: MediaFile[] = [];
  let loading: boolean = true;
  let error: string | null = null;
  
  // Selection state
  let selectedFiles = new Set<number>();
  let isSelecting: boolean = false;
  
  // View state
  let selectedCollectionId: number | null = null;
  let showCollectionsModal = false;
  let activeTab: 'gallery' | 'status' = 'gallery';
  
  // Component refs
  let filterSidebarRef: any;
  
  // WebSocket subscription
  let unsubscribeFileStatus: (() => void) | undefined;
  
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
  let selectedSpeakers: string[] = [];
  let dateRange = { from: null as Date | null, to: null as Date | null };
  let durationRange = { min: null as number | null, max: null as number | null };
  let fileSizeRange = { min: null as number | null, max: null as number | null };
  let selectedFileTypes: string[] = [];
  let selectedStatuses: string[] = [];
  let transcriptSearch: string = '';
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
      
      if (selectedSpeakers.length > 0) {
        selectedSpeakers.forEach(speaker => params.append('speaker', speaker));
      }
      
      if (dateRange.from) {
        params.append('from_date', dateRange.from.toISOString());
      }
      
      if (dateRange.to) {
        params.append('to_date', dateRange.to.toISOString());
      }
      
      // Add duration filter parameters
      if (durationRange.min !== null) {
        params.append('min_duration', durationRange.min.toString());
      }
      
      if (durationRange.max !== null) {
        params.append('max_duration', durationRange.max.toString());
      }
      
      // Add file size filter parameters
      if (fileSizeRange.min !== null) {
        params.append('min_file_size', fileSizeRange.min.toString());
      }
      
      if (fileSizeRange.max !== null) {
        params.append('max_file_size', fileSizeRange.max.toString());
      }
      
      // Add file type filter parameters
      if (selectedFileTypes.length > 0) {
        selectedFileTypes.forEach(fileType => params.append('file_type', fileType));
      }
      
      // Add status filter parameters
      if (selectedStatuses.length > 0) {
        selectedStatuses.forEach(status => params.append('status', status));
      }
      
      // Add transcript search parameter
      if (transcriptSearch.trim()) {
        params.append('transcript_search', transcriptSearch.trim());
      }
      
      // If a collection is selected, fetch files from that collection
      if (selectedCollectionId !== null) {
        const response = await axiosInstance.get(`/api/collections/${selectedCollectionId}/media`, { params });
        files = response.data;
      } else {
        const response = await axiosInstance.get('/files', { params });
        files = response.data;
      }
    } catch (err) {
      console.error('Error fetching files:', err);
      error = 'Failed to load media files. Please try again.';
    } finally {
      loading = false;
    }
  }
  
  // Handle filter changes
  function applyFilters(event: FilterEvent) {
    const { search, tags, speaker, collectionId, dates, durationRange: duration, fileSizeRange: fileSize, fileTypes, statuses, transcriptSearch: transcript } = event.detail;
    
    searchQuery = search;
    selectedTags = tags;
    selectedSpeakers = speaker;
    selectedCollectionId = collectionId;
    dateRange = dates;
    
    // Handle advanced filters if provided
    if (duration) durationRange = duration;
    if (fileSize) fileSizeRange = fileSize;
    if (fileTypes) selectedFileTypes = fileTypes;
    if (statuses) selectedStatuses = statuses;
    if (transcript) transcriptSearch = transcript;
    
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
        toastStore.error(`Failed to delete ${failedDeletions.length} file(s). Please try again.`);
      } else {
        toastStore.success(`Successfully deleted ${selectedFiles.size} file(s).`);
      }
      
      // Refresh the file list
      await fetchFiles();
      clearSelection();
      
    } catch (err) {
      console.error('Error deleting files:', err);
      toastStore.error('An error occurred while deleting files. Please try again.');
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
    selectedSpeakers = [];
    selectedCollectionId = null;
    dateRange = { from: null, to: null };
    durationRange = { min: null, max: null };
    fileSizeRange = { min: null, max: null };
    selectedFileTypes = [];
    selectedStatuses = [];
    transcriptSearch = '';
    
    fetchFiles();
  }
  
  // File upload completed handler
  function handleUploadComplete(event: CustomEvent) {
    // Refresh the file list
    fetchFiles();
    
    // Only close the modal if not a duplicate file
    // For duplicates, we want to keep the modal open to show the notification
    const isDuplicate = event.detail?.isDuplicate || false;
    
    if (!isDuplicate) {
      showUploadModal = false;
    }
  }
  
  // Subscribe to WebSocket file status updates to update file status in real-time
  // Track last processed notification to avoid duplicate processing
  let lastProcessedNotificationId = '';
  
  function setupWebSocketUpdates() {
    unsubscribeFileStatus = websocketStore.subscribe(($ws) => {
      if ($ws.notifications.length > 0) {
        const latestNotification = $ws.notifications[0];
        
        // Only process if this is a new notification we haven't handled
        if (latestNotification.id !== lastProcessedNotificationId) {
          lastProcessedNotificationId = latestNotification.id;
          
          // Check if this notification is for transcription status
          if (latestNotification.type === 'transcription_status' && latestNotification.data?.file_id) {
            const fileId = String(latestNotification.data.file_id);
            const status = latestNotification.data.status;
            
            // Update any files that match this notification
            files = files.map(file => {
              if (String(file.id) === fileId) {
                return {
                  ...file,
                  status: status
                };
              }
              return file;
            });
            
            console.log('MediaLibrary updated from WebSocket notification for file:', fileId, 'Status:', status);
          }
        }
      }
    });
  }
  
  onMount(() => {
    // Update document title
    document.title = 'Gallery | OpenTranscribe';
    
    // Setup WebSocket subscription for real-time updates
    setupWebSocketUpdates();
    
    fetchFiles();
  });
  
  onDestroy(() => {
    // Clean up WebSocket subscription when component is destroyed
    if (unsubscribeFileStatus) {
      unsubscribeFileStatus();
    }
  });
</script>

<div class="media-library">
  <header class="library-header">
    <div class="header-row">
      <div class="title-and-tabs">
        <h1>Media Library</h1>
        <div class="tabs">
          <button 
            class="tab-button {activeTab === 'gallery' ? 'active' : ''}"
            on:click={() => activeTab = 'gallery'}
          >
            Gallery
          </button>
          <button 
            class="tab-button {activeTab === 'status' ? 'active' : ''}"
            on:click={() => activeTab = 'status'}
          >
            File Status
          </button>
        </div>
      </div>
      
      {#if activeTab === 'gallery'}
        <div class="header-actions">
          {#if isSelecting}
          <div class="selection-controls">
            <button 
              class="select-all-btn" 
              on:click={selectAllFiles}
              title="{selectedFiles.size === files.length ? 'Remove all files from selection' : 'Add all visible files to selection'}"
            >
              {selectedFiles.size === files.length ? 'Deselect all' : 'Select all'}
            </button>
            <button
              class="add-to-collection-btn"
              on:click={() => showCollectionsModal = true}
              title="Add selected files to a collection"
            >
              Add to Collection
            </button>
            <button 
              class="delete-selected-btn" 
              on:click={deleteSelectedFiles}
              title="Permanently delete the {selectedFiles.size} selected file{selectedFiles.size === 1 ? '' : 's'} - this action cannot be undone"
            >
              Delete {selectedFiles.size} selected
            </button>
            <button 
              class="cancel-selection-btn" 
              on:click={clearSelection}
              title="Exit selection mode and clear all selected files"
            >
              Cancel
            </button>
          </div>
        {:else}
          <div class="normal-actions">
            <button 
              class="upload-button" 
              on:click={toggleUploadModal}
              title="Upload new audio or video files for transcription"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="17 8 12 3 7 8"></polyline>
                <line x1="12" y1="3" x2="12" y2="15"></line>
              </svg>
              Upload Media
            </button>
            <button 
              class="collections-btn"
              on:click={() => showCollectionsModal = true}
              title="Manage your collections"
            >
              Collections
            </button>
            <button 
              class="select-files-btn" 
              on:click={() => isSelecting = true}
              title="Enter selection mode to choose multiple files for batch operations"
            >
              Select Files
            </button>
          </div>
        {/if}
        </div>
      {/if}
    </div>
    
    {#if activeTab === 'gallery'}
      <div class="mobile-filter-toggle">
        <button 
          on:click={toggleFilters}
          title="Show or hide the filter sidebar to search and filter your media files"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"></polygon>
          </svg>
          Filters
        </button>
      </div>
    {/if}
  </header>

  <div class="library-content">
    {#if activeTab === 'gallery'}
      <div class="filter-sidebar {showFilters ? 'show' : ''}">
        <FilterSidebar 
        bind:this={filterSidebarRef}
        searchQuery={searchQuery}
        selectedTags={selectedTags}
        selectedSpeakers={selectedSpeakers}
        selectedCollectionId={selectedCollectionId}
        dateRange={{from: null, to: null}}
        durationRange={{min: null, max: null}}
        fileSizeRange={{min: null, max: null}}
        selectedFileTypes={selectedFileTypes}
        selectedStatuses={selectedStatuses}
        transcriptSearch={transcriptSearch}
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
          <button 
            class="retry-button" 
            on:click={fetchFiles}
            title="Retry loading your media files"
          >Retry</button>
        </div>
      {:else if files.length === 0}
        <div class="empty-state">
          <p>{selectedCollectionId ? 'No files in this collection.' : 'Your media library is empty.'}</p>
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
                      title="Select or deselect this file for batch operations"
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
                <div class="file-content">
                  {#if file.thumbnail_url && file.content_type && file.content_type.startsWith('video/')}
                    <div class="file-thumbnail">
                      <img 
                        src={file.thumbnail_url} 
                        alt="Thumbnail for {file.filename}" 
                        loading="lazy"
                        class="thumbnail-image"
                      />
                      <div class="video-overlay">
                        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="white" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                          <polygon points="5 3 19 12 5 21 5 3"></polygon>
                        </svg>
                      </div>
                    </div>
                  {:else if file.content_type && file.content_type.startsWith('video/')}
                    <div class="file-thumbnail video-placeholder">
                      <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" stroke-linecap="round" stroke-linejoin="round">
                        <rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"></rect>
                        <line x1="7" y1="2" x2="7" y2="22"></line>
                        <line x1="17" y1="2" x2="17" y2="22"></line>
                        <line x1="2" y1="12" x2="22" y2="12"></line>
                        <line x1="2" y1="7" x2="7" y2="7"></line>
                        <line x1="2" y1="17" x2="7" y2="17"></line>
                        <line x1="17" y1="17" x2="22" y2="17"></line>
                        <line x1="17" y1="7" x2="22" y2="7"></line>
                      </svg>
                    </div>
                  {:else if file.content_type && file.content_type.startsWith('audio/')}
                    <div class="file-thumbnail audio-placeholder">
                      <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M9 18V5l12-2v13"></path>
                        <circle cx="6" cy="18" r="3"></circle>
                        <circle cx="18" cy="16" r="3"></circle>
                      </svg>
                    </div>
                  {/if}
                  
                  <h2 class="file-name">{file.filename}</h2>
                  
                  <div class="file-meta">
                    <span class="file-date">{format(new Date(file.upload_time), 'MMM d, yyyy')}</span>
                    {#if file.duration}
                      <span class="file-duration">{formatDuration(file.duration)}</span>
                    {/if}
                  </div>
                  
                  <div class="file-status status-{file.status}">
                    <span class="status-dot"></span>
                    {#if file.status === 'pending' || file.status === 'processing'}
                      Processing
                    {:else if file.status === 'completed'}
                      Completed
                    {:else if file.status === 'error'}
                      Error
                    {/if}
                  </div>
                </div>
              </Link>
            </div>
          {/each}
        </div>
      {/if}
    </div>
  
  {:else if activeTab === 'status'}
    <div class="status-tab-content">
      <UserFileStatus />
    </div>
  {/if}
  </div>
    
  
</div>

<!-- Upload Modal -->
{#if showUploadModal}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- The modal backdrop that closes on click -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div 
    class="modal-backdrop" 
    role="dialog"
    aria-modal="true"
    tabindex="0"
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
            aria-label="Close upload dialog"
            title="Close the upload dialog"
          >
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

<!-- Collections Modal -->
{#if showCollectionsModal}
  <div class="modal-backdrop" on:click={() => showCollectionsModal = false}>
    <div class="modal-container" on:click|stopPropagation>
      <div class="modal-content">
        <div class="modal-header">
          <h2>{selectedFiles.size > 0 ? 'Add to Collection' : 'Manage Collections'}</h2>
          <button 
            class="modal-close" 
            on:click={() => showCollectionsModal = false}
            aria-label="Close collections dialog"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>
        <div class="modal-body">
          <CollectionsPanel 
            selectedMediaIds={Array.from(selectedFiles)}
            viewMode={selectedFiles.size > 0 ? 'add' : 'manage'}
            onCollectionSelect={() => {
              showCollectionsModal = false;
              if (selectedFiles.size > 0) {
                clearSelection();
              }
              // Refresh collections in filter
              if (filterSidebarRef && filterSidebarRef.refreshCollections) {
                filterSidebarRef.refreshCollections();
              }
              // Refresh files if we're filtering by collection
              if (selectedCollectionId !== null) {
                fetchFiles();
              }
            }}
          />
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
  
  .cancel-selection-btn {
    background-color: #6b7280;
    color: white;
    border: none;
    padding: 0.6rem 1.2rem;
    border-radius: 10px;
    font-size: 0.95rem;
    font-weight: 500;
    cursor: pointer;
  }
  
  .cancel-selection-btn:hover:not(:disabled) {
    background-color: #4b5563;
    text-decoration: none;
  }
  
  .select-all-btn {
    background-color: #059669;
    color: white;
    border: none;
    padding: 0.6rem 1.2rem;
    border-radius: 10px;
    font-size: 0.95rem;
    font-weight: 500;
    cursor: pointer;
  }
  
  .select-all-btn:hover:not(:disabled) {
    background-color: #047857;
    text-decoration: none;
  }
  
  .delete-selected-btn {
    background-color: #dc2626;
    color: white;
    border: none;
    padding: 0.6rem 1.2rem;
    border-radius: 10px;
    font-size: 0.95rem;
    font-weight: 500;
    cursor: pointer;
  }
  
  .delete-selected-btn:hover:not(:disabled) {
    background-color: #b91c1c;
  }
  
  .selection-controls {
    display: flex;
    gap: 0.75rem;
    align-items: center;
  }

  /* File selector checkbox - bottom right */
  .file-selector {
    position: absolute;
    bottom: 12px;
    right: 12px;
    z-index: 10;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  
  .checkmark {
    width: 20px;
    height: 20px;
    background-color: var(--background-color);
    border: 2px solid var(--border-color);
    border-radius: 4px;
    position: relative;
    cursor: pointer;
    transition: all 0.2s ease;
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
  
  .title-and-tabs {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }
  
  .tabs {
    display: flex;
    gap: 0.5rem;
  }
  
  .tab-button {
    padding: 0.5rem 1rem;
    border: 1px solid #e5e7eb;
    background: white;
    border-radius: 6px 6px 0 0;
    cursor: pointer;
    font-weight: 500;
    transition: all 0.2s ease;
    color: #6b7280;
  }
  
  .tab-button.active {
    background: #3b82f6;
    color: white;
    border-color: #3b82f6;
  }
  
  .tab-button:hover:not(.active) {
    background: #f9fafb;
    color: #374151;
  }
  
  .status-tab-content {
    padding: 1rem;
    width: 100%;
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
  
  .collections-btn {
    background-color: #8b5cf6;
    color: white;
    border: none;
    padding: 0.6rem 1.2rem;
    border-radius: 10px;
    font-size: 0.95rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
  }
  
  .collections-btn:hover {
    background-color: #7c3aed;
  }
  
  /* Add to collection button */
  .add-to-collection-btn {
    background-color: #10b981;
    color: white;
    border: none;
    padding: 0.6rem 1.2rem;
    border-radius: 10px;
    font-size: 0.95rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
  }
  
  .add-to-collection-btn:hover {
    background-color: #059669;
  }
  
  /* File grid */
  .file-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 1.5rem;
  }
  
  .file-card {
    position: relative;
    border: 1px solid var(--border-color);
    background-color: var(--surface-color);
    border-radius: 12px;
    padding: 1.5rem;
    transition: all 0.2s ease-in-out;
    cursor: pointer;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
  
  .file-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
    border-color: var(--border-hover);
  }
  
  .file-card.selected {
    border: 2px solid var(--accent-color);
    background-color: var(--selection-background);
  }
  
  .file-thumbnail {
    position: relative;
    width: 100%;
    height: 120px;
    margin-bottom: 1rem;
    border-radius: 8px;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
    background-color: rgba(0, 0, 0, 0.04);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
  }
  
  :global(.dark) .file-thumbnail {
    background-color: rgba(255, 255, 255, 0.05);
  }
  
  .thumbnail-image {
    width: 100%;
    height: 100%;
    object-fit: cover;
    transition: transform 0.3s ease;
  }
  
  .file-card:hover .thumbnail-image {
    transform: scale(1.05);
  }
  
  .video-overlay {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: rgba(0, 0, 0, 0.3);
    display: flex;
    align-items: center;
    justify-content: center;
    opacity: 0.8;
    transition: opacity 0.3s ease;
  }
  
  .file-card:hover .video-overlay {
    opacity: 1;
  }
  
  .video-placeholder,
  .audio-placeholder {
    background-color: rgba(0, 0, 0, 0.04);
    color: var(--text-secondary);
  }
  
  :global(.dark) .video-placeholder,
  :global(.dark) .audio-placeholder {
    background-color: rgba(255, 255, 255, 0.05);
    color: var(--text-secondary);
  }
  
  :global(.dark) .file-card.selected {
    background-color: rgba(59, 130, 246, 0.1);
    border-color: var(--primary-color);
  }
  
  .file-content {
    padding: 1.5rem;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  
  .file-card-link {
    display: block;
    text-decoration: none;
    color: inherit;
    height: 100%;
  }
  
  .file-name {
    font-size: 1.125rem;
    font-weight: 600;
    color: var(--text-primary);
    margin: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    line-height: 1.4;
  }
  
  .file-date {
    font-size: 0.875rem;
    color: var(--text-secondary);
    margin-top: auto;
  }
  
  .file-duration {
    font-size: 0.875rem;
    color: var(--text-secondary);
    font-weight: 500;
  }
  
  .file-meta {
    display: flex;
    align-items: center;
    gap: 1rem;
    font-size: 0.875rem;
    color: var(--text-secondary);
  }
  
  .file-status {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    font-size: 0.75rem;
    font-weight: 500;
    padding: 0.25rem 0.75rem;
    border-radius: 9999px;
    background-color: rgba(0, 0, 0, 0.05);
    width: fit-content;
    align-self: flex-start;
  }
  
  :global(.dark) .file-status {
    background-color: rgba(255, 255, 255, 0.05);
  }
  
  .status-pending,
  .status-processing {
    color: #f59e0b;
    background-color: rgba(245, 158, 11, 0.1);
  }
  
  .status-completed {
    color: #10b981;
    background-color: rgba(16, 185, 129, 0.1);
  }
  
  .status-error {
    color: #ef4444;
    background-color: rgba(239, 68, 68, 0.1);
  }
  
  .status-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background-color: currentColor;
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
  
  .status-processing .status-dot {
    animation: pulse 2s ease-in-out infinite;
  }
  
  .file-tags {
    display: flex;
    gap: 0.25rem;
    flex-wrap: wrap;
    margin-top: 0.5rem;
  }
  
  .tag {
    background-color: var(--primary-light);
    color: var(--primary-color);
    padding: 0.125rem 0.5rem;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 500;
  }
  
  .file-summary {
    margin-top: 0.75rem;
    color: var(--text-secondary);
    font-size: 0.85rem;
    line-height: 1.4;
    overflow: hidden;
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 3;
    line-clamp: 3;
    max-height: 3.6em;
  }
  
  .loading-state,
  .error-state,
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 400px;
    text-align: center;
    color: var(--text-secondary);
  }
  
  .error-state {
    color: var(--error-color);
  }
  
  .retry-button {
    margin-top: 1rem;
    background-color: var(--primary-color);
    color: white;
    border: none;
    padding: 0.5rem 1rem;
    border-radius: 8px;
    cursor: pointer;
    font-size: 0.875rem;
    font-weight: 500;
    transition: all 0.2s ease;
  }
  
  .retry-button:hover {
    background-color: var(--primary-hover);
    transform: translateY(-1px);
  }
  
  .retry-button:active {
    transform: translateY(0);
  }
  
  .mobile-filter-toggle {
    display: none;
  }
  
  /* Modal styles */
  .modal-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }
  
  :global(.dark) .modal-backdrop {
    background: rgba(0, 0, 0, 0.7);
  }
  
  .modal-container {
    background: var(--background-color);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    max-width: 90%;
    max-height: 90vh;
    width: 600px;
    overflow: hidden;
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
  }
  
  :global(.dark) .modal-container {
    background: var(--background-color);
    border-color: var(--border-color);
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3), 0 10px 10px -5px rgba(0, 0, 0, 0.2);
  }
  
  .modal-content {
    display: flex;
    flex-direction: column;
    height: 100%;
  }
  
  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1.5rem;
    border-bottom: 1px solid var(--border-color);
  }
  
  .modal-header h2 {
    margin: 0;
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--text-primary);
  }
  
  .modal-close {
    background: none;
    border: none;
    cursor: pointer;
    padding: 0.5rem;
    color: var(--text-secondary);
    transition: color 0.2s ease;
  }
  
  .modal-close:hover {
    color: var(--text-primary);
  }
  
  .modal-body {
    flex: 1;
    padding: 1.5rem;
    overflow-y: auto;
  }
  
  /* Dark mode adjustments */
  :global(.dark) .file-card {
    background: var(--surface-color);
    border-color: var(--border-color);
  }
  
  :global(.dark) .file-card:hover {
    border-color: var(--border-hover);
  }
  
  :global(.dark) .file-name {
    color: var(--text-primary);
  }
  
  :global(.dark) .file-date,
  :global(.dark) .file-duration,
  :global(.dark) .file-summary {
    color: var(--text-secondary);
  }
  
  :global(.dark) .tag {
    background-color: rgba(99, 102, 241, 0.2);
    color: #a5b4fc;
  }
  
  /* Responsive design */
  @media (max-width: 768px) {
    .library-header {
      flex-direction: column;
      align-items: flex-start;
    }
    
    .header-row {
      flex-direction: column;
      align-items: flex-start;
      gap: 1rem;
    }
    
    .header-actions {
      width: 100%;
    }
    
    .selection-controls {
      flex-wrap: wrap;
      width: 100%;
    }
    
    .selection-controls button {
      flex: 1;
      min-width: 120px;
    }
    
    .filter-sidebar {
      position: fixed;
      top: 0;
      left: -100%;
      width: 100%;
      height: 100%;
      background: white;
      z-index: 100;
      transition: left 0.3s ease;
      overflow-y: auto;
      padding: 1rem;
    }
    
    :global(.dark) .filter-sidebar {
      background: var(--surface-color);
    }
    
    .filter-sidebar.show {
      left: 0;
    }
    
    .mobile-filter-toggle {
      display: block;
      margin-top: 1rem;
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