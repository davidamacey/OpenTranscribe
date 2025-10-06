<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { goto } from '$app/navigation';

  import { flip } from 'svelte/animate';
  import { fade, scale } from 'svelte/transition';
  import { websocketStore } from '$stores/websocket';
  import { toastStore } from '$stores/toast';
  import { hasActiveUploads, uploadsStore } from '$stores/uploads';
  import { galleryStore, galleryState, selectedCount } from '$stores/gallery';
  import ConfirmationModal from '../components/ConfirmationModal.svelte';
  
  // Modal state
  let showUploadModal = false;
  
  // Confirmation modal state
  let showConfirmModal = false;
  let confirmModalTitle = '';
  let confirmModalMessage = '';
  let confirmCallback: (() => void) | null = null;
  
  // Define types
  interface MediaFile {
    id: string;  // UUID
    filename: string;
    status: 'pending' | 'processing' | 'completed' | 'error' | 'cancelling' | 'cancelled' | 'orphaned';
    upload_time: string;
    duration?: number;
    file_size?: number;
    content_type?: string;
    tags?: string[];
    summary?: string;
    file_hash?: string;
    thumbnail_url?: string;
    last_error_message?: string;

    // Formatted fields from backend
    formatted_duration?: string;
    formatted_upload_date?: string;
    formatted_file_age?: string;
    formatted_file_size?: string;
    display_status?: string;
    status_badge_class?: string;

    // Error handling fields from backend
    error_category?: string;
    error_suggestions?: string[];
    user_message?: string;
    is_retryable?: boolean;
    
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
  
  interface FilterEvent {
    detail: {
      search: string;
      tags: string[];
      speaker: string[];
      collectionId: string | null;  // UUID
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
  
  
  import axiosInstance from '../lib/axios';
  
  // Import components
  import FileUploader from '../components/FileUploader.svelte';
  import FilterSidebar from '../components/FilterSidebar.svelte';
  import CollectionsPanel from '../components/CollectionsPanel.svelte';
  import UserFileStatus from '../components/UserFileStatus.svelte';
  
  // Media files state
  let files: MediaFile[] = [];
  let loading: boolean = true;
  let error: string | null = null;


  // Animation and smooth update state
  let fileMap = new Map<string, MediaFile>();
  let pendingNewFiles = new Set<string>();
  let pendingDeletions = new Set<string>();
  let refreshTimeouts = new Map<string, number>();

  // View state
  let selectedCollectionId: string | null = null;
  let showCollectionsModal = false;

  // Use gallery store for state management
  $: activeTab = $galleryState.activeTab;
  $: isSelecting = $galleryState.isSelecting;
  $: selectedFiles = $galleryState.selectedFiles;
  
  // Component refs
  let filterSidebarRef: any;
  
  // WebSocket subscription
  let unsubscribeFileStatus: (() => void) | undefined;
  
  // Define WebSocket update type
  interface FileStatusUpdate {
    file_id: string;  // UUID
    status: 'pending' | 'processing' | 'completed' | 'error';
    progress?: number;
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
  // Use store for showFilters
  $: showFilters = $galleryState.showFilters;
  
  /**
   * Show confirmation modal
   * @param {string} title - The modal title
   * @param {string} message - The confirmation message
   * @param {() => void} callback - The callback to execute on confirmation
   */
  function showConfirmation(title: string, message: string, callback: () => void) {
    confirmModalTitle = title;
    confirmModalMessage = message;
    confirmCallback = callback;
    showConfirmModal = true;
  }

  /**
   * Handle confirmation modal confirm
   */
  function handleConfirmModalConfirm() {
    if (confirmCallback) {
      confirmCallback();
      confirmCallback = null;
    }
    showConfirmModal = false;
  }

  /**
   * Handle confirmation modal cancel
   */
  function handleConfirmModalCancel() {
    confirmCallback = null;
    showConfirmModal = false;
  }

  /**
   * Handle force delete of processing files
   */
  async function handleForceDelete(conflictFileIds: string[]) {
    try {
      // Try force deletion for conflicted files
      const forceResponse = await axiosInstance.post('/files/management/bulk-action', {
        file_uuids: conflictFileIds,  // Use file_uuids (UUIDs)
        action: 'delete',
        force: true
      });
      
      const forceResults = forceResponse.data;
      const forceSuccessful = forceResults.filter((r: any) => r.success);
      
      if (forceSuccessful.length > 0) {
        toastStore.success(`Force deleted ${forceSuccessful.length} processing file(s).`);
        // Remove force deleted files smoothly
        const forceSuccessfulIds = forceSuccessful.map((r: any) => r.file_uuid);  // Use file_uuid from response
        removeFilesSmooth(forceSuccessfulIds);
      }
    } catch (forceErr) {
      console.error('Error force deleting files:', forceErr);
      toastStore.error('Failed to force delete some files. They may require admin intervention.');
    }
    
    clearSelection();
  }
  
  // Fetch media files with smooth update support
  async function fetchFiles(isInitialLoad: boolean = false, skipAnimation: boolean = false) {
    // Only show loading state on initial load
    if (isInitialLoad || files.length === 0) {
      loading = true;
    }
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
      
      let newFiles: MediaFile[] = [];
      
      // If a collection is selected, fetch files from that collection
      if (selectedCollectionId !== null) {
        const response = await axiosInstance.get(`/api/collections/${selectedCollectionId}/media`, { params });
        newFiles = response.data;
      } else {
        const response = await axiosInstance.get('/files', { params });
        newFiles = response.data;
      }
      
      // Update files with smooth transitions
      if (!skipAnimation && files.length > 0 && !isInitialLoad) {
        updateFilesSmooth(newFiles);
      } else {
        files = newFiles;
        galleryStore.setFiles(newFiles);
        updateFileMap();
      }
      
    } catch (err) {
      console.error('Error fetching files:', err);
      error = 'Failed to load media files. Please try again.';
    } finally {
      loading = false;
    }
  }
  
  // Update file map for efficient lookups
  function updateFileMap() {
    fileMap.clear();
    files.forEach(file => {
      fileMap.set(file.id, file);
    });
  }
  
  // Smooth file list updates without full re-render
  function updateFilesSmooth(newFiles: MediaFile[]) {
    const newFileMap = new Map<string, MediaFile>();
    newFiles.forEach(file => newFileMap.set(file.id, file));

    // Identify truly new files (not in current list)
    const existingIds = new Set(files.map(f => f.id));
    const newIds = newFiles.map(f => f.id).filter(id => !existingIds.has(id));

    // Only mark files as new if this is not an initial load
    // (Don't highlight on page navigation, only on actual new uploads)
    if (files.length > 0 && newIds.length > 0) {
      // Mark new files for entrance animation
      newIds.forEach(id => pendingNewFiles.add(id));

      // Clear new file markers after animation
      setTimeout(() => {
        newIds.forEach(id => pendingNewFiles.delete(id));
      }, 600);
    }

    // Update the files array
    files = newFiles;
    galleryStore.setFiles(newFiles);
    updateFileMap();
  }
  
  // Add a single new file smoothly to the top
  function addNewFileSmooth(newFile: MediaFile) {
    // Check if file already exists
    if (fileMap.has(newFile.id)) {
      // Update existing file
      files = files.map(f => f.id === newFile.id ? newFile : f);
      fileMap.set(newFile.id, newFile);
      return;
    }
    
    // Add new file to the beginning
    pendingNewFiles.add(newFile.id);
    files = [newFile, ...files];
    fileMap.set(newFile.id, newFile);
    
    // Clear new file marker after animation
    setTimeout(() => {
      pendingNewFiles.delete(newFile.id);
    }, 600);
  }
  
  // Throttled refresh function to prevent spam
  function throttledRefresh(key: string, delay: number = 500) {
    if (refreshTimeouts.has(key)) {
      clearTimeout(refreshTimeouts.get(key) as any);
    }

    const timeoutId = setTimeout(() => {
      fetchFiles(false, true); // Skip animation for throttled refreshes
      refreshTimeouts.delete(key);
    }, delay);

    refreshTimeouts.set(key, timeoutId as any);
  }
  
  // Remove files smoothly with animation
  function removeFilesSmooth(fileIds: string[]) {
    // Mark files for deletion animation
    fileIds.forEach(id => {
      if (fileMap.has(id)) {
        pendingDeletions.add(id);
      }
    });

    // Wait for exit animation to complete, then remove from array
    setTimeout(() => {
      files = files.filter(file => !fileIds.includes(file.id));
      fileIds.forEach(id => {
        fileMap.delete(id);
        pendingDeletions.delete(id);
      });
    }, 250); // Match fade out animation duration
  }

  // Remove single file smoothly
  function removeFileSmooth(fileId: string) {
    removeFilesSmooth([fileId]);
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
  function toggleFileSelection(fileId: string, event: Event) {
    if (event) {
      event.stopPropagation();
      event.preventDefault();
    }

    galleryStore.toggleFileSelection(fileId);
  }

  // Select all files
  function selectAllFiles() {
    galleryStore.selectAllFiles();
  }

  // Clear selection
  function clearSelection() {
    galleryStore.clearSelection();
  }

  // Toggle filter sidebar for mobile
  function toggleFilters() {
    galleryStore.toggleFilters();
  }
  
  // Toggle upload modal
  function toggleUploadModal() {
    showUploadModal = !showUploadModal;
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

    // Skip animation when resetting filters to avoid highlighting previously filtered items
    fetchFiles(false, true);
  }
  
  // Delete selected files with enhanced error handling
  async function deleteSelectedFiles() {
    if (selectedFiles.size === 0) return;
    
    showConfirmation(
      'Delete Selected Files',
      `Are you sure you want to delete ${selectedFiles.size} selected file(s)? This action cannot be undone.`,
      () => executeDeleteSelectedFiles()
    );
  }

  /**
   * Execute delete selected files after confirmation
   */
  async function executeDeleteSelectedFiles() {
    try {
      // Don't show loading state - use smooth animations instead
      
      // Use bulk action API for better error handling
      const response = await axiosInstance.post('/files/management/bulk-action', {
        file_uuids: Array.from(selectedFiles),  // Use file_uuids (UUIDs)
        action: 'delete',
        force: false
      });
      
      const results = response.data;
      const successful = results.filter((r: any) => r.success);
      const failed = results.filter((r: any) => !r.success);
      
      // Handle conflicts (files that can't be deleted)
      const conflicts = failed.filter((r: any) => r.error === 'HTTP_ERROR' && r.message.includes('FILE_NOT_SAFE_TO_DELETE'));

      if (conflicts.length > 0) {
        const conflictFileIds = conflicts.map((c: any) => c.file_uuid);  // Use file_uuid from response
        showConfirmation(
          'Force Delete Processing Files',
          `${conflicts.length} file(s) are currently processing and cannot be deleted safely. ` +
          `Would you like to cancel their processing and delete them? ` +
          `(This action cannot be undone)`,
          () => handleForceDelete(conflictFileIds)
        );
        return; // Exit early to wait for user confirmation
      }
      
      // Report on regular deletion results
      if (successful.length > 0) {
        toastStore.success(`Successfully deleted ${successful.length} file(s).`);
        // Remove successfully deleted files smoothly
        const successfulIds = successful.map((r: any) => r.file_uuid);  // Use file_uuid from response
        removeFilesSmooth(successfulIds);
      }
      
      if (failed.length > 0) {
        toastStore.error(`Failed to delete ${failed.length} file(s). Please try again.`);
      }
      
      clearSelection();
      
    } catch (err: any) {
      console.error('Error deleting files:', err);
      const errorMessage = err.response?.data?.detail || 'An error occurred while deleting files. Please try again.';
      toastStore.error(errorMessage);
    } finally {
      // No need to set loading = false since we didn't set it to true
    }
  }

  // File upload completed handler
  function handleUploadComplete(event: CustomEvent) {
    // For URL uploads, don't immediately refresh - let WebSocket notifications handle it
    // This prevents showing loading state while YouTube/URL processing happens in background
    const isUrl = event.detail?.isUrl || false;
    const isDuplicate = event.detail?.isDuplicate || false;
    
    if (!isUrl) {
      // For file uploads, do a smooth refresh since files are ready to display
      throttledRefresh('upload-complete', 300);
    }
    // For URL uploads, the gallery will refresh when WebSocket notifications arrive
    
    // Only close the modal if not a duplicate file
    // For duplicates, we want to keep the modal open to show the notification
    if (!isDuplicate) {
      showUploadModal = false;
    }
  }



  // Enhanced error notification using backend categorization
  function showEnhancedErrorNotification(file: MediaFile) {
    // Use backend-provided error categorization
    if (file.error_category && file.error_suggestions) {
      const suggestions = file.error_suggestions.map(s => `• ${s}`).join('\n');
      toastStore.error(
        `${file.user_message || `Processing failed for "${file.title || file.filename}"`}\n\n` +
        `Suggestions:\n${suggestions}`,
        file.error_category === 'file_quality' ? 10000 : 8000
      );
    } else {
      // Minimal fallback for unexpected cases
      toastStore.error(`Processing failed for "${file.title || file.filename}". Please try again.`);
    }
  }
  
  // Subscribe to WebSocket file status updates to update file status in real-time
  // Track processed notifications to avoid duplicate processing
  let processedNotificationIds = new Set<string>();
  let previousActiveUploadCount = 0;

  // Periodic cleanup to prevent processedNotificationIds from growing too large
  setInterval(() => {
    if (processedNotificationIds.size > 1000) {
      processedNotificationIds.clear();
    }
  }, 300000); // Clean up every 5 minutes

  function setupWebSocketUpdates() {
    unsubscribeFileStatus = websocketStore.subscribe(($ws) => {
      if ($ws.notifications.length > 0) {
        // Process all unprocessed notifications, not just the latest one
        const unprocessedNotifications = $ws.notifications.filter(notification =>
          !processedNotificationIds.has(notification.id)
        );

        if (unprocessedNotifications.length > 0) {
          // Mark all as processed immediately to avoid race conditions
          unprocessedNotifications.forEach(notification => {
            processedNotificationIds.add(notification.id);
          });

          // Process each unprocessed notification
          let filesUpdated = false;

          unprocessedNotifications.forEach(notification => {
            // Handle different notification types
            if (notification.type === 'file_deleted' && notification.data?.file_id) {
              const fileId = String(notification.data.file_id);
              removeFileSmooth(fileId);
            }
            else if (notification.type === 'transcription_status' && notification.data?.file_id) {
              const fileId = String(notification.data.file_id);  // UUID string
              const status = notification.data.status;

              // FIX: Update both status and display_status for concurrent upload status tracking
              // This ensures gallery items show correct status during multiple file processing
              // instead of staying stuck on "Pending" while notifications work correctly
              const updatedFiles = files.map(file => {
                if (file.id === fileId) {
                  const updatedFile = {
                    ...file,
                    status: status,
                    // Update display_status to ensure UI shows correct status immediately
                    display_status: status === 'processing' ? 'Processing' :
                                   status === 'completed' ? 'Completed' :
                                   status === 'pending' ? 'Pending' :
                                   status === 'error' ? 'Error' : status
                  };
                  // Update the file map immediately for consistent lookups
                  fileMap.set(fileId, updatedFile);  // Use fileId (UUID) directly
                  filesUpdated = true;
                  return updatedFile;
                }
                return file;
              });

              // Force Svelte reactivity by creating new array reference
              files = updatedFiles;

              // If the file status changed to error, refresh to get the latest error message
              if (status === 'error') {
                throttledRefresh('error-' + fileId, 300);
              }

              // For completed status, don't refresh immediately since we expect a file_updated notification
              // to arrive shortly with complete updated data. This prevents race conditions.
              if (status === 'completed') {
                // Wait a bit longer for the file_updated notification, then refresh if needed
                setTimeout(() => {
                  const currentFile = fileMap.get(fileId);  // Use fileId (UUID) directly
                  if (currentFile && currentFile.status !== 'completed') {
                    throttledRefresh('completed-fallback-' + fileId, 100);
                  }
                }, 800);
              }
            }
            // Handle new file uploads with smooth addition
            else if (notification.type === 'file_upload' || notification.type === 'file_created') {
              if (notification.data?.file) {
                // Add the new file smoothly without full refresh
                addNewFileSmooth(notification.data.file);
              } else {
                // Fallback to throttled refresh if no file data provided
                throttledRefresh('new-file', 500);
              }
            }
            // Handle file updates (metadata, processing completion, etc.)
            else if (notification.type === 'file_updated' && notification.data?.file_id) {
              const fileId = String(notification.data.file_id);  // UUID string

              // Try to update the file in place first
              let fileExists = false;
              let updatedFile = null;
              files = files.map(file => {
                if (file.id === fileId) {  // Compare UUIDs directly
                  fileExists = true;
                  // If we have full file data, use it; otherwise merge notification data
                  if (notification.data.file) {
                    updatedFile = {
                      ...file,
                      ...notification.data.file
                    };
                  } else {
                    const newStatus = notification.data.status || file.status;
                    updatedFile = {
                      ...file,
                      status: newStatus,
                      display_status: notification.data.display_status || file.display_status,
                      thumbnail_url: notification.data.thumbnail_url || file.thumbnail_url,
                    };
                  }
                  return updatedFile;
                }
                return file;
              });

              // Update the file map immediately for consistent lookups
              if (fileExists && updatedFile) {
                fileMap.set(fileId, updatedFile);  // Use fileId (UUID) directly
                filesUpdated = true;
              } else {
                // Only fetch if file doesn't exist in current list (new file)
                if (notification.data.file) {
                  addNewFileSmooth(notification.data.file);
                } else {
                  throttledRefresh('update-' + fileId, 300);
                }
              }
            }
          });

          // Batch update gallery store and file map once after processing all notifications
          if (filesUpdated) {
            galleryStore.setFiles(files);
            updateFileMap();
          }
        }
      }
    });
    
    // Also subscribe to upload store to detect when uploads finish
    const unsubscribeUploads = uploadsStore.subscribe(($uploads) => {
      const currentActiveUploadCount = $uploads.uploads.filter(u => 
        ['uploading', 'processing', 'preparing'].includes(u.status)
      ).length;
      
      // If active upload count decreased to 0, do a smooth refresh
      if (previousActiveUploadCount > 0 && currentActiveUploadCount === 0) {
        throttledRefresh('uploads-complete', 800); // Slightly longer delay for upload completion
      }
      
      previousActiveUploadCount = currentActiveUploadCount;
    });
    
    // Return cleanup function for uploads subscription
    const originalUnsubscribe = unsubscribeFileStatus;
    unsubscribeFileStatus = () => {
      if (originalUnsubscribe) originalUnsubscribe();
      if (unsubscribeUploads) unsubscribeUploads();
      // Clear processed notification IDs to prevent memory leaks
      processedNotificationIds.clear();
    };
  }
  
  onMount(() => {
    // Update document title
    document.title = 'Gallery | OpenTranscribe';
    
    // Setup WebSocket subscription for real-time updates
    setupWebSocketUpdates();
    
    // Listen for events to open Add Media modal
    const handleOpenModalEvent = (event: CustomEvent) => {
      showUploadModal = true;
      // Dispatch a separate event for the FileUploader after the modal is shown
      setTimeout(() => {
        if (event.detail?.activeTab) {
          window.dispatchEvent(new CustomEvent('setFileUploaderTab', {
            detail: { activeTab: event.detail.activeTab }
          }));
        }
      }, 50);
    };

    // Listen for direct file upload from recording popup
    const handleUploadRecordedFile = (event: CustomEvent) => {
      if (event.detail?.file) {
        showUploadModal = true;
        // Trigger file upload directly
        setTimeout(() => {
          window.dispatchEvent(new CustomEvent('directFileUpload', {
            detail: { file: event.detail.file }
          }));
        }, 100);
      }
    };
    
    window.addEventListener('openAddMediaModal', handleOpenModalEvent as EventListener);
    window.addEventListener('uploadRecordedFile', handleUploadRecordedFile as EventListener);

    fetchFiles(true); // Initial load

    // Return cleanup function
    return () => {
      window.removeEventListener('openAddMediaModal', handleOpenModalEvent as EventListener);
      window.removeEventListener('uploadRecordedFile', handleUploadRecordedFile as EventListener);
    };
  });
  
  onDestroy(() => {
    // Clean up WebSocket subscription when component is destroyed
    if (unsubscribeFileStatus) {
      unsubscribeFileStatus();
    }
    
    // Clean up any pending refresh timeouts
    refreshTimeouts.forEach((timeoutId) => {
      clearTimeout(timeoutId);
    });
    refreshTimeouts.clear();
  });

  // Set up store-based action triggers
  onMount(() => {
    // Subscribe to gallery action triggers (initial values are now handled in store)
    const unsubscribeUpload = galleryStore.onUploadTrigger(() => {
      toggleUploadModal();
    });

    const unsubscribeCollections = galleryStore.onCollectionsTrigger(() => {
      showCollectionsModal = true;
    });

    const unsubscribeAddToCollection = galleryStore.onAddToCollectionTrigger(() => {
      showCollectionsModal = true;
    });

    const unsubscribeDeleteSelected = galleryStore.onDeleteSelectedTrigger(() => {
      deleteSelectedFiles();
    });

    // Cleanup subscriptions
    return () => {
      unsubscribeUpload();
      unsubscribeCollections();
      unsubscribeAddToCollection();
      unsubscribeDeleteSelected();
    };
  });
</script>

<!-- Main container with fixed height -->
<div class="media-library-container">
  {#if activeTab === 'gallery'}
    <div class="gallery-tab-wrapper">
      <!-- Left Sidebar: Filters (Sticky) -->
      <div class="filter-sidebar {showFilters ? 'show' : ''}">
        <!-- Filters Toggle Button (always visible) -->
        <div class="filter-toggle-container">
          <button
            class="filter-toggle-btn {showFilters ? 'expanded' : 'collapsed'}"
            on:click={toggleFilters}
            title="{showFilters ? 'Hide' : 'Show'} filters panel"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"></polygon>
            </svg>
            {#if showFilters}
              <span class="filter-toggle-text">Hide Filters</span>
            {/if}
          </button>
        </div>

        <!-- Filter Content (hidden when collapsed) -->
        {#if showFilters}
          <div class="filter-content">
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
        {/if}
      </div>

      <!-- Right Content: Scrollable Media Grid -->
      <div class="content-area">
        <div class="scrollable-content">
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
              class="file-card {selectedFiles.has(file.id) ? 'selected' : ''} {pendingNewFiles.has(file.id) ? 'new-file' : ''} {pendingDeletions.has(file.id) ? 'deleting' : ''}"
              animate:flip={{ duration: 300 }}
              in:scale={{ duration: 300, start: 0.8 }}
              out:fade={{ duration: 250 }}
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
                <a
                  href={isSelecting ? '#' : `/files/${file.id}`}
                  class="file-card-link"
                  on:click={(e) => {
                    if (isSelecting) {
                      e.preventDefault();
                      toggleFileSelection(file.id, e);
                    } else {
                      e.preventDefault();
                      goto(`/files/${file.id}`);
                    }
                  }}
                >
                <div class="file-content">
                  {#if file.thumbnail_url && file.content_type && file.content_type.startsWith('video/')}
                    <div class="file-thumbnail">
                      <img
                        src={file.thumbnail_url}
                        alt="Thumbnail for {file.title || file.filename}"
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

                  <h2 class="file-name">{file.title || file.filename}</h2>

                  <div class="file-meta">
                    <span class="file-date">{file.formatted_upload_date}</span>
                    {#if file.formatted_duration}
                      <span class="file-duration">{file.formatted_duration}</span>
                    {/if}
                  </div>

                  <div class="file-status status-{file.status}" class:clickable-error={file.status === 'error' && file.last_error_message}>
                    <span class="status-dot"></span>
                    {#if file.display_status}
                      <!-- Use backend-provided formatted status only -->
                      {#if file.status === 'error' && file.last_error_message}
                        <!-- svelte-ignore a11y-click-events-have-key-events -->
                        <!-- svelte-ignore a11y-no-static-element-interactions -->
                        <span
                          class="error-details-trigger"
                          on:click|preventDefault|stopPropagation={() => showEnhancedErrorNotification(file)}
                          title="Click for error details"
                        >
                          {file.display_status} - Click for Details
                        </span>
                      {:else}
                        {file.display_status}
                      {/if}
                    {:else}
                      <!-- Fallback to raw status if backend doesn't provide formatted status -->
                      {file.status}
                    {/if}
                  </div>
                </div>
              </a>
            </div>
          {/each}
        </div>
      {/if}
    </div>
  </div>
    </div>
  {:else if activeTab === 'status'}
    <div class="status-tab-content">
      <UserFileStatus />
    </div>
  {/if}
</div>

<!-- Upload Modal -->
{#if showUploadModal}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- The modal backdrop that closes on click -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div
    class="modal-backdrop"
    role="presentation"
    transition:fade={{ duration: 400 }}
    on:click|self={toggleUploadModal}
    on:keydown={(e) => e.key === 'Escape' && toggleUploadModal()}
  >
    <!-- The actual modal dialog -->
    <!-- svelte-ignore a11y-click-events-have-key-events -->
    <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
    <!-- svelte-ignore a11y-no-static-element-interactions -->
    <div
      class="modal-container"
      role="dialog"
      aria-labelledby="upload-modal-title"
      aria-modal="true"
      tabindex="-1"
      transition:scale={{ duration: 350, start: 0.9 }}
      on:click|stopPropagation
      on:keydown|stopPropagation>
      <div class="modal-content">
        <div class="modal-header">
          <h2 id="upload-modal-title">Add Media</h2>
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
  <div
    class="modal-backdrop"
    role="presentation"
    transition:fade={{ duration: 400 }}
    on:click={() => showCollectionsModal = false}
    on:keydown={(e) => e.key === 'Escape' && (() => showCollectionsModal = false)()}
  >
    <!-- svelte-ignore a11y-click-events-have-key-events -->
    <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
    <!-- svelte-ignore a11y-no-static-element-interactions -->
    <div
      class="modal-container"
      role="dialog"
      aria-modal="true"
      transition:scale={{ duration: 350, start: 0.9 }}
      on:click|stopPropagation
      on:keydown|stopPropagation
    >
      <div class="modal-content">
        <div class="modal-header">
          <h2>Manage Collections</h2>
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
              // Only close modal if we're in 'add' mode and actually adding files
              if (selectedFiles.size > 0) {
                showCollectionsModal = false;
                clearSelection();
              }
              // In manage mode, keep the modal open for multiple collections
              
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

<!-- Confirmation Modal -->
<ConfirmationModal
  bind:isOpen={showConfirmModal}
  title={confirmModalTitle}
  message={confirmModalMessage}
  confirmText="Confirm"
  cancelText="Cancel"
  confirmButtonClass="modal-delete-button"
  cancelButtonClass="modal-cancel-button"
  on:confirm={handleConfirmModalConfirm}
  on:cancel={handleConfirmModalCancel}
  on:close={handleConfirmModalCancel}
/>

<style>
  /* Selection controls */
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

  .header-actions {
    display: flex;
    gap: 0.5rem;
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
    border-color: #3b82f6;
  }
  
  .file-checkbox:checked ~ .checkmark {
    background-color: #3b82f6;
    border-color: #3b82f6;
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

  /* Main Container - Fixed Height Layout */
  .media-library-container {
    height: calc(100vh - 60px); /* Full viewport minus navbar only */
    display: flex;
    overflow: hidden;
    padding-top: 0;
  }

  /* Gallery Tab Wrapper */
  .gallery-tab-wrapper {
    display: flex;
    height: 100%;
    width: 100%;
  }
  
  .tab-button {
    color: var(--text-color);
    background: none;
    border: none;
    padding: 0.4rem 0.8rem;
    border-radius: 6px;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-family: inherit;
    font-size: 0.9rem;
    cursor: pointer;
    position: relative;
    font-weight: 500;
  }
  
  .tab-button:hover {
    background-color: var(--hover-color, rgba(0, 0, 0, 0.05));
    color: var(--primary-color);
  }
  
  /* Active state styling - matches navbar */
  .tab-button.active {
    color: var(--primary-color, #3b82f6);
    font-weight: 600;
    background-color: transparent;
    position: relative;
  }
  
  .tab-button.active::after {
    content: '';
    position: absolute;
    bottom: -8px;
    left: 50%;
    transform: translateX(-50%);
    width: calc(100% - 1rem);
    height: 3px;
    background-color: var(--primary-color, #3b82f6);
    border-radius: 2px;
    transition: all 0.3s ease;
    animation: slideIn 0.3s ease-out;
  }
  
  @keyframes slideIn {
    from {
      width: 0;
      opacity: 0;
    }
    to {
      width: calc(100% - 1rem);
      opacity: 1;
    }
  }
  
  .tab-button.active:hover {
    color: var(--primary-color-dark, #2563eb);
    background-color: var(--hover-color, rgba(59, 130, 246, 0.05));
  }
  
  .tab-button.active:hover::after {
    background-color: var(--primary-color-dark, #2563eb);
    width: 100%;
    height: 4px;
  }

  /* Focus states for accessibility */
  .tab-button:focus {
    outline: 2px solid var(--primary-color);
    outline-offset: 2px;
  }
  
  .status-tab-content {
    padding: 1rem;
    width: 100%;
  }
  
  /* Left Sidebar - Sticky Filters */
  .filter-sidebar {
    flex-shrink: 0;
    background-color: var(--surface-color);
    border-right: 1px solid var(--border-color);
    height: 100%;
    display: flex;
    flex-direction: column;
    transition: all 0.3s ease;
    padding-top: 2rem; /* Additional spacing from navbar */
  }

  /* Expanded state */
  .filter-sidebar.show {
    width: 280px;
  }

  /* Collapsed state */
  .filter-sidebar:not(.show) {
    width: 50px; /* Just enough for the toggle button */
  }

  .filter-toggle-container {
    padding: 0 0.5rem;
    margin-bottom: 1rem;
    flex-shrink: 0;
  }

  .filter-sidebar.show .filter-toggle-container {
    padding: 0 1rem;
  }

  .filter-toggle-btn {
    width: 100%;
    background-color: var(--bg-primary);
    color: var(--text-primary);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 0.6rem 1rem;
    font-size: 0.9rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    height: 40px;
    white-space: nowrap;
  }

  .filter-toggle-btn:hover {
    background-color: var(--hover-bg);
    border-color: var(--primary-color);
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
  }

  .filter-toggle-btn:active {
    transform: scale(0.98);
  }

  .filter-toggle-btn svg {
    flex-shrink: 0;
    opacity: 0.8;
  }

  .filter-toggle-btn.collapsed {
    justify-content: center;
    padding: 0.6rem;
    width: auto;
  }

  .filter-content {
    flex: 1;
    overflow-y: auto;
    padding: 0 1rem;
  }

  /* Right Content Area - Scrollable */
  .content-area {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0; /* Allow flex shrinking */
  }

  .scrollable-content {
    flex: 1;
    overflow-y: auto;
    padding: 1.5rem;
    padding-top: 1.5rem; /* Match filter sidebar padding */
  }

  /* Compact Button Styles */
  .compact {
    padding: 0.4rem 0.8rem !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
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
  
  /* Recovery button */
  .recover-btn {
    background-color: #f59e0b;
    color: white;
    border: none;
    padding: 0.6rem 1.2rem;
    border-radius: 10px;
    font-size: 0.95rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  
  .recover-btn:hover {
    background-color: #d97706;
  }
  
  
  /* File grid - moved to combined section below */
  
  .file-card {
    position: relative;
    border: 1px solid var(--border-color);
    background-color: var(--surface-color);
    border-radius: 12px;
    transition: all 0.3s ease-in-out;
    cursor: pointer;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    transform: translateZ(0); /* Enable hardware acceleration */
  }
  
  /* New file animation - subtle highlight that fades quickly */
  .file-card.new-file {
    animation: newFileGlow 0.6s ease-out;
  }

  /* Deleting file animation */
  .file-card.deleting {
    opacity: 0.5;
    transform: scale(0.95);
    transition: all 0.25s ease-out;
    pointer-events: none;
  }

  @keyframes newFileGlow {
    0% {
      transform: scale(1);
      box-shadow: 0 0 15px rgba(59, 130, 246, 0.4);
      border-color: #60a5fa;
    }
    100% {
      transform: scale(1);
      box-shadow: none;
      border-color: var(--border-color);
    }
  }

  /* Dark mode glow uses same animation but with adapted colors via CSS variables */
  :global(.dark) .file-card.new-file {
    animation: newFileGlowDark 0.6s ease-out;
  }

  @keyframes newFileGlowDark {
    0% {
      box-shadow: 0 0 15px rgba(96, 165, 250, 0.3);
      border-color: #60a5fa;
    }
    100% {
      box-shadow: none;
      border-color: var(--border-color);
    }
  }
  
  /* Smooth loading state for existing cards */
  .file-card.loading {
    opacity: 0.7;
    pointer-events: none;
  }
  
  /* Grid container for smooth transitions */
  .file-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 1.5rem;
    /* Enable smooth grid transitions */
    transition: all 0.3s ease;
  }
  
  .file-card:hover {
    transform: translateY(-3px);
    box-shadow: 0 12px 25px -5px rgba(0, 0, 0, 0.15), 0 8px 10px -6px rgba(0, 0, 0, 0.1);
    border-color: var(--border-hover);
  }
  
  /* Smooth hover for thumbnails */
  .file-card:hover .thumbnail-image {
    transform: scale(1.05);
  }
  
  /* Staggered animation for initial load */
  .file-card {
    animation-delay: calc(var(--animation-order, 0) * 0.05s);
  }
  
  .file-card.selected {
    border: 2px solid #3b82f6;
    background-color: rgba(59, 130, 246, 0.05);
    box-shadow: 0 4px 12px rgba(59, 130, 246, 0.15);
  }
  
  :global(.dark) .file-card.selected {
    background-color: rgba(59, 130, 246, 0.1);
    border-color: #60a5fa;
    box-shadow: 0 4px 12px rgba(96, 165, 250, 0.2);
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
  
  
  .file-content {
    padding: 1.5rem;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    flex: 1;
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

  .clickable-error {
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .clickable-error:hover {
    background-color: rgba(239, 68, 68, 0.2);
    transform: translateY(-1px);
    box-shadow: 0 2px 4px rgba(239, 68, 68, 0.2);
  }

  .error-details-trigger {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    text-decoration: underline;
    text-decoration-style: dotted;
  }

  .error-details-trigger:hover {
    text-decoration-style: solid;
  }

  .status-cancelling {
    color: #f59e0b;
    background-color: rgba(245, 158, 11, 0.1);
  }

  .status-cancelled {
    color: #6b7280;
    background-color: rgba(107, 114, 128, 0.1);
  }

  .status-orphaned {
    color: #dc2626;
    background-color: rgba(220, 38, 38, 0.1);
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
    transition: all 0.2s ease;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .modal-close:hover {
    color: var(--text-color);
    background: var(--button-hover);
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
  
  /* Mobile Filter Toggle */
  .mobile-filter-toggle {
    display: none;
    margin-left: auto;
  }

  /* Responsive design */
  @media (max-width: 768px) {
    .media-library-container {
      flex-direction: column;
    }

    .filter-sidebar {
      position: fixed;
      top: 60px;
      left: -100%;
      width: 100%;
      height: calc(100vh - 60px);
      background: var(--surface-color);
      z-index: 1000;
      transition: left 0.3s ease;
      border-right: none;
      border-top: 1px solid var(--border-color);
    }

    .filter-sidebar.show {
      left: 0;
    }

    .content-area {
      width: 100%;
    }

    .scrollable-content {
      padding: 1rem;
    }

    .file-grid {
      grid-template-columns: 1fr;
    }
  }
  
  /* High contrast mode support */
  @media (prefers-contrast: high) {
    .tab-button {
      border: 1px solid transparent;
    }
    
    .tab-button.active {
      color: var(--primary-color);
      font-weight: 700;
    }
    
    .tab-button.active::after {
      height: 4px;
      background-color: var(--primary-color);
    }
    
    .tab-button.active:hover::after {
      height: 5px;
    }
  }
  
  /* Reduced motion support */
  @media (prefers-reduced-motion: reduce) {
    .tab-button,
    .tab-button.active,
    .tab-button.active::after,
    .file-card,
    .file-card.new-file,
    .thumbnail-image {
      transition: none;
      animation: none;
    }
    
    .file-card:hover {
      transform: none;
    }
    
    .file-card:hover .thumbnail-image {
      transform: none;
    }
  }
  
  /* Smooth state transitions for better UX */
  .loading-state {
    transition: opacity 0.3s ease;
  }
  
  .loading-state.entering {
    opacity: 0;
  }
  
  .loading-state.entered {
    opacity: 1;
  }
  
  /* Performance optimizations */
  .file-card {
    will-change: transform;
  }
  
  .thumbnail-image {
    will-change: transform;
  }
  
  /* Loading shimmer effect for better perceived performance */
  @keyframes shimmer {
    0% {
      background-position: -200px 0;
    }
    100% {
      background-position: calc(200px + 100%) 0;
    }
  }
  
  .file-card.loading::after {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: linear-gradient(
      90deg,
      transparent,
      rgba(255, 255, 255, 0.2),
      transparent
    );
    background-size: 200px 100%;
    animation: shimmer 1.5s infinite;
    pointer-events: none;
    z-index: 1;
  }
  
  :global(.dark) .file-card.loading::after {
    background: linear-gradient(
      90deg,
      transparent,
      rgba(255, 255, 255, 0.1),
      transparent
    );
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
    box-shadow: 0 2px 4px rgba(239, 68, 68, 0.2) !important;
  }

  :global(.modal-delete-button:hover) {
    background-color: #dc2626 !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 8px rgba(239, 68, 68, 0.25) !important;
  }

  :global(.modal-cancel-button) {
    background-color: var(--card-background) !important;
    color: var(--text-color) !important;
    border: 1px solid var(--border-color) !important;
    padding: 0.6rem 1.2rem !important;
    border-radius: 10px !important;
    font-size: 0.95rem !important;
    font-weight: 500 !important;
    cursor: pointer !important;
    transition: all 0.2s ease !important;
    box-shadow: var(--card-shadow) !important;
    /* Ensure text is always visible */
    opacity: 1 !important;
  }

  :global(.modal-cancel-button:hover) {
    background-color: #2563eb !important;
    color: white !important;
    border-color: #2563eb !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25) !important;
  }
</style>