<script>
  import { onMount, onDestroy } from "svelte";
  import { slide, fade } from 'svelte/transition';
  import { Link } from "svelte-navigator";
  import { user } from "../stores/auth";
  import { setupWebsocketConnection, fileStatusUpdates, lastNotification } from "$lib/websocket";
  
  /** @typedef {object} MediaFile
   * @property {number} id
   * @property {string} filename
   * @property {number} [file_size]
   * @property {string} [content_type]
   * @property {string} [language]
   * @property {string} [upload_time]
   * @property {number} [duration]
   * @property {string} [format]
   * @property {string} [media_format]
   * @property {string} [codec]
   */

  /** @typedef {object} Task
   * @property {string} id
   * @property {number|null} media_file_id
   * @property {string} task_type
   * @property {string} status
   * @property {number} progress
   * @property {string} created_at
   * @property {string} updated_at
   * @property {string|null} completed_at
   * @property {string|null} error_message
   * @property {MediaFile|null} media_file
   * @property {boolean} [showMetadata]
   */

  /** @type {Array<Task>} */
  let tasks = [];
  
  /** @type {boolean} */
  let loading = true;
  
  /** @type {string | null} */
  let error = null;
  
  /** @type {number | null} */
  let refreshInterval = null;
  
  // Track which metadata popups are open
  /** @type {string|null} */
  let openMetadataId = null;
  
  // Subscribe to WebSocket file status updates to update task status
  // Define proper type for updates object with string keys
  /** @type {Object.<string, {status: string, progress?: number}>} */
  let fileUpdates = {};
  
  const unsubscribeFileStatus = fileStatusUpdates.subscribe(updates => {
    // Cast updates to the proper type
    fileUpdates = /** @type {Object.<string, {status: string, progress?: number}>} */ (updates || {});
    if (tasks.length > 0 && Object.keys(fileUpdates).length > 0) {
      let updatedTask = false;
      
      // Find tasks that match updated files and update their status
      tasks = tasks.map(task => {
        if (task.media_file && task.media_file.id) {
          // Convert ID to string for object key access
          const fileIdStr = task.media_file.id.toString();
          
          if (fileUpdates[fileIdStr]) {
            const update = fileUpdates[fileIdStr];
            
            // Convert file status to task status
            let newTaskStatus;
            let newProgress;
            
            if (update.status === 'completed') {
              newTaskStatus = 'completed';
              newProgress = 1.0;
            } else if (update.status === 'processing') {
              newTaskStatus = 'in_progress';
              newProgress = update.progress ? update.progress/100 : task.progress;
            } else if (update.status === 'error') {
              newTaskStatus = 'failed';
              newProgress = 0;
            }
            
            // Only update if we have a new status and it's different
            if (newTaskStatus && task.status !== newTaskStatus) {
              updatedTask = true;
              return {
                ...task,
                status: newTaskStatus,
                progress: newProgress || task.progress
              };
            }
          }
        }
        return task;
      });
      
      // If we updated any tasks, immediately fetch fresh data
      if (updatedTask) {
        fetchTasks();
      }
    }
  });
  
  // Also track general notifications for task updates
  const unsubscribeNotifications = lastNotification.subscribe(notification => {
    // Only process if notification exists and has a type property
    if (notification && typeof notification === 'object' && 'type' in notification) {
      // Use a type assertion to avoid 'type' not existing on type 'never' error
      const typedNotification = /** @type {{type: string}} */ (notification);
      if (typedNotification.type === 'task_status') {
        // Refresh task list when we receive task status notifications
        fetchTasks();
      }
    }
  });
  
  /**
   * Fetch all tasks for the current user
   */
  async function fetchTasks() {
    try {
      loading = true;
      error = null;
      
      // Import axios instance directly in the function to avoid issues
      const axiosInstance = (await import('../lib/axios')).default;
      const response = await axiosInstance.get('/tasks/');
      tasks = response.data;
      console.log("Tasks data received:", tasks);
    } catch (err) {
      console.error('Failed to fetch tasks:', err);
      error = err instanceof Error ? err.message : 'Failed to load tasks';
    } finally {
      loading = false;
    }
  }
  
  /**
   * Format date string to a more readable format
   * @param {string} dateString - ISO date string
   * @return {string} Formatted date string
   */
  function formatDate(dateString) {
    if (!dateString) return 'N/A';
    
    const date = new Date(dateString);
    return new Intl.DateTimeFormat('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    }).format(date);
  }
  
  /**
   * Format duration in seconds to human readable format
   * @param {number} seconds - Duration in seconds
   * @return {string} Formatted duration
   */
  function formatDuration(seconds) {
    if (!seconds && seconds !== 0) return "Unknown";
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    
    let result = "";
    if (hours > 0) {
      result += `${hours.toString().padStart(2, "0")}:`;
    }
    result += `${minutes.toString().padStart(2, "0")}:${remainingSeconds.toString().padStart(2, "0")}`;
    return result;
  }
  
  /**
   * Calculate time elapsed since a date
   * @param {string} dateString - ISO date string
   * @return {string} Time elapsed in human-readable format
   */
  function timeElapsed(dateString) {
    if (!dateString) return 'N/A';
    
    const date = new Date(dateString);
    const now = new Date();
    const diffInSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);
    
    if (diffInSeconds < 60) {
      return `${diffInSeconds} seconds ago`;
    } else if (diffInSeconds < 3600) {
      return `${Math.floor(diffInSeconds / 60)} minutes ago`;
    } else if (diffInSeconds < 86400) {
      return `${Math.floor(diffInSeconds / 3600)} hours ago`;
    } else {
      return `${Math.floor(diffInSeconds / 86400)} days ago`;
    }
  }
  
  /**
   * Get appropriate color class based on task status
   * @param {string} status - Task status
   * @return {string} CSS class name
   */
  function getStatusClass(status) {
    switch (status) {
      case 'pending':
        return 'status-pending';
      case 'in_progress':
        return 'status-in-progress';
      case 'completed':
        return 'status-completed';
      case 'failed':
        return 'status-failed';
      default:
        return '';
    }
  }
  
  /**
   * Format file size in bytes to human readable format
   * @param {number|string} bytes - File size in bytes
   * @return {string} Formatted file size
   */
  function formatFileSize(bytes) {
    // Convert to number if it's a string
    const sizeInBytes = typeof bytes === 'string' ? Number(bytes) : bytes;
    
    if (!sizeInBytes || isNaN(sizeInBytes)) return 'Unknown';
    
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    if (sizeInBytes === 0) return '0 Bytes';
    
    const i = Math.floor(Math.log(sizeInBytes) / Math.log(1024));
    return parseFloat((sizeInBytes / Math.pow(1024, i)).toFixed(2)) + ' ' + sizes[i];
  }
  
  /**
   * Toggle metadata info display for a specific task
   * @param {string} taskId - Task ID
   */
  function toggleMetadataInfo(taskId) {
    // If clicking the same task, toggle it off/on
    if (openMetadataId === taskId) {
      openMetadataId = null;
    } else {
      openMetadataId = taskId;
    }
    
    // Update task objects to include showMetadata property
    tasks = tasks.map(task => ({
      ...task,
      showMetadata: task.id === openMetadataId
    }));
  }
  
  // Lifecycle hooks
  onMount(() => {
    // Setup WebSocket connection
    setupWebsocketConnection(window.location.origin);
    
    fetchTasks();
    // Refresh tasks every 30 seconds as a fallback
    refreshInterval = window.setInterval(fetchTasks, 30000);
    
    return () => {
      if (refreshInterval) window.clearInterval(refreshInterval);
    };
  });
  
  onDestroy(() => {
    if (refreshInterval) {
      clearInterval(refreshInterval);
    }
    
    // Unsubscribe from WebSocket updates
    if (unsubscribeFileStatus) {
      unsubscribeFileStatus();
    }
    
    if (unsubscribeNotifications) {
      unsubscribeNotifications();
    }
  });
