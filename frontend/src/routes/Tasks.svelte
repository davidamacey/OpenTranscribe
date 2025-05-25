<script>
  import { onMount, onDestroy } from "svelte";
  import { Link } from "svelte-navigator";
  import { user } from "../stores/auth";
  import { setupWebsocketConnection, fileStatusUpdates, lastNotification } from "$lib/websocket";
  
  /** @type {Array<{
    id: string,
    media_file_id: number | null,
    task_type: string,
    status: string,
    progress: number,
    created_at: string,
    updated_at: string,
    completed_at: string | null,
    error_message: string | null,
    media_file: {
      id: number,
      filename: string
    } | null
  }>} */
  let tasks = [];
  
  /** @type {boolean} */
  let loading = true;
  
  /** @type {string | null} */
  let error = null;
  
  /** @type {number | null} */
  let refreshInterval = null;
  
  // Subscribe to WebSocket file status updates to update task status
  const unsubscribeFileStatus = fileStatusUpdates.subscribe(updates => {
    if (tasks.length > 0 && Object.keys(updates).length > 0) {
      let updatedTask = false;
      
      // Find tasks that match updated files and update their status
      tasks = tasks.map(task => {
        if (task.media_file && updates[task.media_file.id]) {
          const update = updates[task.media_file.id];
          console.log(`Tasks: Received WebSocket update for file ${task.media_file.id}:`, update);
          
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
            console.log(`Tasks: Updating task ${task.id} status from ${task.status} to ${newTaskStatus}`);
            updatedTask = true;
            return {
              ...task,
              status: newTaskStatus,
              progress: newProgress || task.progress
            };
          }
        }
        return task;
      });
      
      // If we updated any tasks, immediately fetch fresh data
      if (updatedTask) {
        console.log('Tasks: Tasks updated via WebSocket, fetching fresh data');
        fetchTasks();
      }
    }
  });
  
  // Also track general notifications for task updates
  const unsubscribeNotifications = lastNotification.subscribe(notification => {
    if (notification && notification.type === 'task_status') {
      console.log('Tasks: Received task status notification:', notification);
      // Refresh task list when we receive task status notifications
      fetchTasks();
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
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                </svg>
              {:else if task.task_type === 'summarization'}
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <line x1="8" y1="6" x2="21" y2="6"></line>
                  <line x1="8" y1="12" x2="21" y2="12"></line>
                  <line x1="8" y1="18" x2="21" y2="18"></line>
                  <line x1="3" y1="6" x2="3.01" y2="6"></line>
                  <line x1="3" y1="12" x2="3.01" y2="12"></line>
                  <line x1="3" y1="18" x2="3.01" y2="18"></line>
                </svg>
              {:else}
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M20.24 12.24a6 6 0 0 0-8.49-8.49L5 10.5V19h8.5z"></path>
                  <line x1="16" y1="8" x2="2" y2="22"></line>
                  <line x1="17.5" y1="15" x2="9" y2="15"></line>
                </svg>
              {/if}
              <span>{task.task_type.charAt(0).toUpperCase() + task.task_type.slice(1)}</span>
            </div>
            <div class={`task-status ${getStatusClass(task.status)}`}>
              <span>{task.status}</span>
              {#if task.status === 'in_progress'}
                <span class="task-progress">{Math.round(task.progress * 100)}%</span>
              {/if}
            </div>
          </div>
          
          <div class="task-info">
            {#if task.media_file}
              <div class="media-info">
                <span class="info-label">File:</span>
                <Link to={`/media/${task.media_file.id}`} class="file-link">
                  {task.media_file.filename}
                </Link>
              </div>
            {/if}
            
            <div class="task-dates">
              <div class="date-info">
                <span class="info-label">Created:</span>
                <span class="date-value">{formatDate(task.created_at)}</span>
                <span class="date-relative">({timeElapsed(task.created_at)})</span>
              </div>
              
              {#if task.completed_at}
                <div class="date-info">
                  <span class="info-label">Completed:</span>
                  <span class="date-value">{formatDate(task.completed_at)}</span>
                  <span class="date-relative">({timeElapsed(task.completed_at)})</span>
                </div>
              {/if}
            </div>
            
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
  
  .media-info {
    margin-bottom: 1rem;
  }
  
  .file-link {
    color: var(--primary-color);
    text-decoration: none;
    font-weight: 500;
  }
  
  .file-link:hover {
    text-decoration: underline;
  }
  
  .task-dates {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-bottom: 1rem;
  }
  
  .date-info {
    display: flex;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 0.5rem;
  }
  
  .info-label {
    font-weight: 600;
    color: var(--text-secondary-color);
    min-width: 80px;
  }
  
  .date-value {
    font-weight: 500;
  }
  
  .date-relative {
    font-size: 0.85rem;
    color: var(--text-secondary-color);
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
