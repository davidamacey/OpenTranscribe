<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import axiosInstance from '../lib/axios';
  import { user } from '../stores/auth';
  import { websocketStore } from '../stores/websocket';
  import { toastStore } from '../stores/toast';
  import { t } from '../stores/locale';
  import { getFlowerUrl } from '$lib/utils/url';

  // Helper function to translate status values
  function translateStatus(status: string): string {
    const statusMap: Record<string, string> = {
      'completed': $t('common.completed'),
      'processing': $t('common.processing'),
      'pending': $t('common.pending'),
      'error': $t('common.error'),
      'failed': $t('fileStatus.failed'),
      'in_progress': $t('fileStatus.inProgress'),
      'Completed': $t('common.completed'),
      'Processing': $t('common.processing'),
      'Pending': $t('common.pending'),
      'Error': $t('common.error'),
      'Failed': $t('fileStatus.failed'),
      'In Progress': $t('fileStatus.inProgress'),
    };
    return statusMap[status] || status;
  }

  // Component state
  let loading = false;
  let error: any = null;
  let fileStatus: any = null;
  let selectedFile: any = null;
  let detailedStatus: any = null;
  let retryingFiles = new Set();

  // Auto-refresh settings (enabled by default)
  let refreshInterval: any = null;

  // Tasks section state
  let tasks: any[] = [];
  let tasksLoading = false;
  let tasksError: any = null;
  let showTasksSection = false;

  // Restore tasks section state from session storage
  if (typeof window !== 'undefined') {
    const savedTasksSection = sessionStorage.getItem('showTasksSection');
    if (savedTasksSection === 'true') {
      showTasksSection = true;
    }
  }

  // Task filtering
  let taskFilter = 'all'; // 'all', 'pending', 'in_progress', 'completed', 'failed'
  let taskTypeFilter = 'all'; // 'all', 'transcription', 'summarization'
  let taskAgeFilter = 'all'; // 'all', 'today', 'week', 'month', 'older'
  let taskDateFrom = '';
  let taskDateTo = '';
  let filteredTasks: any[] = [];

  // WebSocket subscription
  let unsubscribeWebSocket: any = null;
  let lastProcessedNotificationId = '';

  onMount(() => {
    fetchFileStatus();
    setupWebSocketUpdates();
    startAutoRefresh();

    // Load tasks if section should be shown
    if (showTasksSection && tasks.length === 0) {
      fetchTasks();
    }
  });

  // Refetch tasks when filters change
  $: if (showTasksSection && (taskFilter || taskTypeFilter || taskAgeFilter || taskDateFrom || taskDateTo)) {
    fetchTasks(true); // Silent reload when filters change
  }

  async function fetchFileStatus(silent = false) {
    if (!silent) {
      loading = true;
    }
    error = null;

    try {
      const response = await axiosInstance.get('/my-files/status');
      fileStatus = response.data;
    } catch (err: any) {
      console.error('Error fetching file status:', err);
      if (!silent) {
        error = err.response?.data?.detail || $t('fileStatus.loadFailed');
      }
    } finally {
      if (!silent) {
        loading = false;
      }
    }
  }

  async function fetchTasks(silent = false) {
    if (!silent) {
      tasksLoading = true;
    }
    tasksError = null;

    try {
      // Build query parameters for backend filtering
      const params = new URLSearchParams();
      if (taskFilter !== 'all') {
        params.append('status', taskFilter);
      }
      if (taskTypeFilter !== 'all') {
        params.append('task_type', taskTypeFilter);
      }
      if (taskAgeFilter !== 'all') {
        params.append('age_filter', taskAgeFilter);
      }
      if (taskDateFrom) {
        params.append('date_from', taskDateFrom);
      }
      if (taskDateTo) {
        params.append('date_to', taskDateTo);
      }

      const queryString = params.toString();
      const url = queryString ? `/tasks/?${queryString}` : '/tasks/';

      const response = await axiosInstance.get(url);
      // Tasks are already filtered and include computed fields from backend
      tasks = response.data;
      filteredTasks = tasks; // No frontend filtering needed
    } catch (err: any) {
      console.error('Error fetching tasks:', err);
      if (!silent) {
        tasksError = err.response?.data?.detail || $t('fileStatus.tasksLoadFailed');
      }
    } finally {
      if (!silent) {
        tasksLoading = false;
      }
    }
  }

  function toggleTasksSection() {
    showTasksSection = !showTasksSection;

    // Save state to session storage
    if (typeof window !== 'undefined') {
      sessionStorage.setItem('showTasksSection', showTasksSection.toString());
    }

    if (showTasksSection && tasks.length === 0) {
      fetchTasks();
    }
  }

  function openFlowerDashboard() {
    // Dynamically construct Flower URL from current location
    const url = getFlowerUrl();
    window.open(url, '_blank');
  }

  async function fetchDetailedStatus(fileId: any) {
    try {
      const response = await axiosInstance.get(`/my-files/${fileId}/status`);
      detailedStatus = response.data;
      selectedFile = fileId;
      // Disable body scrolling when modal opens
      document.body.style.overflow = 'hidden';
    } catch (err: any) {
      console.error('Error fetching detailed status:', err);
      error = err.response?.data?.detail || $t('fileStatus.detailsLoadFailed');
    }
  }

  function closeModal() {
    detailedStatus = null;
    selectedFile = null;
    // Re-enable body scrolling when modal closes
    document.body.style.overflow = '';
  }

  async function retryFile(fileId: any) {
    if (retryingFiles.has(fileId)) return;

    retryingFiles.add(fileId);
    retryingFiles = retryingFiles; // Trigger reactivity

    try {
      await axiosInstance.post(`/my-files/${fileId}/retry`);

      // Refresh status after retry
      await fetchFileStatus(true); // Silent refresh
      if (selectedFile === fileId) {
        await fetchDetailedStatus(fileId);
      }

      // Show success message
      showMessage($t('fileStatus.retryInitiated'), 'success');

    } catch (err: any) {
      console.error('Error retrying file:', err);
      const errorMsg = err.response?.data?.detail || $t('fileStatus.retryFailed');
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
      showMessage($t('fileStatus.recoveryInitiated'), 'success');

      // Refresh status after a delay
      setTimeout(() => {
        fetchFileStatus(true); // Silent refresh
      }, 2000);

    } catch (err: any) {
      console.error('Error requesting recovery:', err);
      const errorMsg = err.response?.data?.detail || $t('fileStatus.recoveryFailed');
      showMessage(errorMsg, 'error');
    } finally {
      loading = false;
    }
  }

  function startAutoRefresh() {
    refreshInterval = setInterval(() => {
      fetchFileStatus(true); // Silent refresh
      if (showTasksSection) {
        fetchTasks(true); // Silent refresh
      }
    }, 30000); // Refresh every 30 seconds
  }

  function showMessage(message: any, type: any) {
    if (type === 'success') {
      toastStore.success(message);
    } else {
      toastStore.error(message);
    }
  }

  // Note: formatFileAge is now handled by the backend - use formatted_file_age field

  function formatDate(dateString: any) {
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

  // Note: formatDuration is now handled by the backend - use formatted_duration field

  // Note: formatFileSize is now handled by the backend - use formatted_file_size field

  // Note: getStatusBadgeClass is now handled by the backend - use status_badge_class field

  // Filtering is now handled by the backend

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

            // Refresh file status when we get updates
            fetchFileStatus(true); // Silent refresh

            // Also refresh tasks if tasks section is open
            if (showTasksSection) {
              fetchTasks(true); // Silent refresh
            }
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
    // Ensure body scrolling is restored if component is destroyed while modal is open
    if (document.body.style.overflow === 'hidden') {
      document.body.style.overflow = '';
    }
  });
