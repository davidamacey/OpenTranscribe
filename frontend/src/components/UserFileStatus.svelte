<script>
  import { onMount, onDestroy } from 'svelte';
  import axiosInstance from '../lib/axios';
  import { user } from '../stores/auth';
  import { websocketStore } from '../stores/websocket';
  import { toastStore } from '../stores/toast';
  
  // Component state
  let loading = false;
  let error = null;
  let fileStatus = null;
  let selectedFile = null;
  let detailedStatus = null;
  let retryingFiles = new Set();
  
  // Auto-refresh settings (per session, not persistent)
  let autoRefresh = false;
  let refreshInterval = null;
  
  // WebSocket subscription
  let unsubscribeWebSocket = null;
  let lastProcessedNotificationId = '';
  
  onMount(() => {
    fetchFileStatus();
    setupWebSocketUpdates();
  });
  
  async function fetchFileStatus() {
    loading = true;
    error = null;
    
    try {
      const response = await axiosInstance.get('/my-files/status');
      fileStatus = response.data;
    } catch (err) {
      console.error('Error fetching file status:', err);
      error = err.response?.data?.detail || 'Failed to load file status';
    } finally {
      loading = false;
    }
  }
  
  async function fetchDetailedStatus(fileId) {
    try {
      const response = await axiosInstance.get(`/my-files/${fileId}/status`);
      detailedStatus = response.data;
      selectedFile = fileId;
    } catch (err) {
      console.error('Error fetching detailed status:', err);
      error = err.response?.data?.detail || 'Failed to load file details';
    }
  }
  
  async function retryFile(fileId) {
    if (retryingFiles.has(fileId)) return;
    
    retryingFiles.add(fileId);
    retryingFiles = retryingFiles; // Trigger reactivity
    
    try {
      await axiosInstance.post(`/my-files/${fileId}/retry`);
      
      // Refresh status after retry
      await fetchFileStatus();
      if (selectedFile === fileId) {
        await fetchDetailedStatus(fileId);
      }
      
      // Show success message
      showMessage('File retry initiated successfully', 'success');
      
    } catch (err) {
      console.error('Error retrying file:', err);
      const errorMsg = err.response?.data?.detail || 'Failed to retry file';
      showMessage(errorMsg, 'error');
    } finally {
      retryingFiles.delete(fileId);
      retryingFiles = retryingFiles; // Trigger reactivity
    }
  }
  
  async function requestRecovery() {
    loading = true;
    
    try {
      await axiosInstance.post('/my-files/request-recovery');
      showMessage('Recovery process started for your files', 'success');
      
      // Refresh status after a delay
      setTimeout(() => {
        fetchFileStatus();
      }, 2000);
      
    } catch (err) {
      console.error('Error requesting recovery:', err);
      const errorMsg = err.response?.data?.detail || 'Failed to request recovery';
      showMessage(errorMsg, 'error');
    } finally {
      loading = false;
    }
  }
  
  function toggleAutoRefresh() {
    if (autoRefresh) {
      refreshInterval = setInterval(fetchFileStatus, 30000); // Refresh every 30 seconds
    } else {
      if (refreshInterval) {
        clearInterval(refreshInterval);
        refreshInterval = null;
      }
    }
  }
  
  function showMessage(message, type) {
    if (type === 'success') {
      toastStore.success(message);
    } else {
      toastStore.error(message);
    }
  }
  
  function formatFileAge(hours) {
    if (hours < 1) {
      return `${Math.round(hours * 60)} minutes ago`;
    } else if (hours < 24) {
      return `${Math.round(hours)} hours ago`;
    } else {
      return `${Math.round(hours / 24)} days ago`;
    }
  }
  
  function getStatusBadgeClass(status) {
    switch (status) {
      case 'completed': return 'status-completed';
      case 'processing': return 'status-processing';
      case 'pending': return 'status-pending';
      case 'error': return 'status-error';
      default: return 'status-unknown';
    }
  }
  
  // Setup WebSocket updates for real-time file status changes
  function setupWebSocketUpdates() {
    unsubscribeWebSocket = websocketStore.subscribe(($ws) => {
      if ($ws.notifications.length > 0) {
        const latestNotification = $ws.notifications[0];
        
        // Only process if this is a new notification we haven't handled
        if (latestNotification.id !== lastProcessedNotificationId) {
          lastProcessedNotificationId = latestNotification.id;
          
          // Check if this notification is for transcription status
          if (latestNotification.type === 'transcription_status' && latestNotification.data?.file_id) {
            console.log('UserFileStatus received WebSocket update for file:', latestNotification.data.file_id, 'Status:', latestNotification.data.status);
            
            // Refresh file status when we get updates
            fetchFileStatus();
          }
        }
      }
    });
  }
  
  // Cleanup on component destroy
  onDestroy(() => {
    if (refreshInterval) {
      clearInterval(refreshInterval);
    }
    if (unsubscribeWebSocket) {
      unsubscribeWebSocket();
    }
  });