</script>

<div class="tasks-container">
  <div class="tasks-header">
    <h1>Tasks</h1>
    
    <div class="tasks-actions">
      <button 
        class="flower-link" 
        on:click={() => {
          const protocol = window.location.protocol;
          const host = window.location.hostname;
          const port = import.meta.env.VITE_FLOWER_PORT || '5555';
          const urlPrefix = import.meta.env.VITE_FLOWER_URL_PREFIX || 'flower';
          // Construct the URL properly with trailing slash
          const url = urlPrefix 
            ? `${protocol}//${host}:${port}/${urlPrefix}/` 
            : `${protocol}//${host}:${port}/`;
          window.open(url, '_blank');
        }}
        aria-label="Open Flower Dashboard"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
        </svg>
        Flower Dashboard
      </button>
      <button class="refresh-button" on:click={fetchTasks}>
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M23 4v6h-6"></path>
          <path d="M1 20v-6h6"></path>
          <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10"></path>
          <path d="M20.49 15a9 9 0 0 1-14.85 3.36L1 14"></path>
        </svg>
        Refresh
      </button>
    </div>
  </div>
  
  {#if loading && tasks.length === 0}
    <div class="loading-container">
      <div class="loading-spinner"></div>
      <p>Loading tasks...</p>
    </div>
  {:else if error}
    <div class="error-container">
      <p class="error-message">{error}</p>
      <button class="retry-button" on:click={fetchTasks}>Try Again</button>
    </div>
  {:else if tasks.length === 0}
    <div class="empty-container">
      <div class="empty-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
        </svg>
      </div>
      <h3>No tasks found</h3>
      <p>There are no processing tasks at the moment.</p>
      <p>When you upload a file for transcription, tasks will appear here.</p>
    </div>
  {:else}
    <div class="tasks-list">
      {#each tasks as task (task.id)}
        <div class="task-card">
          <div class="task-header">
            <div class="task-type">
              {#if task.task_type === 'transcription'}
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path>
                  <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
                  <line x1="12" y1="19" x2="12" y2="23"></line>
                  <line x1="8" y1="23" x2="16" y2="23"></line>
                </svg>
                Transcription
              {:else}
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <line x1="8" y1="6" x2="21" y2="6"></line>
                  <line x1="8" y1="12" x2="21" y2="12"></line>
                  <line x1="8" y1="18" x2="21" y2="18"></line>
                  <line x1="3" y1="6" x2="3.01" y2="6"></line>
                </svg>
                Summarization
              {/if}
            </div>
            <div class="task-status {getStatusClass(task.status)}">
              {#if task.status === 'pending'}
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <line x1="12" y1="2" x2="12" y2="6"></line>
                  <line x1="12" y1="18" x2="12" y2="22"></line>
                  <line x1="4.93" y1="4.93" x2="7.76" y2="7.76"></line>
                  <line x1="16.24" y1="16.24" x2="19.07" y2="19.07"></line>
                  <line x1="2" y1="12" x2="6" y2="12"></line>
                  <line x1="18" y1="12" x2="22" y2="12"></line>
                  <line x1="4.93" y1="19.07" x2="7.76" y2="16.24"></line>
                  <line x1="16.24" y1="7.76" x2="19.07" y2="4.93"></line>
                </svg>
                Pending
              {:else if task.status === 'in_progress'}
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <circle cx="12" cy="12" r="10"></circle>
                  <polyline points="12 6 12 12 16 14"></polyline>
                </svg>
                In Progress
                <span class="task-progress">{Math.round(task.progress * 100)}%</span>
              {:else if task.status === 'completed'}
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                  <polyline points="22 4 12 14.01 9 11.01"></polyline>
                </svg>
                Completed
              {:else if task.status === 'failed'}
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <circle cx="12" cy="12" r="10"></circle>
                  <line x1="15" y1="9" x2="9" y2="15"></line>
                  <line x1="9" y1="9" x2="15" y2="15"></line>
                </svg>
                Failed
              {/if}
              
              <!-- Info button -->
              {#if task.media_file}
                <button class="info-button" on:click|stopPropagation={() => toggleMetadataInfo(task.id)}>
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="12" r="10"></circle>
                    <line x1="12" y1="16" x2="12" y2="12"></line>
                    <line x1="12" y1="8" x2="12.01" y2="8"></line>
                  </svg>
                </button>
              {/if}
            </div>
          </div>
          
          <div class="task-info">
            {#if task.media_file}
              <!-- Media info moved to task-dates section -->
            {/if}
            


            <!-- Metadata popup -->
            {#if task.showMetadata}
              <div class="metadata-popup" transition:slide={{duration: 300}}>
                <h4>File Details</h4>
                <div class="metadata-grid">
                  {#if task.media_file}
                    <div class="metadata-item">
                      <span class="metadata-label">File Name:</span>
                      <span class="metadata-value">{task.media_file.filename}</span>
                    </div>
                    <div class="metadata-item">
                      <span class="metadata-label">File Size:</span>
                      <span class="metadata-value">{task.media_file.file_size !== undefined && task.media_file.file_size !== null ? formatFileSize(task.media_file.file_size) : 'Unknown'}</span>
                    </div>
                    <div class="metadata-item">
                      <span class="metadata-label">Content Type:</span>
                      <span class="metadata-value">{task.media_file.content_type || 'Unknown'}</span>
                    </div>
                    <div class="metadata-item">
                      <span class="metadata-label">Language:</span>
                      <span class="metadata-value">{task.media_file.language || 'Auto-detected'}</span>
                    </div>
                    <div class="metadata-item">
                      <span class="metadata-label">Upload Time:</span>
                      <span class="metadata-value">{formatDate(task.media_file.upload_time)}</span>
                    </div>
                  {/if}
                  <div class="metadata-item">
                    <span class="metadata-label">Task Type:</span>
                    <span class="metadata-value">{task.task_type}</span>
                  </div>
                  <div class="metadata-item">
                    <span class="metadata-label">Task Created:</span>
                    <span class="metadata-value">{formatDate(task.created_at)}</span>
                  </div>
                  {#if task.completed_at}
                    <div class="metadata-item">
                      <span class="metadata-label">Task Completed:</span>
                      <span class="metadata-value">{formatDate(task.completed_at)}</span>
                    </div>
                    <div class="metadata-item">
                      <span class="metadata-label">Processing Time:</span>
                      <span class="metadata-value">{formatDuration(Math.floor((new Date(task.completed_at).getTime() - new Date(task.created_at).getTime()) / 1000))}</span>
                    </div>
                  {/if}
                </div>
              </div>
            {/if}

            {#if task.error_message}
              <div class="error-details">
                <span class="info-label">Error:</span>
                <div class="error-message">{task.error_message}</div>
              </div>
            {/if}
          </div>

          {#if task.status === 'in_progress'}
            <div class="progress-bar-container">
              <div class="progress-bar" style="width: {task.progress * 100}%"></div>
            </div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .tasks-container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 2rem 1rem;
  }

  .tasks-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 2rem;
  }

  .tasks-header h1 {
    font-size: 1.75rem;
    font-weight: 600;
    color: var(--text-color);
    margin: 0;
  }

  .tasks-actions {
    display: flex;
    gap: 1rem;
  }

  .flower-link,
  .refresh-button {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    border-radius: 4px;
    font-weight: 500;
    transition: background-color 0.2s;
    font-size: 0.9rem;
  }

  .flower-link {
    background-color: var(--card-background);
    color: var(--text-color);
    text-decoration: none;
    border: 1px solid var(--border-color);
  }

  .refresh-button {
    background-color: var(--surface-color);
    color: var(--text-color);
    border: 1px solid var(--border-color);
    cursor: pointer;
    font-family: inherit;
  }

  .flower-link:hover,
  .refresh-button:hover {
    background-color: var(--button-hover);
  }

  .loading-container,
  .error-container,
  .empty-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 4rem 2rem;
    text-align: center;
    background-color: var(--surface-color);
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  }

  .loading-spinner {
    border: 3px solid rgba(0, 0, 0, 0.1);
    border-top: 3px solid var(--primary-color);
    border-radius: 50%;
    width: 40px;
    height: 40px;
    animation: spin 1s linear infinite;
    margin-bottom: 1rem;
  }

  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }

  .error-message {
    color: var(--error-color);
    margin-bottom: 1rem;
  }

  .retry-button {
    background-color: var(--primary-color);
    color: white;
    border: none;
    border-radius: 4px;
    padding: 0.5rem 1rem;
    font-family: inherit;
    font-weight: 500;
    cursor: pointer;
  }

  .empty-container {
    color: var(--text-secondary-color);
  }

  .empty-icon {
    color: var(--text-secondary-color);
    opacity: 0.5;
    margin-bottom: 1rem;
  }

  .empty-container h3 {
    margin: 0 0 0.5rem;
    font-weight: 600;
  }

  .empty-container p {
    margin: 0.25rem 0;
  }

  .tasks-list {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
    gap: 1.5rem;
  }

  .task-card {
    background-color: var(--surface-color);
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    overflow: hidden;
  }

  .task-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem;
    border-bottom: 1px solid var(--border-color);
  }

  .task-type {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-weight: 600;
  }

  .task-status {
    padding: 0.25rem 0.75rem;
    border-radius: 100px;
    font-size: 0.8rem;
    font-weight: 500;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .status-pending {
    background-color: var(--background-color);
    color: var(--text-secondary);
  }

  [data-theme='dark'] .status-pending {
    background-color: #334155;
    color: #cbd5e1;
  }

  .status-in-progress {
    background-color: #cff4fc;
    color: #055160;
  }

  [data-theme='dark'] .status-in-progress {
    background-color: #164e63;
    color: #7dd3fc;
  }

  /* Dark mode styles handled through variables in global.css */
  /* These selectors need :global to work properly */
  :global([data-theme='dark']) .file-info-section {
    background-color: rgba(255, 255, 255, 0.05);
  }

  :global([data-theme='dark']) .highlight {
    color: var(--primary-color-light);
  }

  .status-completed {
    background-color: #d1e7dd;
    color: #0f5132;
  }

  [data-theme='dark'] .status-completed {
    background-color: #064e3b;
    color: #6ee7b7;
  }

  .status-failed {
    background-color: #f8d7da;
    color: #842029;
  }

  [data-theme='dark'] .status-failed {
    background-color: #7f1d1d;
    color: #fca5a5;
  }

  .task-progress {
    font-weight: 600;
  }

  .task-info {
    padding: 1rem;
  }

  .file-link {
    color: var(--primary-color);
    text-decoration: none;
    font-weight: 500;
  }

  .file-link:hover {
    text-decoration: underline;
  }

  /* Removed file-info-section class as file info is now at the same level as timing info */

  .highlight {
    font-weight: 600;
    color: var(--primary-color);
  }

  /* Removed highlight-box as it's replaced by highlight-row */

  .task-info-card {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .task-status-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.75rem;
  }

  .status-indicator {
    display: inline-flex;
    align-items: center;
    padding: 0.25rem 0.75rem;
    border-radius: 100px;
    font-weight: 500;
    gap: 0.5rem;
  }
  
  .task-type {
    font-weight: 500;
    color: var(--text-secondary-color);
  }
  
  .file-name-row {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
  }
  
  /* Removed file-info-rows class as we now use consistent info-row styling */
  
  .info-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  
  .info-label {
    font-weight: 600;
    color: var(--text-secondary-color);
    font-size: 0.85rem;
  }
  
  .detail-value {
    font-weight: 500;
  }
  
  .timing-section {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  
  .highlight-row {
    background-color: rgba(var(--primary-color-rgb), 0.1);
    border-radius: 6px;
    padding: 0.5rem;
  }
  
  .info-button {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--text-secondary-color);
    padding: 4px;
    margin-left: 8px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
  }
  
  .info-button:hover {
    background-color: rgba(0, 0, 0, 0.05);
    color: var(--primary-color);
  }
  
  .metadata-popup {
    margin-top: 1rem;
    padding: 1rem;
    background-color: var(--background-color);
    border-radius: 8px;
    border: 1px solid var(--border-color);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  }
  
  .metadata-popup h4 {
    margin-top: 0;
    margin-bottom: 0.75rem;
    font-weight: 600;
    color: var(--text-color);
  }
  
  .metadata-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 0.75rem;
  }
  
  .metadata-item {
    display: flex;
    flex-direction: column;
  }
  
  .metadata-label {
    font-size: 0.8rem;
    font-weight: 600;
    color: var(--text-secondary-color);
  }
  
  .metadata-value {
    font-size: 0.9rem;
    font-weight: 500;
    color: var(--text-color);
  }
  
  .error-details {
    background-color: rgba(var(--error-color-rgb), 0.05);
    border-radius: 4px;
    padding: 0.75rem;
    margin-top: 0.5rem;
  }
  
  .error-details .info-label {
    color: var(--error-color);
  }
  
  .error-details .error-message {
    margin-top: 0.5rem;
    font-family: monospace;
    white-space: pre-wrap;
    font-size: 0.85rem;
  }
  
  .progress-bar-container {
    height: 6px;
    background-color: #e9ecef;
  }
  
  .progress-bar {
    height: 100%;
    background-color: var(--primary-color);
    transition: width 0.3s ease;
  }
  
  @media (max-width: 768px) {
    .tasks-header {
      flex-direction: column;
      align-items: flex-start;
      gap: 1rem;
    }
    
    .tasks-list {
      grid-template-columns: 1fr;
    }
  }
</style>
