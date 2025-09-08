<script lang="ts">
  import { onMount } from 'svelte';
  import axiosInstance from '../lib/axios';
  import { user as userStore } from '../stores/auth';
  import UserManagementTable from '../components/UserManagementTable.svelte';
  
  // Explicitly declare router props to prevent warnings
  export let location = null;
  export let navigate = null;
  export let condition = true;
  
  // Component state
  /** @type {Array<any>} */
  let users = [];
  /** @type {boolean} */
  let loading = true;
  /** @type {string|null} */
  let error = null;
  /** @type {string} */
  let activeTab = 'users';
  
  // Task health monitoring
  /** @type {Array<any>} */
  let stuckTasks = [];
  /** @type {Array<any>} */
  let inconsistentFiles = [];
  /** @type {boolean} */
  let loadingHealth = false;
  /** @type {string|null} */
  let healthError = null;
  /** @type {boolean} */
  let recoveryInProgress = false;
  
  // System stats
  /** @type {{ 
    users: { total: number, new: number }, 
    files: { total: number, new: number, total_duration: number, segments: number }, 
    tasks: { 
      total: number, 
      pending: number, 
      running: number, 
      completed: number, 
      failed: number, 
      success_rate: number, 
      avg_processing_time: number,
      recent: Array<{id: string, type: string, status: string, created_at: string, elapsed: number}>
    },
    speakers: { total: number, avg_per_file: number },
    system: { 
      cpu: { usage: number }, 
      memory: { total: number, available: number, used: number, percent: number }, 
      disk: { total: number, used: number, free: number, percent: number } 
    } 
  }} */
  let stats = {
    users: { total: 0, new: 0 },
    files: { total: 0, new: 0, total_duration: 0, segments: 0 },
    tasks: { 
      total: 0, 
      pending: 0, 
      running: 0, 
      completed: 0, 
      failed: 0, 
      success_rate: 0, 
      avg_processing_time: 0,
      recent: []
    },
    speakers: { total: 0, avg_per_file: 0 },
    system: {
      cpu: { usage: 0 },
      memory: { total: 0, available: 0, used: 0, percent: 0 },
      disk: { total: 0, used: 0, free: 0, percent: 0 }
    }
  };
  
  /**
   * Fetch all users from the API
   */
  async function fetchUsers() {
    loading = true;
    error = null;
    
    try {
      const response = await axiosInstance.get('/admin/users');
      users = response.data;
    } catch (err) {
      console.error('Error fetching users:', err);
      error = err instanceof Error ? err.message : 'Failed to load users';
    } finally {
      loading = false;
    }
  }
  
  /**
   * Fetch system statistics
   */
  async function fetchStats() {
    try {
      const response = await axiosInstance.get('/admin/stats');
      stats = response.data;
    } catch (err) {
      console.error('Error fetching system stats:', err);
      // Don't set error, just log it
    }
  }
  /**
   * Fetch task health data
   */
  async function fetchTaskHealth() {
    loadingHealth = true;
    healthError = null;
    
    try {
      const response = await axiosInstance.get('/tasks/system/health');
      stuckTasks = response.data.stuck_tasks?.items || [];
      inconsistentFiles = response.data.inconsistent_files?.items || [];
    } catch (err) {
      console.error('Error fetching task health:', err);
      healthError = err instanceof Error ? err.message : 'Failed to load task health data';
    } finally {
      loadingHealth = false;
    }
  }

  /**
   * Recover stuck tasks
   */
  async function recoverStuckTasks() {
    if (recoveryInProgress) return;
    
    recoveryInProgress = true;
    try {
      const response = await axiosInstance.post('/tasks/recover-stuck-tasks');
      // Refresh data after recovery
      await fetchTaskHealth();
      // Show success message or handle response as needed
      alert(`Recovery completed: ${response.data.count} tasks processed`);
    } catch (err) {
      console.error('Error recovering tasks:', err);
      const errorMsg = err instanceof Error ? err.message : 'Unknown error occurred';
      alert(`Failed to recover tasks: ${errorMsg}`);
    } finally {
      recoveryInProgress = false;
    }
  }

  /**
   * Fix inconsistent files
   */
  async function fixInconsistentFiles() {
    if (recoveryInProgress) return;
    
    recoveryInProgress = true;
    try {
      const response = await axiosInstance.post('/tasks/fix-inconsistent-files');
      // Refresh data after fix
      await fetchTaskHealth();
      // Show success message or handle response as needed
      alert(`Files fixed: ${response.data.count} files processed`);
    } catch (err) {
      console.error('Error fixing files:', err);
      const errorMsg = err instanceof Error ? err.message : 'Unknown error occurred';
      alert(`Failed to fix files: ${errorMsg}`);
    } finally {
      recoveryInProgress = false;
    }
  }

  /**
   * Recover a specific task that's stuck
   * @param {string} taskId - The ID of the task to recover
   */
  async function recoverTask(taskId) {
    try {
      await axiosInstance.post(`/tasks/system/recover-task/${taskId}`);
      alert('Task recovery initiated successfully');
      // Refresh health data
      fetchTaskHealth();
    } catch (err) {
      console.error('Error recovering task:', err);
      const errorMsg = err instanceof Error ? err.message : 'Unknown error occurred';
      alert(`Failed to recover task: ${errorMsg}`);
    }
  }

  /**
   * Retry a specific file's processing
   * @param {number} fileId - The ID of the media file to retry
   */
  async function retryTask(fileId) {
    try {
      await axiosInstance.post(`/tasks/retry-file/${fileId}`);
      alert('File processing restarted successfully');
      // Refresh health data
      fetchTaskHealth();
    } catch (err) {
      console.error('Error retrying task:', err);
      const errorMsg = err instanceof Error ? err.message : 'Unknown error occurred';
      alert(`Failed to retry task: ${errorMsg}`);
    }
  }

  /**
   * Trigger startup recovery
   */
  async function triggerStartupRecovery() {
    if (recoveryInProgress) return;
    
    recoveryInProgress = true;
    try {
      const response = await axiosInstance.post('/tasks/system/startup-recovery');
      alert('Startup recovery triggered successfully');
      // Refresh health data after a delay
      setTimeout(() => fetchTaskHealth(), 2000);
    } catch (err) {
      console.error('Error triggering startup recovery:', err);
      const errorMsg = err instanceof Error ? err.message : 'Unknown error occurred';
      alert(`Failed to trigger startup recovery: ${errorMsg}`);
    } finally {
      recoveryInProgress = false;
    }
  }

  /**
   * Trigger recovery for all user files
   */
  async function triggerAllUserRecovery() {
    if (recoveryInProgress) return;
    
    if (!confirm('This will recover files for all users. Are you sure?')) {
      return;
    }
    
    recoveryInProgress = true;
    try {
      const response = await axiosInstance.post('/tasks/system/recover-all-user-files');
      alert('All user file recovery triggered successfully');
      // Refresh health data after a delay
      setTimeout(() => fetchTaskHealth(), 2000);
    } catch (err) {
      console.error('Error triggering all user recovery:', err);
      const errorMsg = err instanceof Error ? err.message : 'Unknown error occurred';
      alert(`Failed to trigger all user recovery: ${errorMsg}`);
    } finally {
      recoveryInProgress = false;
    }
  }

  /**
   * Trigger recovery for a specific user's files
   * @param {number} userId - The ID of the user to recover files for
   */
  async function triggerUserRecovery(userId) {
    if (recoveryInProgress) return;
    
    recoveryInProgress = true;
    try {
      const response = await axiosInstance.post(`/tasks/system/recover-user-files/${userId}`);
      alert(`File recovery triggered for user: ${response.data.message}`);
      // Refresh health data after a delay
      setTimeout(() => fetchTaskHealth(), 2000);
    } catch (err) {
      console.error('Error triggering user recovery:', err);
      const errorMsg = err instanceof Error ? err.message : 'Unknown error occurred';
      alert(`Failed to trigger user recovery: ${errorMsg}`);
    } finally {
      recoveryInProgress = false;
    }
  }

  /**
   * Refresh all data
   */
  function refreshData() {
    fetchUsers();
    fetchStats();
    fetchTaskHealth();
  }
  
  /**
   * Format bytes to human-readable size
   * @param {number} bytes - Size in bytes
   * @returns {string} - Formatted size string
   */
  function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';

    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));

    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }
  
  /**
   * Format seconds to human-readable time
   * @param {number} seconds - Time in seconds
   * @returns {string} - Formatted time string
   */
  function formatTime(seconds) {
    if (!seconds) return '0s';
    
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    let result = '';
    if (hours > 0) result += `${hours}h `;
    if (minutes > 0 || hours > 0) result += `${minutes}m `;
    result += `${secs}s`;
    
    return result;
  }
  
  /**
   * Calculate how long a task has been stuck based on timestamp
   * @param {string} timestamp - ISO timestamp string
   * @returns {number} - Time in seconds
   */
  function calculateTimeStuck(timestamp) {
    if (!timestamp) return 0;
    try {
      const timeStamp = new Date(timestamp);
      const now = new Date();
      const diffMs = now.getTime() - timeStamp.getTime();
      return Math.floor(diffMs / 1000); // Convert to seconds
    } catch (error) {
      console.error('Error calculating time stuck:', error);
      return 0;
    }
  }
  
  onMount(() => {
    fetchUsers();
    fetchStats();
    fetchTaskHealth();
  });