</script>

<div class="file-status-container">
  <div class="header">
    <h2>My Files Status</h2>
    <div class="controls">
      <button 
        class="refresh-btn" 
        on:click={fetchFileStatus}
        disabled={loading}
      >
        {loading ? 'Refreshing...' : 'Refresh'}
      </button>
      
      <label class="auto-refresh-toggle">
        <input 
          type="checkbox" 
          bind:checked={autoRefresh} 
          on:change={() => toggleAutoRefresh()}
        />
        Auto-refresh
      </label>
    </div>
  </div>
  
  {#if error}
    <div class="error-message">
      {error}
    </div>
  {/if}
  
  {#if loading && !fileStatus}
    <div class="loading">Loading file status...</div>
  {:else if fileStatus}
    <div class="status-overview">
      <div class="status-cards">
        <div class="status-card">
          <div class="status-number">{fileStatus.status_counts.total}</div>
          <div class="status-label">Total Files</div>
        </div>
        
        <div class="status-card">
          <div class="status-number">{fileStatus.status_counts.completed}</div>
          <div class="status-label">Completed</div>
        </div>
        
        <div class="status-card">
          <div class="status-number">{fileStatus.status_counts.processing}</div>
          <div class="status-label">Processing</div>
        </div>
        
        <div class="status-card">
          <div class="status-number">{fileStatus.status_counts.pending}</div>
          <div class="status-label">Pending</div>
        </div>
        
        <div class="status-card error">
          <div class="status-number">{fileStatus.status_counts.error}</div>
          <div class="status-label">Errors</div>
        </div>
      </div>
      
      {#if fileStatus.has_problems}
        <div class="problems-section">
          <div class="problems-header">
            <h3>Files That Need Attention</h3>
            <button 
              class="recovery-btn" 
              on:click={requestRecovery}
              disabled={loading}
            >
              Request Recovery for All
            </button>
          </div>
          
          <div class="problem-files">
            {#each fileStatus.problem_files.files as file}
              <div class="problem-file">
                <div class="file-info">
                  <div class="filename">{file.filename}</div>
                  <div class="file-meta">
                    <span class="status-badge {getStatusBadgeClass(file.status)}">
                      {file.status}
                    </span>
                    <span class="file-age">{formatFileAge(file.age_hours)}</span>
                  </div>
                </div>
                
                <div class="file-actions">
                  <button 
                    class="details-btn"
                    on:click={() => fetchDetailedStatus(file.id)}
                  >
                    Details
                  </button>
                  
                  {#if file.can_retry}
                    <button 
                      class="retry-btn"
                      on:click={() => retryFile(file.id)}
                      disabled={retryingFiles.has(file.id)}
                    >
                      {retryingFiles.has(file.id) ? 'Retrying...' : 'Retry'}
                    </button>
                  {/if}
                </div>
              </div>
            {/each}
          </div>
        </div>
      {:else}
        <div class="no-problems">
          <p>✅ All your files are processing normally!</p>
        </div>
      {/if}
      
      {#if fileStatus.recent_files.count > 0}
        <div class="recent-files">
          <h3>Recent Files</h3>
          <div class="recent-files-list">
            {#each fileStatus.recent_files.files as file}
              <div class="recent-file">
                <div class="filename">{file.filename}</div>
                <span class="status-badge {getStatusBadgeClass(file.status)}">
                  {file.status}
                </span>
                <span class="file-age">{formatFileAge(file.age_hours)}</span>
              </div>
            {/each}
          </div>
        </div>
      {/if}
    </div>
  {/if}
  
  {#if detailedStatus && selectedFile}
    <div class="detailed-status-modal" on:click={() => { detailedStatus = null; selectedFile = null; }}>
      <div class="modal-content" on:click|stopPropagation>
        <div class="modal-header">
          <h3>File Details: {detailedStatus.file.filename}</h3>
          <button class="close-btn" on:click={() => { detailedStatus = null; selectedFile = null; }}>×</button>
        </div>
        
        <div class="modal-body">
          <div class="file-details">
            <div class="detail-row">
              <span class="label">Status:</span>
              <span class="status-badge {getStatusBadgeClass(detailedStatus.file.status)}">
                {detailedStatus.file.status}
              </span>
            </div>
            
            <div class="detail-row">
              <span class="label">File Age:</span>
              <span>{formatFileAge(detailedStatus.file_age_hours)}</span>
            </div>
            
            {#if detailedStatus.file.duration}
              <div class="detail-row">
                <span class="label">Duration:</span>
                <span>{Math.round(detailedStatus.file.duration / 60)} minutes</span>
              </div>
            {/if}
            
            {#if detailedStatus.is_stuck}
              <div class="warning">
                ⚠️ This file appears to be stuck in processing
              </div>
            {/if}
            
            {#if detailedStatus.suggestions.length > 0}
              <div class="suggestions">
                <h4>Suggestions:</h4>
                <ul>
                  {#each detailedStatus.suggestions as suggestion}
                    <li>{suggestion}</li>
                  {/each}
                </ul>
              </div>
            {/if}
            
            {#if detailedStatus.can_retry}
              <div class="retry-section">
                <button 
                  class="retry-btn large"
                  on:click={() => retryFile(selectedFile)}
                  disabled={retryingFiles.has(selectedFile)}
                >
                  {retryingFiles.has(selectedFile) ? 'Retrying...' : 'Retry Processing'}
                </button>
              </div>
            {/if}
          </div>
          
          {#if detailedStatus.task_details.length > 0}
            <div class="task-details">
              <h4>Task Details:</h4>
              <div class="tasks-list">
                {#each detailedStatus.task_details as task}
                  <div class="task-item">
                    <div class="task-type">{task.task_type}</div>
                    <div class="task-status {getStatusBadgeClass(task.status)}">{task.status}</div>
                    {#if task.error_message}
                      <div class="task-error">{task.error_message}</div>
                    {/if}
                  </div>
                {/each}
              </div>
            </div>
          {/if}
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  .file-status-container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 1rem;
    color: var(--text-color);
  }
  
  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 2rem;
  }
  
  .header h2 {
    margin: 0;
    color: var(--text-color);
  }
  
  .controls {
    display: flex;
    gap: 1rem;
    align-items: center;
  }
  
  .refresh-btn, .recovery-btn {
    padding: 0.5rem 1rem;
    background: var(--primary-color);
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    transition: all 0.2s ease;
    font-weight: 500;
  }
  
  .refresh-btn:hover, .recovery-btn:hover {
    background: var(--primary-hover);
    transform: translateY(-1px);
  }
  
  .refresh-btn:disabled, .recovery-btn:disabled {
    background: var(--text-light);
    cursor: not-allowed;
    transform: none;
  }
  
  .auto-refresh-toggle {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    cursor: pointer;
    color: var(--text-color);
    font-weight: 500;
  }
  
  .auto-refresh-toggle input[type="checkbox"] {
    width: 16px;
    height: 16px;
    cursor: pointer;
  }
  
  .status-cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 1rem;
    margin-bottom: 2rem;
  }
  
  .status-card {
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 1.5rem;
    text-align: center;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    transition: all 0.2s ease;
  }
  
  .status-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  }
  
  .status-card.error {
    border-color: var(--error-color);
    background: var(--error-background);
  }
  
  :global(.dark) .status-card {
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
  }
  
  :global(.dark) .status-card:hover {
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.4);
  }
  
  .status-number {
    font-size: 2rem;
    font-weight: bold;
    color: var(--text-color);
    margin-bottom: 0.5rem;
  }
  
  .status-label {
    color: var(--text-light);
    font-size: 0.875rem;
  }
  
  .problems-section {
    background: var(--warning-background);
    border: 1px solid var(--warning-border);
    border-radius: 8px;
    padding: 1.5rem;
    margin-bottom: 2rem;
  }
  
  :global(.dark) .problems-section {
    background: rgba(245, 158, 11, 0.1);
    border-color: rgba(245, 158, 11, 0.3);
  }
  
  .problems-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
  }
  
  .problems-header h3 {
    margin: 0;
    color: var(--text-color);
  }
  
  .problem-files {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }
  
  .problem-file {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: var(--background-color);
    padding: 1rem;
    border-radius: 6px;
    border: 1px solid var(--border-color);
    transition: all 0.2s ease;
  }
  
  .problem-file:hover {
    border-color: var(--border-hover);
    transform: translateY(-1px);
  }
  
  .file-info {
    flex: 1;
  }
  
  .filename {
    font-weight: 500;
    margin-bottom: 0.25rem;
    color: var(--text-color);
  }
  
  .file-meta {
    display: flex;
    gap: 1rem;
    align-items: center;
  }
  
  .file-age {
    color: var(--text-light);
    font-size: 0.875rem;
  }
  
  .file-actions {
    display: flex;
    gap: 0.5rem;
  }
  
  .details-btn, .retry-btn {
    padding: 0.25rem 0.75rem;
    font-size: 0.875rem;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .details-btn {
    background: var(--background-color);
    color: var(--text-color);
    border-color: var(--border-color);
  }
  
  .details-btn:hover {
    background: var(--surface-color);
    border-color: var(--border-hover);
  }
  
  .retry-btn {
    background: var(--success-color);
    color: white;
    border-color: var(--success-color);
  }
  
  .retry-btn:hover {
    background: var(--success-hover);
    border-color: var(--success-hover);
    transform: translateY(-1px);
  }
  
  .retry-btn:disabled {
    background: var(--text-light);
    border-color: var(--text-light);
    cursor: not-allowed;
    transform: none;
  }
  
  .status-badge {
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 500;
    text-transform: uppercase;
  }
  
  .status-completed {
    background: rgba(16, 185, 129, 0.1);
    color: #10b981;
  }
  
  .status-processing {
    background: rgba(59, 130, 246, 0.1);
    color: #3b82f6;
  }
  
  .status-pending {
    background: rgba(245, 158, 11, 0.1);
    color: #f59e0b;
  }
  
  .status-error {
    background: rgba(239, 68, 68, 0.1);
    color: #ef4444;
  }
  
  :global(.dark) .status-completed {
    background: rgba(16, 185, 129, 0.2);
    color: #34d399;
  }
  
  :global(.dark) .status-processing {
    background: rgba(59, 130, 246, 0.2);
    color: #60a5fa;
  }
  
  :global(.dark) .status-pending {
    background: rgba(245, 158, 11, 0.2);
    color: #fbbf24;
  }
  
  :global(.dark) .status-error {
    background: rgba(239, 68, 68, 0.2);
    color: #f87171;
  }
  
  .no-problems {
    text-align: center;
    padding: 2rem;
    background: var(--success-background);
    border: 1px solid var(--success-border);
    border-radius: 8px;
    color: var(--success-color);
  }
  
  :global(.dark) .no-problems {
    background: rgba(16, 185, 129, 0.1);
    border-color: rgba(16, 185, 129, 0.3);
    color: #34d399;
  }
  
  .recent-files {
    margin-top: 2rem;
  }
  
  .recent-files h3 {
    color: var(--text-color);
    margin-bottom: 1rem;
  }
  
  .recent-files-list {
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    overflow: hidden;
  }
  
  .recent-file {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--border-color);
    transition: background-color 0.2s ease;
  }
  
  .recent-file:hover {
    background: var(--background-color);
  }
  
  .recent-file:last-child {
    border-bottom: none;
  }
  
  .detailed-status-modal {
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
  
  :global(.dark) .detailed-status-modal {
    background: rgba(0, 0, 0, 0.7);
  }
  
  .modal-content {
    background: var(--background-color);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    max-width: 600px;
    width: 90%;
    max-height: 80vh;
    overflow-y: auto;
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
  }
  
  :global(.dark) .modal-content {
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3), 0 10px 10px -5px rgba(0, 0, 0, 0.2);
  }
  
  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1.5rem;
    border-bottom: 1px solid var(--border-color);
  }
  
  .modal-header h3 {
    margin: 0;
    color: var(--text-color);
  }
  
  .close-btn {
    background: none;
    border: none;
    font-size: 1.5rem;
    cursor: pointer;
    color: var(--text-light);
    transition: color 0.2s ease;
  }
  
  .close-btn:hover {
    color: var(--text-color);
  }
  
  .modal-body {
    padding: 1.5rem;
  }
  
  .detail-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.5rem 0;
    border-bottom: 1px solid var(--border-color);
  }
  
  .label {
    font-weight: 500;
    color: var(--text-color);
  }
  
  .warning {
    background: var(--warning-background);
    color: var(--warning-text);
    padding: 0.75rem;
    border-radius: 4px;
    margin: 1rem 0;
    border: 1px solid var(--warning-border);
  }
  
  :global(.dark) .warning {
    background: rgba(245, 158, 11, 0.2);
    color: #fbbf24;
    border-color: rgba(245, 158, 11, 0.3);
  }
  
  .suggestions {
    margin: 1rem 0;
  }
  
  .suggestions h4 {
    color: var(--text-color);
    margin-bottom: 0.5rem;
  }
  
  .suggestions ul {
    list-style: none;
    padding: 0;
  }
  
  .suggestions li {
    padding: 0.5rem 0;
    color: var(--text-color);
  }
  
  .retry-section {
    text-align: center;
    margin: 1rem 0;
  }
  
  .retry-btn.large {
    padding: 0.75rem 1.5rem;
    font-size: 1rem;
  }
  
  .task-details {
    margin-top: 1.5rem;
    border-top: 1px solid var(--border-color);
    padding-top: 1.5rem;
  }
  
  .task-details h4 {
    color: var(--text-color);
    margin: 0 0 1rem 0;
  }
  
  .tasks-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  
  .task-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.5rem;
    background: var(--surface-color);
    border-radius: 4px;
    border: 1px solid var(--border-color);
  }
  
  .task-type {
    color: var(--text-color);
    font-weight: 500;
  }
  
  .task-error {
    color: var(--error-color);
    font-size: 0.875rem;
    margin-top: 0.25rem;
  }
  
  .loading {
    text-align: center;
    padding: 2rem;
    color: var(--text-light);
  }
  
  .error-message {
    background: var(--error-background);
    color: var(--error-color);
    padding: 1rem;
    border-radius: 4px;
    margin-bottom: 1rem;
    border: 1px solid var(--error-border);
  }
  
  :global(.dark) .error-message {
    background: rgba(239, 68, 68, 0.1);
    border-color: rgba(239, 68, 68, 0.3);
  }
  
  @media (max-width: 768px) {
    .header {
      flex-direction: column;
      align-items: flex-start;
      gap: 1rem;
    }
    
    .controls {
      width: 100%;
      justify-content: space-between;
    }
    
    .problem-file {
      flex-direction: column;
      align-items: flex-start;
      gap: 1rem;
    }
    
    .file-actions {
      align-self: stretch;
      justify-content: flex-end;
    }
    
    .status-cards {
      grid-template-columns: repeat(2, 1fr);
    }
  }
</style>