</script>

<div class="file-status-container">
  <div class="header">
    <h2>{$t('fileStatus.title')}</h2>
    <div class="controls">
      <button
        class="flower-btn"
        on:click={openFlowerDashboard}
        title={$t('fileStatus.flowerTooltip')}
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
        </svg>
        {$t('nav.flowerDashboard')}
      </button>

      <button
        class="tasks-toggle-btn"
        on:click={toggleTasksSection}
        title={$t('fileStatus.tasksToggleTooltip')}
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M9 11l3 3L22 4"></path>
          <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path>
        </svg>
        {showTasksSection ? $t('fileStatus.hideTasks') : $t('fileStatus.showAllTasks')}
      </button>

      <div class="auto-refresh-info">
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"/>
          <path d="M12 16v-4"/>
          <path d="M12 8h.01"/>
        </svg>
        {$t('fileStatus.autoRefresh')}
      </div>
    </div>
  </div>

  {#if error}
    <div class="error-message">
      {error}
    </div>
  {/if}

  {#if loading && !fileStatus}
    <div class="loading">{$t('fileStatus.loading')}</div>
  {:else if fileStatus}
    <div class="status-overview">
      <div class="status-cards">
        <div class="status-card">
          <div class="status-number">{fileStatus.status_counts.total}</div>
          <div class="status-label">{$t('fileStatus.totalFiles')}</div>
        </div>

        <div class="status-card">
          <div class="status-number">{fileStatus.status_counts.completed}</div>
          <div class="status-label">{$t('common.completed')}</div>
        </div>

        <div class="status-card">
          <div class="status-number">{fileStatus.status_counts.processing}</div>
          <div class="status-label">{$t('common.processing')}</div>
        </div>

        <div class="status-card">
          <div class="status-number">{fileStatus.status_counts.pending}</div>
          <div class="status-label">{$t('common.pending')}</div>
        </div>

        <div class="status-card error">
          <div class="status-number">{fileStatus.status_counts.error}</div>
          <div class="status-label">{$t('fileStatus.errors')}</div>
        </div>
      </div>

      {#if fileStatus.has_problems}
        <div class="problems-section">
          <div class="problems-header">
            <h3>{$t('fileStatus.filesNeedAttention')}</h3>
            <button
              class="recovery-btn"
              on:click={requestRecovery}
              disabled={loading}
            >
              {$t('fileStatus.requestRecoveryAll')}
            </button>
          </div>

          <div class="problem-files">
            {#each fileStatus.problem_files.files as file}
              <div class="problem-file">
                <div class="file-info">
                  <div class="filename">{file.filename}</div>
                  <div class="file-meta">
                    <span class="status-badge {file.status_badge_class || 'status-unknown'}">
                      {translateStatus(file.display_status || file.status)}
                    </span>
                    <span class="file-age">{file.formatted_file_age || $t('common.unknown')}</span>
                  </div>
                </div>

                <div class="file-actions">
                  <button
                    class="info-button"
                    on:click={() => fetchDetailedStatus(file.uuid)}
                    title={$t('fileStatus.viewDetailsTooltip')}
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <circle cx="12" cy="12" r="10"></circle>
                      <line x1="12" y1="16" x2="12" y2="12"></line>
                      <line x1="12" y1="8" x2="12.01" y2="8"></line>
                    </svg>
                  </button>

                  <button
                    class="details-btn"
                    on:click={() => fetchDetailedStatus(file.uuid)}
                  >
                    {$t('fileStatus.details')}
                  </button>

                  {#if file.can_retry}
                    <button
                      class="retry-btn"
                      on:click={() => retryFile(file.uuid)}
                      disabled={retryingFiles.has(file.uuid)}
                    >
                      {retryingFiles.has(file.uuid) ? $t('fileStatus.retrying') : $t('fileStatus.retry')}
                    </button>
                  {/if}
                </div>
              </div>
            {/each}
          </div>
        </div>
      {:else}
        <div class="no-problems">
          <p>{$t('fileStatus.allFilesNormal')}</p>
        </div>
      {/if}

      {#if fileStatus.recent_files.count > 0}
        <div class="recent-files">
          <h3>{$t('fileStatus.recentFiles')}</h3>
          <div class="recent-files-grid">
            {#each fileStatus.recent_files.files as file}
              <div class="recent-file-card">
                <div class="filename">{file.filename}</div>
                <div class="file-status-row">
                  <div class="status-info">
                    <span class="status-badge {file.status_badge_class || 'status-unknown'}">
                      {translateStatus(file.display_status || file.status)}
                    </span>
                    <span class="file-age">{file.formatted_file_age || $t('common.unknown')}</span>
                  </div>
                  <button
                    class="info-button small"
                    on:click={() => fetchDetailedStatus(file.uuid)}
                    title={$t('fileStatus.viewDetailsTooltip')}
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <circle cx="12" cy="12" r="10"></circle>
                      <line x1="12" y1="16" x2="12" y2="12"></line>
                      <line x1="12" y1="8" x2="12.01" y2="8"></line>
                    </svg>
                  </button>
                </div>
              </div>
            {/each}
          </div>
        </div>
      {/if}
    </div>
  {/if}

  <!-- Tasks Section -->
  {#if showTasksSection}
    <div class="tasks-section">
      <div class="tasks-header">
        <h3>{$t('fileStatus.allTasks')}</h3>
      </div>

      <div class="compact-filters">
        <select bind:value={taskFilter} class="compact-filter-select">
          <option value="all">{$t('fileStatus.allStatuses')}</option>
          <option value="pending">{$t('common.pending')}</option>
          <option value="in_progress">{$t('fileStatus.inProgress')}</option>
          <option value="completed">{$t('common.completed')}</option>
          <option value="failed">{$t('fileStatus.failed')}</option>
        </select>

        <select bind:value={taskTypeFilter} class="compact-filter-select">
          <option value="all">{$t('fileStatus.allTypes')}</option>
          <option value="transcription">{$t('fileStatus.transcription')}</option>
          <option value="summarization">{$t('fileStatus.summarization')}</option>
        </select>

        <select bind:value={taskAgeFilter} class="compact-filter-select">
          <option value="all">{$t('fileStatus.allAges')}</option>
          <option value="today">{$t('fileStatus.last24h')}</option>
          <option value="week">{$t('fileStatus.lastWeek')}</option>
          <option value="month">{$t('fileStatus.lastMonth')}</option>
          <option value="older">{$t('fileStatus.older')}</option>
        </select>

        <input
          type="date"
          bind:value={taskDateFrom}
          class="compact-date-input"
          placeholder={$t('fileStatus.fromDate')}
          title={$t('fileStatus.fromDateTooltip')}
        />

        <input
          type="date"
          bind:value={taskDateTo}
          class="compact-date-input"
          placeholder={$t('fileStatus.toDate')}
          title={$t('fileStatus.toDateTooltip')}
        />

        {#if taskFilter !== 'all' || taskTypeFilter !== 'all' || taskAgeFilter !== 'all' || taskDateFrom || taskDateTo}
          <button
            class="compact-clear-btn"
            on:click={() => {
              taskFilter = 'all';
              taskTypeFilter = 'all';
              taskAgeFilter = 'all';
              taskDateFrom = '';
              taskDateTo = '';
            }}
            title={$t('fileStatus.clearFilters')}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        {/if}
      </div>

      {#if tasksLoading && tasks.length === 0}
        <div class="loading">{$t('fileStatus.loadingTasks')}</div>
      {:else if tasksError}
        <div class="error-message">{tasksError}</div>
      {:else if filteredTasks.length === 0}
        <div class="no-tasks">
          <p>{taskFilter !== 'all' || taskTypeFilter !== 'all' ? $t('fileStatus.noTasksFilters') : $t('fileStatus.noTasks')}</p>
        </div>
      {:else}
        <div class="tasks-grid">
          {#each filteredTasks as task (task.id)}
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
                    {$t('fileStatus.transcription')}
                  {:else}
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <line x1="8" y1="6" x2="21" y2="6"></line>
                      <line x1="8" y1="12" x2="21" y2="12"></line>
                      <line x1="8" y1="18" x2="21" y2="18"></line>
                      <line x1="3" y1="6" x2="3.01" y2="6"></line>
                    </svg>
                    {$t('fileStatus.summarization')}
                  {/if}
                </div>
                <div class="task-status {task.status_badge_class || 'status-unknown'}">
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
                    {$t('common.pending')}
                  {:else if task.status === 'in_progress'}
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <circle cx="12" cy="12" r="10"></circle>
                      <polyline points="12 6 12 12 16 14"></polyline>
                    </svg>
                    {$t('fileStatus.inProgress')}
                    <span class="task-progress">{Math.round(task.progress * 100)}%</span>
                  {:else if task.status === 'completed'}
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                      <polyline points="22 4 12 14.01 9 11.01"></polyline>
                    </svg>
                    {$t('common.completed')}
                  {:else if task.status === 'failed'}
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <circle cx="12" cy="12" r="10"></circle>
                      <line x1="15" y1="9" x2="9" y2="15"></line>
                      <line x1="9" y1="9" x2="15" y2="15"></line>
                    </svg>
                    {$t('fileStatus.failed')}
                  {/if}

                  {#if task.media_file}
                    <button
                      class="info-button small"
                      on:click={() => fetchDetailedStatus(task.media_file.uuid)}
                      title={$t('fileStatus.viewDetailsTooltip')}
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
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
                  <div class="task-file">{task.media_file.filename}</div>
                {/if}

                {#if task.error_message}
                  <div class="error-details">
                    <span class="info-label">{$t('fileStatus.error')}</span>
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
  {/if}

  {#if detailedStatus && selectedFile}
    <!-- svelte-ignore a11y-click-events-have-key-events -->
    <!-- svelte-ignore a11y-no-static-element-interactions -->
    <div
      class="detailed-status-modal"
      role="presentation"
      on:click={closeModal}
      on:keydown={(e) => e.key === 'Escape' && closeModal()}
    >
      <!-- svelte-ignore a11y-click-events-have-key-events -->
      <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
      <!-- svelte-ignore a11y-no-static-element-interactions -->
      <!-- svelte-ignore a11y_interactive_supports_focus -->
      <div
        class="modal-content"
        role="dialog"
        aria-modal="true"
        on:click|stopPropagation
        on:keydown|stopPropagation
      >
        <div class="modal-header">
          <h3>{$t('fileStatus.fileDetails')}: {detailedStatus.file.filename}</h3>
          <button class="close-btn" on:click={closeModal}>×</button>
        </div>

        <div class="modal-body">
          <!-- File Details Grid -->
          <div class="file-details">
            <h4>{$t('fileStatus.fileInformation')}</h4>
            <div class="metadata-grid">
              <div class="metadata-item">
                <span class="metadata-label">{$t('fileStatus.fileName')}:</span>
                <span class="metadata-value">{detailedStatus.file.filename}</span>
              </div>
              <div class="metadata-item">
                <span class="metadata-label">{$t('common.status')}:</span>
                <span class="status-badge {detailedStatus.file.status_badge_class || 'status-unknown'}">
                  {translateStatus(detailedStatus.file.display_status || detailedStatus.file.status)}
                </span>
              </div>
              <div class="metadata-item">
                <span class="metadata-label">{$t('fileStatus.fileSize')}:</span>
                <span class="metadata-value">{detailedStatus.file.formatted_file_size || $t('fileStatus.unknown')}</span>
              </div>
              <div class="metadata-item">
                <span class="metadata-label">{$t('common.duration')}:</span>
                <span class="metadata-value">{detailedStatus.file.formatted_duration || $t('fileStatus.unknown')}</span>
              </div>
              <div class="metadata-item">
                <span class="metadata-label">{$t('fileStatus.language')}:</span>
                <span class="metadata-value">{detailedStatus.file.language || $t('fileStatus.autoDetected')}</span>
              </div>
              <div class="metadata-item">
                <span class="metadata-label">{$t('fileStatus.uploadTime')}:</span>
                <span class="metadata-value">{formatDate(detailedStatus.file.upload_time)}</span>
              </div>
              {#if detailedStatus.file.completed_at}
                <div class="metadata-item">
                  <span class="metadata-label">{$t('fileStatus.completedAt')}:</span>
                  <span class="metadata-value">{formatDate(detailedStatus.file.completed_at)}</span>
                </div>
              {/if}
              <div class="metadata-item">
                <span class="metadata-label">{$t('fileStatus.fileAge')}:</span>
                <span class="metadata-value">{detailedStatus.file.formatted_file_age || $t('fileStatus.unknown')}</span>
              </div>
            </div>

            {#if detailedStatus.is_stuck}
              <div class="warning">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display: inline; margin-right: 4px;">
                  <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/>
                  <path d="M12 9v4"/>
                  <path d="m12 17 .01 0"/>
                </svg>
                {$t('fileStatus.fileStuck')}
              </div>
            {/if}

            {#if detailedStatus.can_retry}
              <div class="retry-section">
                <button
                  class="retry-btn large"
                  on:click={() => retryFile(selectedFile)}
                  disabled={retryingFiles.has(selectedFile)}
                >
                  {retryingFiles.has(selectedFile) ? $t('fileStatus.retrying') : $t('fileStatus.retryProcessing')}
                </button>
              </div>
            {/if}
          </div>

          {#if detailedStatus.task_details.length > 0}
            <div class="task-details">
              <h4>{$t('fileStatus.taskDetailsTitle')}</h4>
              <div class="task-metadata-grid">
                {#each detailedStatus.task_details as task}
                  <div class="task-metadata-card">
                    <div class="task-card-header">
                      <span class="task-type-label">{task.task_type}</span>
                      <span class="status-badge {task.status_badge_class || 'status-unknown'}">{translateStatus(task.status)}</span>
                    </div>
                    <div class="task-metadata-items">
                      <div class="metadata-item">
                        <span class="metadata-label">{$t('fileStatus.taskCreated')}</span>
                        <span class="metadata-value">{formatDate(task.created_at)}</span>
                      </div>
                      {#if task.updated_at}
                        <div class="metadata-item">
                          <span class="metadata-label">{$t('fileStatus.lastUpdated')}</span>
                          <span class="metadata-value">{formatDate(task.updated_at)}</span>
                        </div>
                      {/if}
                      {#if task.completed_at}
                        <div class="metadata-item">
                          <span class="metadata-label">{$t('fileStatus.taskCompleted')}</span>
                          <span class="metadata-value">{formatDate(task.completed_at)}</span>
                        </div>
                        <div class="metadata-item">
                          <span class="metadata-label">{$t('fileStatus.processingTime')}</span>
                          <span class="metadata-value">{task.formatted_processing_time || $t('common.unknown')}</span>
                        </div>
                      {/if}
                      {#if task.progress !== undefined && task.status === 'in_progress'}
                        <div class="metadata-item">
                          <span class="metadata-label">{$t('fileStatus.progress')}</span>
                          <span class="metadata-value">{Math.round(task.progress * 100)}%</span>
                        </div>
                      {/if}
                    </div>
                    {#if task.error_message}
                      <div class="task-error-details">
                        <span class="metadata-label">{$t('fileStatus.errorLabel')}</span>
                        <div class="task-error">{task.error_message}</div>
                      </div>
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

  .recovery-btn, .flower-btn, .tasks-toggle-btn {
    padding: 0.6rem 1.2rem;
    background: #3b82f6;
    color: white;
    border: none;
    border-radius: 10px;
    cursor: pointer;
    transition: all 0.2s ease;
    font-weight: 500;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.95rem;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }

  .flower-btn {
    background: var(--surface-color);
    color: var(--text-color);
    border: 1px solid var(--border-color);
  }

  .recovery-btn:hover, .tasks-toggle-btn:hover {
    background: #2563eb;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }

  .recovery-btn:active, .tasks-toggle-btn:active {
    transform: translateY(0);
  }

  .flower-btn:hover {
    background: var(--button-hover);
    border-color: var(--border-hover);
  }

  .recovery-btn:disabled, .tasks-toggle-btn:disabled {
    background: var(--text-light);
    cursor: not-allowed;
    transform: none;
  }

  .spinner-mini {
    width: 16px;
    height: 16px;
    border: 2px solid transparent;
    border-top: 2px solid currentColor;
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }

  .auto-refresh-info {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: var(--text-secondary);
    font-size: 0.875rem;
    font-weight: 500;
    padding: 0.5rem 0.75rem;
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 6px;
  }

  .auto-refresh-info svg {
    opacity: 0.7;
  }

  .status-cards {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 0.75rem;
    margin: 0 auto 1.5rem auto;
    max-width: 700px;
  }

  .status-card {
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    padding: 1rem;
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
    font-size: 1.5rem;
    font-weight: bold;
    color: var(--text-color);
    margin-bottom: 0.25rem;
  }

  .status-label {
    color: var(--text-light);
    font-size: 0.8rem;
    font-weight: 500;
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
    align-items: center;
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

  .status-unknown {
    background: rgba(156, 163, 175, 0.1);
    color: #6b7280;
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

  .recent-files-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
    gap: 0.75rem;
  }

  .recent-file-card {
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    padding: 0.75rem;
    transition: all 0.2s ease;
  }

  .recent-file-card:hover {
    transform: translateY(-1px);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    border-color: var(--border-hover);
  }

  .recent-file-card .filename {
    margin-bottom: 0.5rem;
    font-weight: 500;
    font-size: 0.9rem;
    color: var(--text-color);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .file-status-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.5rem;
  }

  .status-info {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    flex: 1;
  }

  .info-button {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--text-secondary-color);
    padding: 6px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
    flex-shrink: 0;
  }

  .info-button:hover {
    background-color: rgba(0, 0, 0, 0.05);
    color: var(--primary-color);
    transform: scale(1.1);
  }

  :global(.dark) .info-button:hover {
    background-color: rgba(255, 255, 255, 0.1);
  }

  .info-button.small {
    padding: 4px;
  }

  /* Tasks Section Styles */
  .tasks-section {
    margin-top: 2rem;
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 1.5rem;
  }

  .tasks-header {
    margin-bottom: 1rem;
  }

  .tasks-header h3 {
    margin: 0;
    color: var(--text-color);
  }

  .compact-filters {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    flex-wrap: wrap;
    padding: 0.75rem;
    background: var(--background-color);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    margin-bottom: 1.5rem;
    width: fit-content;
  }

  .compact-filter-select {
    padding: 0.35rem 0.5rem;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    background: var(--surface-color);
    color: var(--text-color);
    font-size: 0.8rem;
    cursor: pointer;
    width: auto;
    min-width: 0;
  }

  .compact-filter-select:focus {
    outline: 2px solid var(--primary-color);
    outline-offset: 2px;
  }

  .compact-date-input {
    padding: 0.35rem 0.5rem;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    background: var(--surface-color);
    color: var(--text-color);
    font-size: 0.8rem;
    font-family: inherit;
    width: 115px;
  }

  .compact-date-input:focus {
    outline: 2px solid var(--primary-color);
    outline-offset: 2px;
  }

  .compact-clear-btn {
    padding: 0.35rem;
    background: var(--error-color);
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
  }

  .compact-clear-btn:hover {
    background: var(--error-hover);
    transform: scale(1.1);
  }


  .tasks-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
    gap: 1rem;
  }

  .task-card {
    background: var(--background-color);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    padding: 1rem;
    transition: all 0.2s ease;
  }

  .task-card:hover {
    transform: translateY(-1px);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    border-color: var(--border-hover);
  }

  .task-card .task-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border-color);
  }

  .task-card .task-type {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-weight: 600;
    color: var(--text-color);
  }

  .task-card .task-status {
    padding: 0.25rem 0.75rem;
    border-radius: 100px;
    font-size: 0.8rem;
    font-weight: 500;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .task-file {
    font-weight: 500;
    color: var(--text-color);
    margin-bottom: 0.5rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .task-progress {
    font-weight: 600;
    margin-left: 0.5rem;
  }

  .no-tasks {
    text-align: center;
    padding: 2rem;
    color: var(--text-secondary-color);
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

  .file-details h4 {
    margin: 0 0 1rem 0;
    color: var(--text-color);
    font-weight: 600;
  }

  .metadata-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 0.75rem;
    margin-bottom: 1.5rem;
  }

  .metadata-item {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .metadata-label {
    font-size: 0.8rem;
    font-weight: 600;
    color: var(--text-secondary-color);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .metadata-value {
    font-size: 0.9rem;
    font-weight: 500;
    color: var(--text-color);
    word-break: break-word;
  }

  .task-metadata-grid {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .task-metadata-card {
    background: var(--background-color);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    padding: 1rem;
  }

  .task-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border-color);
  }

  .task-type-label {
    font-weight: 600;
    color: var(--text-color);
    text-transform: capitalize;
  }

  .task-metadata-items {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 0.75rem;
  }

  .task-error-details {
    margin-top: 1rem;
    padding: 0.75rem;
    background: rgba(var(--error-color-rgb, 239, 68, 68), 0.05);
    border-radius: 4px;
    border: 1px solid rgba(var(--error-color-rgb, 239, 68, 68), 0.2);
  }

  .task-error-details .metadata-label {
    color: var(--error-color);
  }

  .task-error-details .task-error {
    margin-top: 0.5rem;
    font-family: monospace;
    white-space: pre-wrap;
    font-size: 0.85rem;
    color: var(--error-color);
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
      flex-wrap: wrap;
      gap: 0.5rem;
    }

    .compact-filters {
      padding: 0.6rem;
      gap: 0.4rem;
      width: 100%;
    }

    .compact-filter-select {
      font-size: 0.75rem;
      padding: 0.3rem 0.4rem;
    }

    .compact-date-input {
      width: 100px;
      font-size: 0.75rem;
      padding: 0.3rem 0.4rem;
    }

    .compact-clear-btn {
      width: 24px;
      height: 24px;
      padding: 0.3rem;
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
      grid-template-columns: repeat(5, 1fr);
      gap: 0.5rem;
    }

    .status-card {
      padding: 0.75rem;
    }

    .status-number {
      font-size: 1.25rem;
    }

    .status-label {
      font-size: 0.7rem;
    }
  }
</style>
