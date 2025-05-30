<script>
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
   * Refresh all data
   */
  function refreshData() {
    fetchUsers();
    fetchStats();
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
  
  onMount(() => {
    fetchUsers();
    fetchStats();
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
        title="View system performance statistics and analytics"
      >
        System Stats
      </button>
      <button 
        class="tab-button {activeTab === 'settings' ? 'active' : ''}" 
        on:click={() => activeTab = 'settings'}
        title="Configure system-wide settings and preferences"
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
  
  @media (min-width: 768px) {
    .admin-container {
      padding: 2rem;
    }
  }
</style>