</script>

<div class="admin-container">
  <h1>Admin Dashboard</h1>
  
  {#if !$userStore || $userStore?.role !== 'admin'}
    <div class="access-denied">
      <p>You do not have permission to access this page.</p>
    </div>
  {:else}
    <div class="dashboard-tabs">
      <button 
        class="tab-button {activeTab === 'users' ? 'active' : ''}" 
        on:click={() => activeTab = 'users'}
        title="Manage user accounts, roles, and permissions"
      >
        Users
      </button>
      <button 
        class="tab-button {activeTab === 'stats' ? 'active' : ''}" 
        on:click={() => activeTab = 'stats'}
        title="View system statistics and performance metrics"
      >
        Statistics
      </button>
      <button 
        class="tab-button {activeTab === 'task-health' ? 'active' : ''}" 
        on:click={() => { activeTab = 'task-health'; fetchTaskHealth(); }}
        title="Monitor and recover stuck tasks and inconsistent files"
      >
        Task Health
      </button>
      <button 
        class="tab-button {activeTab === 'settings' ? 'active' : ''}" 
        on:click={() => activeTab = 'settings'}
        title="Configure system settings and preferences"
      >
        Settings
      </button>
    </div>
    
    {#if error}
      <div class="error-message">
        {error}
      </div>
    {/if}
    
    {#if activeTab === 'users'}
      <div class="users-section">
        <h2>User Management</h2>
        <UserManagementTable 
          {users} 
          {loading} 
          {error} 
          onRefresh={refreshData}
          onUserRecovery={triggerUserRecovery}
        />
      </div>
    {:else if activeTab === 'stats'}
      <div class="stats-section">
        <h2>System Statistics</h2>
        
        <div class="stats-grid">
          <!-- User Stats -->
          <div class="stat-card">
            <h3>Users</h3>
            <div class="stat-value">{stats.users?.total || 0}</div>
            <div class="stat-detail">New (Last 7 days): {stats.users?.new || 0}</div>
          </div>
          
          <!-- Media Stats -->
          <div class="stat-card">
            <h3>Media Files</h3>
            <div class="stat-value">{stats.files?.total || 0}</div>
            <div class="stat-detail">
              <span>New (Last 7 days): {stats.files?.new || 0}</span>
              <span>Total Duration: {formatTime(stats.files?.total_duration || 0)}</span>
              <span>Transcript Segments: {stats.files?.segments || 0}</span>
            </div>
          </div>
          
          <!-- Task Status Stats -->
          <div class="stat-card">
            <h3>Tasks Status</h3>
            <div class="stat-value">{stats.tasks?.total || 0} Total</div>
            <div class="stat-detail">
              <span>Pending: {stats.tasks?.pending || 0}</span>
              <span>Running: {stats.tasks?.running || 0}</span>
              <span>Completed: {stats.tasks?.completed || 0}</span>
              <span>Failed: {stats.tasks?.failed || 0}</span>
            </div>
          </div>

          <!-- Task Performance Stats -->
          <div class="stat-card">
            <h3>Task Performance</h3>
            <div class="stat-value">{stats.tasks?.success_rate || 0}% Success</div>
            <div class="stat-detail">
              <span>Avg Processing Time: {formatTime(stats.tasks?.avg_processing_time || 0)}</span>
            </div>
          </div>
          
          <!-- Speaker Stats -->
          <div class="stat-card">
            <h3>Speakers</h3>
            <div class="stat-value">{stats.speakers?.total || 0}</div>
            <div class="stat-detail">
              <span>Avg per file: {stats.speakers?.avg_per_file || 0}</span>
            </div>
          </div>

          <!-- CPU Stats -->
          <div class="stat-card">
            <h3>CPU Usage</h3>
            <div class="stat-value">{stats.system?.cpu?.usage || 0}%</div>
            <div class="progress-bar">
              <div class="progress-fill" style="width: {stats.system?.cpu?.usage || 0}%"></div>
            </div>
          </div>

          <!-- Memory Stats -->
          <div class="stat-card">
            <h3>Memory Usage</h3>
            <div class="stat-value">{stats.system?.memory?.percent || 0}</div>
            <div class="stat-detail">
              <span>Total: {formatBytes(stats.system?.memory?.total || 0)}</span>
              <span>Used: {formatBytes(stats.system?.memory?.used || 0)}</span>
              <span>Available: {formatBytes(stats.system?.memory?.available || 0)}</span>
            </div>
            <div class="progress-bar">
              <div class="progress-fill" style="width: {stats.system?.memory?.percent || 0}%"></div>
            </div>
          </div>

          <!-- Disk Stats -->
          <div class="stat-card">
            <h3>Disk Usage</h3>
            <div class="stat-value">{stats.system?.disk?.percent || 0}</div>
            <div class="stat-detail">
              <span>Total: {formatBytes(stats.system?.disk?.total || 0)}</span>
              <span>Used: {formatBytes(stats.system?.disk?.used || 0)}</span>
              <span>Free: {formatBytes(stats.system?.disk?.free || 0)}</span>
            </div>
            <div class="progress-bar">
              <div class="progress-fill" style="width: {stats.system?.disk?.percent || 0}%"></div>
            </div>
          </div>
        </div>

        <!-- Recent Tasks -->
        <div class="recent-tasks-section">
          <h3>Recent Tasks</h3>
          <table class="tasks-table">
            <thead>
              <tr>
                <th>Task ID</th>
                <th>Type</th>
                <th>Status</th>
                <th>Created</th>
                <th>Elapsed</th>
              </tr>
            </thead>
            <tbody>
              {#if stats.tasks?.recent && stats.tasks.recent.length > 0}
                {#each stats.tasks.recent as task}
                  <tr>
                    <td>{task.id.substring(0, 8)}...</td>
                    <td>{task.type}</td>
                    <td>
                      <span class="status-badge status-{task.status}">{task.status}</span>
                    </td>
                    <td>{new Date(task.created_at).toLocaleString()}</td>
                    <td>{formatTime(task.elapsed)}</td>
                  </tr>
                {/each}
              {:else}
                <tr>
                  <td colspan="5">No recent tasks found</td>
                </tr>
              {/if}
            </tbody>
          </table>
        </div>
      </div>
    {:else if activeTab === 'task-health'}
      <div class="task-health-section">
        <h2>Task Health Monitoring</h2>
        
        <div class="health-controls">
          <button 
            class="action-button refresh" 
            on:click={fetchTaskHealth}
            disabled={loadingHealth}
            title="Refresh task health data"
          >
            {loadingHealth ? 'Refreshing...' : 'Refresh'}
          </button>
          
          <button 
            class="action-button recover" 
            on:click={recoverStuckTasks}
            disabled={loadingHealth || recoveryInProgress || stuckTasks.length === 0}
            title="Attempt to recover all stuck tasks"
          >
            {recoveryInProgress ? 'Recovering...' : 'Recover All Stuck Tasks'}
          </button>
          
          <button 
            class="action-button fix" 
            on:click={fixInconsistentFiles}
            disabled={loadingHealth || recoveryInProgress || inconsistentFiles.length === 0}
            title="Fix all inconsistent file statuses"
          >
            {recoveryInProgress ? 'Fixing...' : 'Fix All Inconsistent Files'}
          </button>
          
          <button 
            class="action-button startup-recovery" 
            on:click={triggerStartupRecovery}
            disabled={loadingHealth || recoveryInProgress}
            title="Trigger startup recovery to handle files interrupted by crashes or shutdowns"
          >
            {recoveryInProgress ? 'Running...' : 'Startup Recovery'}
          </button>
          
          <button 
            class="action-button all-user-recovery" 
            on:click={triggerAllUserRecovery}
            disabled={loadingHealth || recoveryInProgress}
            title="Recover stuck files for all users - use for system-wide issues"
          >
            {recoveryInProgress ? 'Running...' : 'Recover All User Files'}
          </button>
        </div>
        
        {#if healthError}
          <div class="error-message">
            <p>{healthError}</p>
          </div>
        {/if}
        
        <div class="health-panels">
          <!-- Stuck Tasks Panel -->
          <div class="health-panel">
            <h3>Stuck Tasks <span class="badge">{stuckTasks.length}</span></h3>
            
            {#if loadingHealth}
              <div class="loading-indicator">Loading tasks...</div>
            {:else if stuckTasks.length === 0}
              <p class="empty-state">No stuck tasks found. All tasks are running normally.</p>
            {:else}
              <table class="health-table">
                <thead>
                  <tr>
                    <th>Task ID</th>
                    <th>Media File</th>
                    <th>Status</th>
                    <th>Time Stuck</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {#each stuckTasks as task}
                    <tr>
                      <td title="{task.id}">{task.id.substring(0, 8)}...</td>
                      <td>
                        {#if task.media_file}
                          <a href="/file/{task.media_file.id}" target="_blank" rel="noopener noreferrer">
                            {task.media_file.filename || `File #${task.media_file.id}`}
                          </a>
                        {:else}
                          N/A
                        {/if}
                      </td>
                      <td>
                        <span class="status-badge status-{task.status.toLowerCase().replace('_', '-')}">
                          {task.status}
                        </span>
                      </td>
                      <td>{formatTime(calculateTimeStuck(task.created_at || task.updated_at))}</td>
                      <td>
                        {#if task.media_file}
                          <div class="button-group">
                            <button 
                              class="small-button recover-btn" 
                              on:click={() => recoverTask(task.id)}
                              title="Recover this stuck task"
                            >
                              Recover
                            </button>
                            <button 
                              class="small-button" 
                              on:click={() => retryTask(task.media_file.id)}
                              title="Retry file processing"
                            >
                              Retry File
                            </button>
                          </div>
                        {/if}
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            {/if}
          </div>
          
          <!-- Inconsistent Files Panel -->
          <div class="health-panel">
            <h3>Inconsistent Files <span class="badge">{inconsistentFiles.length}</span></h3>
            
            {#if loadingHealth}
              <div class="loading-indicator">Loading files...</div>
            {:else if inconsistentFiles.length === 0}
              <p class="empty-state">No inconsistent files found. All files have consistent status.</p>
            {:else}
              <table class="health-table">
                <thead>
                  <tr>
                    <th>File ID</th>
                    <th>Filename</th>
                    <th>File Status</th>
                    <th>Task Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {#each inconsistentFiles as file}
                    <tr>
                      <td>{file.id}</td>
                      <td>
                        <a href="/file/{file.id}" target="_blank" rel="noopener noreferrer">
                          {file.filename || `File #${file.id}`}
                        </a>
                      </td>
                      <td>
                        <span class="status-badge status-{file.status.toLowerCase().replace('_', '-')}">
                          {file.status}
                        </span>
                      </td>
                      <td>
                        {#if file.latest_task}
                          <span class="status-badge status-{file.latest_task.status.toLowerCase().replace('_', '-')}">
                            {file.latest_task.status}
                          </span>
                        {:else}
                          <span class="status-badge status-unknown">NO TASK</span>
                        {/if}
                      </td>
                      <td>
                        <button 
                          class="small-button" 
                          on:click={() => retryTask(file.id)}
                          title="Retry processing this file"
                        >
                          Retry
                        </button>
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            {/if}
          </div>
        </div>
      </div>
    {:else if activeTab === 'settings'}
      <div class="settings-section">
        <h2>System Settings</h2>
        
        <div class="settings-form">
          <p>System settings management is coming soon.</p>
        </div>
      </div>
    {/if}
  {/if}
</div>

<style>
  .admin-container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 1rem;
  }
  
  h1 {
    font-size: 1.5rem;
    margin-bottom: 1.5rem;
    color: var(--text-color);
  }
  
  h2 {
    font-size: 1.2rem;
    margin-top: 0;
    margin-bottom: 1.5rem;
    color: var(--text-color);
  }

  h3 {
    font-size: 1.1rem;
    margin-top: 1.5rem;
    margin-bottom: 1rem;
    color: var(--text-color);
  }
  
  .dashboard-tabs {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 1.5rem;
    border-bottom: 1px solid var(--border-color);
    padding-bottom: 0.5rem;
  }
  
  .tab-button {
    background: none;
    border: none;
    padding: 0.6rem 1.2rem;
    font-size: 0.95rem;
    font-weight: 500;
    color: var(--text-light);
    cursor: pointer;
    border-radius: 10px 10px 0 0;
    transition: all 0.2s ease;
  }
  
  .tab-button:hover:not(:disabled),
  .tab-button:focus:not(:disabled) {
    color: #3b82f6;
    background-color: rgba(59, 130, 246, 0.1);
  }
  
  .tab-button.active {
    color: #3b82f6;
    border-bottom: 2px solid #3b82f6;
    background-color: rgba(59, 130, 246, 0.05);
  }
  
  .users-section, .stats-section, .settings-section {
    background-color: var(--surface-color);
    border-radius: 8px;
    padding: 1.5rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  }
  
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
    gap: 1rem;
    margin-bottom: 1.5rem;
  }
  
  .stat-card {
    background-color: var(--background-color);
    border-radius: 8px;
    padding: 1.5rem;
    text-align: center;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
    transition: transform 0.2s, box-shadow 0.2s;
  }

  .stat-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  }
  
  .stat-card h3 {
    font-size: 1rem;
    margin: 0 0 0.5rem;
    color: var(--text-light);
  }
  
  .stat-value {
    font-size: 1.5rem;
    font-weight: 500;
    color: var(--primary-color);
    margin-bottom: 0.5rem;
  }
  
  .stat-detail {
    font-size: 0.85rem;
    color: var(--text-light);
    margin-top: 0.5rem;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .progress-bar {
    width: 100%;
    height: 8px;
    background-color: #e0e0e0;
    border-radius: 4px;
    margin-top: 0.75rem;
    overflow: hidden;
  }

  .progress-fill {
    height: 100%;
    background-color: var(--primary-color);
    border-radius: 4px;
  }
  
  .error-message {
    background-color: rgba(239, 68, 68, 0.1);
    color: var(--error-color);
    padding: 0.75rem;
    border-radius: 4px;
    margin-bottom: 1rem;
  }
  
  .access-denied {
    background-color: rgba(239, 68, 68, 0.1);
    color: var(--error-color);
    padding: 1.5rem;
    border-radius: 8px;
    text-align: center;
  }

  .tasks-table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 1rem;
    font-size: 0.9rem;
  }

  .tasks-table th, .tasks-table td {
    padding: 0.75rem 1rem;
    text-align: left;
    border-bottom: 1px solid var(--border-color);
  }

  .tasks-table th {
    background-color: var(--background-color);
    font-weight: 500;
    color: var(--text-color);
  }

  .tasks-table tr:last-child td {
    border-bottom: none;
  }

  .status-badge {
    display: inline-block;
    padding: 0.25rem 0.5rem;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 500;
  }

  .status-pending {
    background-color: rgba(245, 158, 11, 0.1);
    color: #d97706;
  }

  .status-processing {
    background-color: rgba(59, 130, 246, 0.1);
    color: #3b82f6;
  }

  .status-completed {
    background-color: rgba(16, 185, 129, 0.1);
    color: #10b981;
  }

  .status-failed {
    background-color: rgba(239, 68, 68, 0.1);
    color: #ef4444;
  }

  .recent-tasks-section {
    background-color: var(--background-color);
    border-radius: 8px;
    padding: 1.5rem;
    margin-top: 1.5rem;
  }
  
  /* Task Health Styles */
  .task-health-section {
    background-color: var(--surface-color);
    border-radius: 8px;
    padding: 1.5rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  }
  
  .health-controls {
    display: flex;
    gap: 0.75rem;
    margin-bottom: 1.5rem;
    flex-wrap: wrap;
  }
  
  .action-button {
    padding: 0.6rem 1rem;
    border-radius: 4px;
    font-size: 0.9rem;
    font-weight: 500;
    cursor: pointer;
    border: none;
    transition: all 0.2s ease;
  }
  
  .action-button.refresh {
    background-color: var(--background-color);
    color: var(--text-color);
    border: 1px solid var(--border-color);
  }
  
  .button-group {
    display: flex;
    gap: 0.25rem;
    flex-wrap: wrap;
  }
  
  .small-button.recover-btn {
    background-color: var(--brand-color-light);
    color: var(--bg-color);
  }
  
  .small-button.recover-btn:hover {
    background-color: var(--brand-color);
  }
  
  .action-button.recover {
    background-color: #3b82f6;
    color: white;
  }
  
  .action-button.fix {
    background-color: #10b981;
    color: white;
  }
  
  .action-button:hover:not(:disabled) {
    filter: brightness(0.9);
  }
  
  .action-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  
  .health-panels {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
  }
  
  .health-panel {
    background-color: var(--background-color);
    border-radius: 8px;
    padding: 1.5rem;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  }
  
  .health-panel h3 {
    display: flex;
    align-items: center;
    margin-top: 0;
    margin-bottom: 1rem;
  }
  
  .badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background-color: var(--primary-color);
    color: white;
    border-radius: 999px;
    font-size: 0.75rem;
    padding: 0.25rem 0.6rem;
    margin-left: 0.75rem;
  }
  
  .health-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9rem;
  }
  
  .health-table th, .health-table td {
    padding: 0.75rem;
    text-align: left;
    border-bottom: 1px solid var(--border-color);
  }
  
  .health-table th {
    font-weight: 500;
  }
  
  .health-table tr:last-child td {
    border-bottom: none;
  }
  
  .small-button {
    padding: 0.3rem 0.6rem;
    font-size: 0.8rem;
    border-radius: 4px;
    background-color: var(--primary-color);
    color: white;
    border: none;
    cursor: pointer;
    transition: background-color 0.2s;
  }
  
  .small-button:hover {
    background-color: #2563eb;
  }
  
  .status-unknown {
    background-color: rgba(156, 163, 175, 0.1);
    color: #6b7280;
  }
  
  .empty-state {
    text-align: center;
    color: var(--text-light);
    padding: 2rem 0;
  }
  
  .loading-indicator {
    text-align: center;
    color: var(--text-light);
    padding: 1rem 0;
  }
  
  @media (min-width: 768px) {
    .admin-container {
      padding: 2rem;
    }
  }
</style>
