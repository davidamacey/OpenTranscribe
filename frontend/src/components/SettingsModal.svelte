<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { user as userStore, authStore, fetchUserInfo } from '$stores/auth';
  import { settingsModalStore, type SettingsSection } from '$stores/settingsModalStore';
  import axiosInstance from '$lib/axios';
  import { UserSettingsApi, RecordingSettingsHelper, type RecordingSettings } from '$lib/api/userSettings';

  // Import settings components
  import LLMSettings from '$components/settings/LLMSettings.svelte';
  import PromptSettings from '$components/settings/PromptSettings.svelte';
  import AudioExtractionSettings from '$components/settings/AudioExtractionSettings.svelte';
  import UserManagementTable from '$components/UserManagementTable.svelte';
  import ConfirmationModal from '$components/ConfirmationModal.svelte';

  // Modal state
  let modalElement: HTMLElement;
  let showCloseConfirmation = false;

  // Settings state
  $: isOpen = $settingsModalStore.isOpen;
  $: activeSection = $settingsModalStore.activeSection;
  $: isAdmin = $userStore?.role === 'admin';

  // User Profile section
  let fullName = '';
  let email = '';
  let profileChanged = false;
  let profileLoading = false;
  let profileSuccess = '';
  let profileError = '';

  // Password section
  let currentPassword = '';
  let newPassword = '';
  let confirmPassword = '';
  let passwordChanged = false;
  let passwordLoading = false;
  let passwordSuccess = '';
  let passwordError = '';
  let showCurrentPassword = false;
  let showNewPassword = false;
  let showConfirmPassword = false;

  // Recording settings section
  let maxRecordingDuration = 120;
  let recordingQuality: 'standard' | 'high' | 'maximum' = 'high';
  let autoStopEnabled = true;
  let recordingSettingsChanged = false;
  let recordingSettingsLoading = false;
  let recordingSettingsSuccess = '';
  let recordingSettingsError = '';

  // Admin Users section
  let users: any[] = [];
  let usersLoading = false;
  let usersError = '';

  // Admin Stats section
  let stats: any = {
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
      cpu: { total_percent: '0%', per_cpu: [], logical_cores: 0, physical_cores: 0 },
      memory: { total: '0 B', available: '0 B', used: '0 B', percent: '0%' },
      disk: { total: '0 B', used: '0 B', free: '0 B', percent: '0%' },
      gpu: { available: false, name: 'N/A', memory_total: 'N/A', memory_used: 'N/A', memory_free: 'N/A', memory_percent: 'N/A' },
      uptime: 'Unknown',
      platform: 'Unknown',
      python_version: 'Unknown'
    }
  };
  let statsLoading = false;
  let statsError = '';

  // Admin Task Health section
  let taskHealthData: any = null;
  let taskHealthLoading = false;
  let taskHealthError = '';
  let showConfirmModal = false;
  let confirmModalTitle = '';
  let confirmModalMessage = '';
  let confirmCallback: (() => void) | null = null;

  // Define sidebar sections
  $: sidebarSections = [
    ...(isAdmin ? [
      {
        title: 'Administration',
        items: [
          { id: 'admin-users' as SettingsSection, label: 'Users', icon: 'users' },
          { id: 'admin-statistics' as SettingsSection, label: 'Statistics', icon: 'chart' },
          { id: 'admin-task-health' as SettingsSection, label: 'Task Health', icon: 'health' },
          { id: 'admin-settings' as SettingsSection, label: 'System Settings', icon: 'settings' }
        ]
      }
    ] : []),
    {
      title: 'User Settings',
      items: [
        { id: 'profile' as SettingsSection, label: 'Profile', icon: 'user' },
        { id: 'password' as SettingsSection, label: 'Password', icon: 'lock' },
        { id: 'recording' as SettingsSection, label: 'Recording', icon: 'mic' },
        { id: 'audio-extraction' as SettingsSection, label: 'Audio Extraction', icon: 'file-audio' },
        { id: 'ai-prompts' as SettingsSection, label: 'AI Summarization Prompts', icon: 'message' },
        { id: 'llm-provider' as SettingsSection, label: 'LLM Provider Configuration', icon: 'brain' }
      ]
    }
  ];

  // Reactive profile change detection
  $: if ($authStore.user) {
    profileChanged = $authStore.user.full_name !== fullName;
    settingsModalStore.setDirty('profile', profileChanged);
  }

  // Reactive password change detection
  $: {
    passwordChanged = !!(currentPassword || newPassword || confirmPassword);
    settingsModalStore.setDirty('password', passwordChanged);
  }

  // Reactive recording settings change detection
  $: {
    settingsModalStore.setDirty('recording', recordingSettingsChanged);
  }

  // Reactive user data update when authStore changes or modal opens
  $: if ($authStore.user && isOpen) {
    fullName = $authStore.user.full_name || '';
    email = $authStore.user.email || '';
  }

  // Load data when modal opens
  $: if (isOpen && !profileLoading && !recordingSettingsLoading) {
    // Only reload if we haven't loaded yet or data is stale
    if (!fullName && $authStore.user) {
      fullName = $authStore.user.full_name || '';
      email = $authStore.user.email || '';
    }
  }

  onMount(() => {
    // Initialize user data
    if ($authStore.user) {
      fullName = $authStore.user.full_name || '';
      email = $authStore.user.email || '';
    }

    // Load recording settings
    loadRecordingSettings();

    // Load admin data if admin
    if (isAdmin) {
      if (activeSection === 'admin-users') {
        loadAdminUsers();
      } else if (activeSection === 'admin-statistics') {
        loadAdminStats();
      } else if (activeSection === 'admin-task-health') {
        loadTaskHealth();
      }
    }

    // Add escape key listener
    document.addEventListener('keydown', handleKeyDown);
  });

  onDestroy(() => {
    document.removeEventListener('keydown', handleKeyDown);
    // Re-enable body scroll when component is destroyed
    document.body.style.overflow = '';
  });

  // Track previous open state to detect when modal opens
  let previousOpenState = false;

  // Prevent body scroll when modal is open and load initial data
  $: {
    if (isOpen && !previousOpenState) {
      // Modal just opened
      document.body.style.overflow = 'hidden';

      // Load data for the active section when modal opens
      if (activeSection === 'admin-users' && isAdmin) {
        loadAdminUsers();
      } else if (activeSection === 'admin-statistics' && isAdmin) {
        loadAdminStats();
      } else if (activeSection === 'admin-task-health' && isAdmin) {
        loadTaskHealth();
      }

      previousOpenState = true;
    } else if (!isOpen && previousOpenState) {
      // Modal just closed
      document.body.style.overflow = '';
      previousOpenState = false;
    }
  }

  function handleKeyDown(event: KeyboardEvent) {
    if (event.key === 'Escape' && isOpen) {
      attemptClose();
    }
  }

  function handleBackdropClick(event: MouseEvent) {
    if (event.target === event.currentTarget) {
      attemptClose();
    }
  }

  function attemptClose() {
    const hasUnsavedChanges = settingsModalStore.hasAnyDirty($settingsModalStore);
    if (hasUnsavedChanges) {
      showCloseConfirmation = true;
    } else {
      closeModal();
    }
  }

  function closeModal() {
    settingsModalStore.close();
    showCloseConfirmation = false;
    resetAllForms();
  }

  function forceClose() {
    showCloseConfirmation = false;
    closeModal();
  }

  function resetAllForms() {
    // Reset profile
    if ($authStore.user) {
      fullName = $authStore.user.full_name || '';
      email = $authStore.user.email || '';
    }
    profileError = '';
    profileSuccess = '';

    // Reset password
    currentPassword = '';
    newPassword = '';
    confirmPassword = '';
    showCurrentPassword = false;
    showNewPassword = false;
    showConfirmPassword = false;
    passwordError = '';
    passwordSuccess = '';

    // Reset recording settings
    loadRecordingSettings();
    recordingSettingsError = '';
    recordingSettingsSuccess = '';

    // Clear all dirty states
    settingsModalStore.clearAllDirty();
  }

  function switchSection(sectionId: SettingsSection) {
    // Clear messages when switching
    profileError = '';
    profileSuccess = '';
    passwordError = '';
    passwordSuccess = '';
    recordingSettingsError = '';
    recordingSettingsSuccess = '';
    usersError = '';
    statsError = '';
    taskHealthError = '';

    settingsModalStore.setActiveSection(sectionId);

    // Load data for specific sections
    if (sectionId === 'admin-users') {
      loadAdminUsers();
    } else if (sectionId === 'admin-statistics') {
      loadAdminStats();
    } else if (sectionId === 'admin-task-health') {
      loadTaskHealth();
    }
  }

  // Profile functions
  async function updateProfile() {
    profileLoading = true;
    profileError = '';
    profileSuccess = '';

    try {
      const response = await axiosInstance.put('/users/me', {
        full_name: fullName
      });

      authStore.setUser(response.data);
      localStorage.setItem('user', JSON.stringify(response.data));

      profileSuccess = 'Profile updated successfully';
      profileChanged = false;
      settingsModalStore.clearDirty('profile');

      await fetchUserInfo();
    } catch (err: any) {
      console.error('Error updating profile:', err);
      profileError = err.response?.data?.detail || 'Failed to update profile';
    } finally {
      profileLoading = false;
    }
  }

  // Password functions
  async function updatePassword() {
    passwordLoading = true;
    passwordError = '';
    passwordSuccess = '';

    // Validation
    if (!currentPassword || !newPassword || !confirmPassword) {
      passwordError = 'Please fill in all password fields';
      passwordLoading = false;
      return;
    }

    if (newPassword !== confirmPassword) {
      passwordError = 'New passwords do not match';
      passwordLoading = false;
      return;
    }

    if (newPassword.length < 8) {
      passwordError = 'Password must be at least 8 characters long';
      passwordLoading = false;
      return;
    }

    try {
      await axiosInstance.put('/users/me', {
        password: newPassword,
        current_password: currentPassword
      });

      passwordSuccess = 'Password updated successfully';

      // Clear password fields
      currentPassword = '';
      newPassword = '';
      confirmPassword = '';
      showCurrentPassword = false;
      showNewPassword = false;
      showConfirmPassword = false;
      passwordChanged = false;
      settingsModalStore.clearDirty('password');
    } catch (err: any) {
      console.error('Error updating password:', err);
      passwordError = err.response?.data?.detail || 'Failed to update password';
    } finally {
      passwordLoading = false;
    }
  }

  // Recording settings functions
  async function loadRecordingSettings() {
    recordingSettingsLoading = true;
    try {
      const settings = await UserSettingsApi.getRecordingSettings();
      maxRecordingDuration = settings.max_recording_duration;
      recordingQuality = settings.recording_quality;
      autoStopEnabled = settings.auto_stop_enabled;
      recordingSettingsChanged = false;
    } catch (err: any) {
      console.error('Error loading recording settings:', err);
      recordingSettingsError = err.response?.data?.detail || 'Failed to load recording settings';
    } finally {
      recordingSettingsLoading = false;
    }
  }

  function handleRecordingSettingsChange() {
    recordingSettingsChanged = true;
    settingsModalStore.setDirty('recording', true);
  }

  async function saveRecordingSettings() {
    recordingSettingsLoading = true;
    recordingSettingsError = '';
    recordingSettingsSuccess = '';

    // Validate settings
    const settingsToValidate: RecordingSettings = {
      max_recording_duration: maxRecordingDuration,
      recording_quality: recordingQuality,
      auto_stop_enabled: autoStopEnabled
    };

    const validationErrors = RecordingSettingsHelper.validateSettings(settingsToValidate);
    if (validationErrors.length > 0) {
      recordingSettingsError = validationErrors[0];
      recordingSettingsLoading = false;
      return;
    }

    try {
      await UserSettingsApi.updateRecordingSettings(settingsToValidate);
      recordingSettingsSuccess = 'Recording settings saved successfully';
      recordingSettingsChanged = false;
      settingsModalStore.clearDirty('recording');
    } catch (err: any) {
      console.error('Error saving recording settings:', err);
      recordingSettingsError = err.response?.data?.detail || 'Failed to save recording settings';
    } finally {
      recordingSettingsLoading = false;
    }
  }

  async function resetRecordingSettings() {
    recordingSettingsLoading = true;
    recordingSettingsError = '';
    recordingSettingsSuccess = '';

    try {
      await UserSettingsApi.resetRecordingSettings();
      await loadRecordingSettings();
      recordingSettingsSuccess = 'Recording settings reset to defaults';
      recordingSettingsChanged = false;
      settingsModalStore.clearDirty('recording');
    } catch (err: any) {
      console.error('Error resetting recording settings:', err);
      recordingSettingsError = err.response?.data?.detail || 'Failed to reset recording settings';
    } finally {
      recordingSettingsLoading = false;
    }
  }

  // Admin functions
  async function loadAdminUsers() {
    usersLoading = true;
    usersError = '';

    try {
      const response = await axiosInstance.get('/admin/users');
      users = response.data;
    } catch (err: any) {
      console.error('Error loading admin users:', err);
      usersError = err.response?.data?.detail || 'Failed to load users';
    } finally {
      usersLoading = false;
    }
  }

  async function refreshAdminUsers() {
    await loadAdminUsers();
  }

  async function recoverUserFiles(userId: string) {
    try {
      await axiosInstance.post(`/tasks/system/recover-user-files/${userId}`);
      // Optionally show success message
    } catch (err: any) {
      console.error('Error recovering user files:', err);
      usersError = err.response?.data?.detail || 'Failed to recover user files';
    }
  }

  async function loadAdminStats() {
    statsLoading = true;
    statsError = '';

    try {
      const response = await axiosInstance.get('/admin/stats');
      stats = response.data;
    } catch (err: any) {
      console.error('Error loading admin stats:', err);
      statsError = err.response?.data?.detail || 'Failed to load statistics';
    } finally {
      statsLoading = false;
    }
  }

  async function refreshAdminStats() {
    await loadAdminStats();
  }

  async function loadTaskHealth() {
    taskHealthLoading = true;
    taskHealthError = '';

    try {
      const response = await axiosInstance.get('/tasks/system/health');
      taskHealthData = response.data;
    } catch (err: any) {
      console.error('Error loading task health:', err);
      taskHealthError = err.response?.data?.detail || 'Failed to load task health data';
    } finally {
      taskHealthLoading = false;
    }
  }

  async function refreshTaskHealth() {
    await loadTaskHealth();
  }

  function showConfirmation(title: string, message: string, callback: () => void) {
    confirmModalTitle = title;
    confirmModalMessage = message;
    confirmCallback = callback;
    showConfirmModal = true;
  }

  function handleConfirmModalConfirm() {
    showConfirmModal = false;
    if (confirmCallback) {
      confirmCallback();
      confirmCallback = null;
    }
  }

  function handleConfirmModalCancel() {
    showConfirmModal = false;
    confirmCallback = null;
  }

  async function recoverStuckTasks() {
    showConfirmation(
      'Recover Stuck Tasks',
      'This will attempt to recover all stuck tasks. Continue?',
      async () => {
        try {
          await axiosInstance.post('/tasks/recover-stuck-tasks');
          await refreshTaskHealth();
        } catch (err: any) {
          console.error('Error recovering stuck tasks:', err);
          taskHealthError = err.response?.data?.detail || 'Failed to recover stuck tasks';
        }
      }
    );
  }

  async function fixInconsistentFiles() {
    showConfirmation(
      'Fix Inconsistent Files',
      'This will attempt to fix all files with inconsistent state. Continue?',
      async () => {
        try {
          await axiosInstance.post('/tasks/fix-inconsistent-files');
          await refreshTaskHealth();
        } catch (err: any) {
          console.error('Error fixing inconsistent files:', err);
          taskHealthError = err.response?.data?.detail || 'Failed to fix inconsistent files';
        }
      }
    );
  }

  async function startupRecovery() {
    showConfirmation(
      'Startup Recovery',
      'This will run the startup recovery process. Continue?',
      async () => {
        try {
          await axiosInstance.post('/tasks/system/startup-recovery');
          await refreshTaskHealth();
        } catch (err: any) {
          console.error('Error running startup recovery:', err);
          taskHealthError = err.response?.data?.detail || 'Failed to run startup recovery';
        }
      }
    );
  }

  async function recoverAllUserFiles() {
    showConfirmation(
      'Recover All User Files',
      'This will recover files for all users. This may take a while. Continue?',
      async () => {
        try {
          await axiosInstance.post('/tasks/system/recover-all-user-files');
          await refreshTaskHealth();
        } catch (err: any) {
          console.error('Error recovering all user files:', err);
          taskHealthError = err.response?.data?.detail || 'Failed to recover all user files';
        }
      }
    );
  }

  async function retryTask(taskId: number) {
    try {
      await axiosInstance.post(`/tasks/system/recover-task/${taskId}`);
      await refreshTaskHealth();
    } catch (err: any) {
      console.error('Error retrying task:', err);
      taskHealthError = err.response?.data?.detail || 'Failed to retry task';
    }
  }

  async function retryFile(fileId: number) {
    try {
      await axiosInstance.post(`/tasks/retry-file/${fileId}`);
      await refreshTaskHealth();
    } catch (err: any) {
      console.error('Error retrying file:', err);
      taskHealthError = err.response?.data?.detail || 'Failed to retry file';
    }
  }

  // AI settings change handlers
  function onAISettingsChange() {
    // Clear any existing messages
    profileSuccess = '';
    profileError = '';
  }

  // Helper function for formatting time
  function formatTime(seconds: number): string {
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
</script>

{#if isOpen}
  <div
    class="settings-modal-backdrop"
    on:click={handleBackdropClick}
    role="presentation"
  >
    <div class="settings-modal" bind:this={modalElement} role="dialog" aria-modal="true" aria-labelledby="settings-modal-title">
      <!-- Close button -->
      <button class="modal-close-button" on:click={attemptClose} aria-label="Close settings" title="Close settings">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="18" y1="6" x2="6" y2="18"></line>
          <line x1="6" y1="6" x2="18" y2="18"></line>
        </svg>
      </button>

      <div class="settings-modal-container">
        <!-- Sidebar -->
        <aside class="settings-sidebar">
          <h2 id="settings-modal-title" class="settings-title">Settings</h2>

          {#each sidebarSections as section}
            <div class="sidebar-section">
              <h3 class="section-heading">{section.title}</h3>
              <nav class="section-nav">
                {#each section.items as item}
                  <button
                    class="nav-item"
                    class:active={activeSection === item.id}
                    class:dirty={$settingsModalStore.dirtyState[item.id]}
                    on:click={() => switchSection(item.id)}
                  >
                    <span class="nav-item-label">{item.label}</span>
                    {#if $settingsModalStore.dirtyState[item.id]}
                      <span class="dirty-indicator" title="Unsaved changes">●</span>
                    {/if}
                  </button>
                {/each}
              </nav>
            </div>
          {/each}
        </aside>

        <!-- Content Area -->
        <main class="settings-content">
          <!-- Profile Section -->
          {#if activeSection === 'profile'}
            <div class="content-section">
              <h3 class="section-title">Profile Settings</h3>
              <p class="section-description">Update your personal information</p>

              {#if profileSuccess}
                <div class="alert alert-success">{profileSuccess}</div>
              {/if}

              {#if profileError}
                <div class="alert alert-error">{profileError}</div>
              {/if}

              <form on:submit|preventDefault={updateProfile} class="settings-form">
                <div class="form-group">
                  <label for="email">Email</label>
                  <input
                    type="email"
                    id="email"
                    class="form-control"
                    value={email}
                    disabled
                  />
                  <small class="form-text">Email cannot be changed</small>
                </div>

                <div class="form-group">
                  <label for="fullName">Full Name</label>
                  <input
                    type="text"
                    id="fullName"
                    class="form-control"
                    bind:value={fullName}
                    required
                  />
                </div>

                <div class="form-actions">
                  <button
                    type="submit"
                    class="btn btn-primary"
                    disabled={!profileChanged || profileLoading}
                  >
                    {profileLoading ? 'Saving...' : 'Save Changes'}
                  </button>
                </div>
              </form>
            </div>
          {/if}

          <!-- Password Section -->
          {#if activeSection === 'password'}
            <div class="content-section">
              <h3 class="section-title">Change Password</h3>
              <p class="section-description">Update your account password</p>

              {#if passwordSuccess}
                <div class="alert alert-success">{passwordSuccess}</div>
              {/if}

              {#if passwordError}
                <div class="alert alert-error">{passwordError}</div>
              {/if}

              <form on:submit|preventDefault={updatePassword} class="settings-form">
                <div class="form-group">
                  <div class="password-header">
                    <label for="currentPassword">Current Password</label>
                    <button
                      type="button"
                      class="toggle-password"
                      on:click={() => showCurrentPassword = !showCurrentPassword}
                      tabindex="-1"
                      aria-label={showCurrentPassword ? 'Hide password' : 'Show password'}
                    >
                      {#if showCurrentPassword}
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                          <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/>
                          <circle cx="12" cy="12" r="3"/>
                        </svg>
                      {:else}
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                          <path d="m15 18-.722-3.25"/>
                          <path d="m2 2 20 20"/>
                          <path d="m9 9-.637 3.181"/>
                          <path d="M12.5 5.5c2.13.13 4.16 1.11 5.5 3.5-.274.526-.568 1.016-.891 1.469"/>
                          <path d="M2 12s3-7 10-7c1.284 0 2.499.23 3.62.67"/>
                          <path d="m18.147 8.476.853 3.524"/>
                        </svg>
                      {/if}
                    </button>
                  </div>
                  <input
                    type={showCurrentPassword ? 'text' : 'password'}
                    id="currentPassword"
                    class="form-control"
                    bind:value={currentPassword}
                    required
                  />
                </div>

                <div class="form-group">
                  <div class="password-header">
                    <label for="newPassword">New Password</label>
                    <button
                      type="button"
                      class="toggle-password"
                      on:click={() => showNewPassword = !showNewPassword}
                      tabindex="-1"
                      aria-label={showNewPassword ? 'Hide password' : 'Show password'}
                    >
                      {#if showNewPassword}
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                          <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/>
                          <circle cx="12" cy="12" r="3"/>
                        </svg>
                      {:else}
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                          <path d="m15 18-.722-3.25"/>
                          <path d="m2 2 20 20"/>
                          <path d="m9 9-.637 3.181"/>
                          <path d="M12.5 5.5c2.13.13 4.16 1.11 5.5 3.5-.274.526-.568 1.016-.891 1.469"/>
                          <path d="M2 12s3-7 10-7c1.284 0 2.499.23 3.62.67"/>
                          <path d="m18.147 8.476.853 3.524"/>
                        </svg>
                      {/if}
                    </button>
                  </div>
                  <input
                    type={showNewPassword ? 'text' : 'password'}
                    id="newPassword"
                    class="form-control"
                    bind:value={newPassword}
                    required
                  />
                  <small class="form-text">Minimum 8 characters</small>
                </div>

                <div class="form-group">
                  <div class="password-header">
                    <label for="confirmPassword">Confirm New Password</label>
                    <button
                      type="button"
                      class="toggle-password"
                      on:click={() => showConfirmPassword = !showConfirmPassword}
                      tabindex="-1"
                      aria-label={showConfirmPassword ? 'Hide password' : 'Show password'}
                    >
                      {#if showConfirmPassword}
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                          <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/>
                          <circle cx="12" cy="12" r="3"/>
                        </svg>
                      {:else}
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                          <path d="m15 18-.722-3.25"/>
                          <path d="m2 2 20 20"/>
                          <path d="m9 9-.637 3.181"/>
                          <path d="M12.5 5.5c2.13.13 4.16 1.11 5.5 3.5-.274.526-.568 1.016-.891 1.469"/>
                          <path d="M2 12s3-7 10-7c1.284 0 2.499.23 3.62.67"/>
                          <path d="m18.147 8.476.853 3.524"/>
                        </svg>
                      {/if}
                    </button>
                  </div>
                  <input
                    type={showConfirmPassword ? 'text' : 'password'}
                    id="confirmPassword"
                    class="form-control"
                    bind:value={confirmPassword}
                    required
                  />
                </div>

                <div class="form-actions">
                  <button
                    type="submit"
                    class="btn btn-primary"
                    disabled={!passwordChanged || passwordLoading}
                  >
                    {passwordLoading ? 'Updating...' : 'Update Password'}
                  </button>
                </div>
              </form>
            </div>
          {/if}

          <!-- Recording Settings Section -->
          {#if activeSection === 'recording'}
            <div class="content-section">
              <h3 class="section-title">Recording Settings</h3>
              <p class="section-description">Configure audio recording preferences</p>

              {#if recordingSettingsSuccess}
                <div class="alert alert-success">{recordingSettingsSuccess}</div>
              {/if}

              {#if recordingSettingsError}
                <div class="alert alert-error">{recordingSettingsError}</div>
              {/if}

              <form on:submit|preventDefault={saveRecordingSettings} class="settings-form">
                <div class="form-group">
                  <label for="maxRecordingDuration">Maximum Recording Duration (minutes)</label>
                  <input
                    type="number"
                    id="maxRecordingDuration"
                    class="form-control"
                    bind:value={maxRecordingDuration}
                    on:input={handleRecordingSettingsChange}
                    min="15"
                    max="480"
                    required
                  />
                  <small class="form-text">Range: 15-480 minutes (8 hours)</small>
                </div>

                <div class="form-group">
                  <label for="recordingQuality">Recording Quality</label>
                  <select
                    id="recordingQuality"
                    class="form-control"
                    bind:value={recordingQuality}
                    on:change={handleRecordingSettingsChange}
                  >
                    <option value="standard">Standard (16kHz, 64kbps)</option>
                    <option value="high">High (44.1kHz, 128kbps)</option>
                    <option value="maximum">Maximum (48kHz, 192kbps)</option>
                  </select>
                  <small class="form-text">Higher quality requires more storage</small>
                </div>

                <div class="form-group">
                  <label class="checkbox-label">
                    <input
                      type="checkbox"
                      bind:checked={autoStopEnabled}
                      on:change={handleRecordingSettingsChange}
                    />
                    <span>Auto-stop at maximum duration</span>
                  </label>
                  <small class="form-text">Automatically stop recording when limit is reached</small>
                </div>

                <div class="form-actions">
                  <button
                    type="submit"
                    class="btn btn-primary"
                    disabled={!recordingSettingsChanged || recordingSettingsLoading}
                  >
                    {recordingSettingsLoading ? 'Saving...' : 'Save Settings'}
                  </button>

                  <button
                    type="button"
                    class="btn btn-secondary"
                    on:click={resetRecordingSettings}
                    disabled={recordingSettingsLoading}
                  >
                    Reset to Defaults
                  </button>
                </div>
              </form>
            </div>
          {/if}

          <!-- Audio Extraction Settings Section -->
          {#if activeSection === 'audio-extraction'}
            <div class="content-section">
              <h3 class="section-title">Audio Extraction Settings</h3>
              <p class="section-description">Configure how OpenTranscribe handles large video files. Audio extraction reduces upload size by 90%+ while preserving transcription quality.</p>
              <AudioExtractionSettings />
            </div>
          {/if}

          <!-- AI Prompts Section -->
          {#if activeSection === 'ai-prompts'}
            <div class="content-section">
              <h3 class="section-title">AI Summarization Prompts</h3>
              <p class="section-description">Manage your AI summarization prompts to customize how transcripts are analyzed and summarized.</p>
              <PromptSettings onSettingsChange={onAISettingsChange} />
            </div>
          {/if}

          <!-- LLM Provider Section -->
          {#if activeSection === 'llm-provider'}
            <div class="content-section">
              <h3 class="section-title">LLM Provider Configuration</h3>
              <p class="section-description">Configure your preferred Large Language Model provider for AI summarization and speaker identification.</p>
              <LLMSettings onSettingsChange={onAISettingsChange} />
            </div>
          {/if}

          <!-- Admin Users Section -->
          {#if activeSection === 'admin-users' && isAdmin}
            <div class="content-section">
              <h3 class="section-title">User Management</h3>
              <p class="section-description">Create, edit, and delete user accounts. Manage user roles and permissions including admin privileges.</p>
              <UserManagementTable
                {users}
                loading={usersLoading}
                error={usersError}
                onRefresh={refreshAdminUsers}
                onUserRecovery={recoverUserFiles}
              />
            </div>
          {/if}

          <!-- Admin Statistics Section -->
          {#if activeSection === 'admin-statistics' && isAdmin}
            <div class="content-section">
              <h3 class="section-title">System Statistics</h3>
              <p class="section-description">View system-wide metrics and performance</p>

              {#if statsError}
                <div class="alert alert-error">{statsError}</div>
              {/if}

              <div class="stats-actions">
                <button
                  type="button"
                  class="btn btn-secondary"
                  on:click={refreshAdminStats}
                  disabled={statsLoading}
                >
                  {statsLoading ? 'Loading...' : 'Refresh Statistics'}
                </button>
              </div>

              {#if statsLoading}
                <div class="loading-state">
                  <div class="spinner"></div>
                  <p>Loading statistics...</p>
                </div>
              {:else}
                <div class="stats-grid">
                  <!-- User Stats -->
                  <div class="stat-card">
                    <h4>Users</h4>
                    <div class="stat-value">{stats.users?.total || 0}</div>
                    <div class="stat-detail">New (7d): {stats.users?.new || 0}</div>
                  </div>

                  <!-- Media Stats -->
                  <div class="stat-card">
                    <h4>Media Files</h4>
                    <div class="stat-value">{stats.files?.total || 0}</div>
                    <div class="stat-detail">New: {stats.files?.new || 0}</div>
                    <div class="stat-detail">Segments: {stats.files?.segments || 0}</div>
                  </div>

                  <!-- Task Stats -->
                  <div class="stat-card">
                    <h4>Tasks</h4>
                    <div class="stat-detail">Pending: {stats.tasks?.pending || 0}</div>
                    <div class="stat-detail">Running: {stats.tasks?.running || 0}</div>
                    <div class="stat-detail">Completed: {stats.tasks?.completed || 0}</div>
                    <div class="stat-detail">Failed: {stats.tasks?.failed || 0}</div>
                    <div class="stat-detail">Success Rate: {stats.tasks?.success_rate || 0}%</div>
                  </div>

                  <!-- Performance Stats -->
                  <div class="stat-card">
                    <h4>Performance</h4>
                    <div class="stat-detail">Avg Process Time: {formatTime(stats.tasks?.avg_processing_time || 0)}</div>
                    <div class="stat-detail">Speakers: {stats.speakers?.total || 0}</div>
                  </div>

                  <!-- System Resources -->
                  <div class="stat-card stat-card-with-bar">
                    <div class="stat-card-content">
                      <h4>CPU Usage</h4>
                      <div class="stat-value">{stats.system?.cpu?.total_percent || '0%'}</div>
                    </div>
                    <div class="progress-bar">
                      <div class="progress-fill" style="width: {parseFloat(stats.system?.cpu?.total_percent) || 0}%"></div>
                    </div>
                  </div>

                  <div class="stat-card stat-card-with-bar">
                    <div class="stat-card-content">
                      <h4>Memory Usage</h4>
                      <div class="stat-value">{stats.system?.memory?.percent || '0%'}</div>
                      <div class="stat-detail">
                        <span>Total: {stats.system?.memory?.total || 'Unknown'}</span>
                        <span>Used: {stats.system?.memory?.used || 'Unknown'}</span>
                        <span>Available: {stats.system?.memory?.available || 'Unknown'}</span>
                      </div>
                    </div>
                    <div class="progress-bar">
                      <div class="progress-fill" style="width: {parseFloat(stats.system?.memory?.percent) || 0}%"></div>
                    </div>
                  </div>

                  <div class="stat-card stat-card-with-bar">
                    <div class="stat-card-content">
                      <h4>Disk Usage</h4>
                      <div class="stat-value">{stats.system?.disk?.percent || '0%'}</div>
                      <div class="stat-detail">
                        <span>Total: {stats.system?.disk?.total || 'Unknown'}</span>
                        <span>Used: {stats.system?.disk?.used || 'Unknown'}</span>
                        <span>Free: {stats.system?.disk?.free || 'Unknown'}</span>
                      </div>
                    </div>
                    <div class="progress-bar">
                      <div class="progress-fill" style="width: {parseFloat(stats.system?.disk?.percent) || 0}%"></div>
                    </div>
                  </div>

                  <!-- GPU VRAM -->
                  <div class="stat-card stat-card-with-bar">
                    {#if stats.system?.gpu?.available}
                      <div class="stat-card-content">
                        <h4>GPU VRAM</h4>
                        <div class="stat-value">{stats.system.gpu.memory_percent || '0%'}</div>
                        <div class="stat-detail">
                          <span>GPU: {stats.system.gpu.name || 'Unknown'}</span>
                          <span>Total: {stats.system.gpu.memory_total || 'Unknown'}</span>
                          <span>Used: {stats.system.gpu.memory_used || 'Unknown'}</span>
                          <span>Free: {stats.system.gpu.memory_free || 'Unknown'}</span>
                        </div>
                      </div>
                      <div class="progress-bar">
                        <div class="progress-fill" style="width: {parseFloat(stats.system.gpu.memory_percent) || 0}%"></div>
                      </div>
                    {:else}
                      <div class="stat-card-content">
                        <h4>GPU VRAM</h4>
                        <div class="stat-value">N/A</div>
                        <div class="stat-detail">{stats.system?.gpu?.name || 'No GPU Available'}</div>
                      </div>
                    {/if}
                  </div>
                </div>

                <!-- Recent Tasks Table -->
                {#if stats.tasks?.recent && stats.tasks.recent.length > 0}
                  <div class="recent-tasks">
                    <h4>Recent Tasks</h4>
                    <div class="table-container">
                      <table class="data-table">
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
                        </tbody>
                      </table>
                    </div>
                  </div>
                {:else}
                  <div class="recent-tasks">
                    <h4>Recent Tasks</h4>
                    <p class="empty-state">No recent tasks found</p>
                  </div>
                {/if}
              {/if}
            </div>
          {/if}

          <!-- Admin Task Health Section -->
          {#if activeSection === 'admin-task-health' && isAdmin}
            <div class="content-section">
              <h3 class="section-title">Task Health Monitor</h3>
              <p class="section-description">Monitor and recover stuck tasks and inconsistent files</p>

              {#if taskHealthError}
                <div class="alert alert-error">{taskHealthError}</div>
              {/if}

              <div class="stats-actions">
                <button
                  type="button"
                  class="btn btn-secondary"
                  on:click={refreshTaskHealth}
                  disabled={taskHealthLoading}
                >
                  {taskHealthLoading ? 'Loading...' : 'Refresh Health Data'}
                </button>
              </div>

              {#if taskHealthLoading}
                <div class="loading-state">
                  <div class="spinner"></div>
                  <p>Loading task health data...</p>
                </div>
              {:else if taskHealthData}
                <div class="task-health-grid">
                  <!-- Recovery Actions -->
                  <div class="health-card">
                    <h4>System Recovery Actions</h4>
                    <div class="action-buttons">
                      <button class="btn btn-warning" on:click={recoverStuckTasks}>
                        Recover Stuck Tasks ({taskHealthData.stuck_tasks?.length || 0})
                      </button>
                      <button class="btn btn-warning" on:click={fixInconsistentFiles}>
                        Fix Inconsistent Files ({taskHealthData.inconsistent_files?.length || 0})
                      </button>
                      <button class="btn btn-primary" on:click={startupRecovery}>
                        Startup Recovery
                      </button>
                      <button class="btn btn-primary" on:click={recoverAllUserFiles}>
                        Recover All User Files
                      </button>
                    </div>
                  </div>

                  <!-- Stuck Tasks -->
                  {#if taskHealthData.stuck_tasks && taskHealthData.stuck_tasks.length > 0}
                    <div class="health-card">
                      <h4>Stuck Tasks</h4>
                      <div class="table-container">
                        <table class="data-table">
                          <thead>
                            <tr>
                              <th>ID</th>
                              <th>Type</th>
                              <th>Status</th>
                              <th>Created</th>
                              <th>Actions</th>
                            </tr>
                          </thead>
                          <tbody>
                            {#each taskHealthData.stuck_tasks as task}
                              <tr>
                                <td>{task.id}</td>
                                <td>{task.task_type}</td>
                                <td><span class="status-badge status-{task.status}">{task.status}</span></td>
                                <td>{new Date(task.created_at).toLocaleString()}</td>
                                <td>
                                  <button class="btn-small btn-primary" on:click={() => retryTask(task.id)}>
                                    Retry
                                  </button>
                                </td>
                              </tr>
                            {/each}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  {/if}

                  <!-- Inconsistent Files -->
                  {#if taskHealthData.inconsistent_files && taskHealthData.inconsistent_files.length > 0}
                    <div class="health-card">
                      <h4>Inconsistent Files</h4>
                      <div class="table-container">
                        <table class="data-table">
                          <thead>
                            <tr>
                              <th>ID</th>
                              <th>Filename</th>
                              <th>Status</th>
                              <th>Actions</th>
                            </tr>
                          </thead>
                          <tbody>
                            {#each taskHealthData.inconsistent_files as file}
                              <tr>
                                <td>{file.id}</td>
                                <td>{file.filename}</td>
                                <td><span class="status-badge status-{file.status}">{file.status}</span></td>
                                <td>
                                  <button class="btn-small btn-primary" on:click={() => retryFile(file.id)}>
                                    Retry
                                  </button>
                                </td>
                              </tr>
                            {/each}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  {/if}
                </div>
              {:else}
                <div class="placeholder-message">
                  <p>Click "Refresh Health Data" to load task health information.</p>
                </div>
              {/if}
            </div>
          {/if}

          <!-- Admin System Settings Section -->
          {#if activeSection === 'admin-settings' && isAdmin}
            <div class="content-section">
              <h3 class="section-title">System Settings</h3>
              <p class="section-description">System-wide configuration (Coming Soon)</p>
              <div class="placeholder-message">
                <p>System settings management will be available in a future update.</p>
              </div>
            </div>
          {/if}
        </main>
      </div>
    </div>
  </div>
{/if}

<!-- Close Confirmation Modal -->
<ConfirmationModal
  bind:isOpen={showCloseConfirmation}
  title="Unsaved Changes"
  message="You have unsaved changes. Are you sure you want to close without saving?"
  confirmText="Close Without Saving"
  cancelText="Keep Editing"
  confirmButtonClass="btn-danger"
  cancelButtonClass="btn-secondary"
  on:confirm={forceClose}
  on:cancel={() => showCloseConfirmation = false}
  on:close={() => showCloseConfirmation = false}
/>

<!-- Admin Confirmation Modal -->
<ConfirmationModal
  bind:isOpen={showConfirmModal}
  title={confirmModalTitle}
  message={confirmModalMessage}
  confirmText="Confirm"
  cancelText="Cancel"
  confirmButtonClass="btn-primary"
  cancelButtonClass="btn-secondary"
  on:confirm={handleConfirmModalConfirm}
  on:cancel={handleConfirmModalCancel}
  on:close={handleConfirmModalCancel}
/>

<style>
  .settings-modal-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: var(--modal-backdrop);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1100;
    animation: fadeIn 0.2s ease-out;
  }

  @keyframes fadeIn {
    from {
      opacity: 0;
    }
    to {
      opacity: 1;
    }
  }

  .settings-modal {
    position: relative;
    width: 90vw;
    max-width: 1200px;
    height: 85vh;
    max-height: 900px;
    background-color: var(--surface-color);
    border-radius: 12px;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
    overflow: hidden;
    animation: slideUp 0.3s ease-out;
  }

  @keyframes slideUp {
    from {
      transform: translateY(20px);
      opacity: 0;
    }
    to {
      transform: translateY(0);
      opacity: 1;
    }
  }

  .modal-close-button {
    position: absolute;
    top: 0.75rem;
    right: 0.75rem;
    background: none;
    border: none;
    cursor: pointer;
    padding: 0.5rem;
    color: var(--text-secondary);
    transition: color 0.2s ease;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10;
  }

  .modal-close-button:hover {
    color: var(--text-color);
    background: var(--button-hover, var(--background-color));
  }

  .settings-modal-container {
    display: flex;
    height: 100%;
    overflow: hidden;
  }

  .settings-sidebar {
    width: 240px;
    background-color: var(--background-color);
    border-right: 1px solid var(--border-color);
    padding: 1.5rem 0;
    overflow-y: auto;
    flex-shrink: 0;
  }

  .settings-title {
    font-size: 1.25rem;
    font-weight: 600;
    margin: 0 1.25rem 1.5rem;
    color: var(--text-color);
  }

  .sidebar-section {
    margin-bottom: 1.5rem;
  }

  .section-heading {
    font-size: 0.6875rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-secondary);
    margin: 0 1.25rem 0.5rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border-color);
  }

  .section-nav {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .nav-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.5rem 1.25rem;
    border: none;
    background-color: transparent;
    color: var(--text-color);
    text-align: left;
    cursor: pointer;
    transition: color 0.15s;
    font-size: 0.8125rem;
    position: relative;
  }

  .nav-item:hover {
    color: var(--primary-color);
  }

  .nav-item.active {
    background-color: var(--primary-light);
    color: var(--primary-color);
    font-weight: 500;
  }

  .nav-item.active::before {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 3px;
    background-color: var(--primary-color);
  }

  .nav-item-label {
    flex: 1;
  }

  .dirty-indicator {
    color: var(--warning-color);
    font-size: 1.2em;
    line-height: 1;
  }

  .settings-content {
    flex: 1;
    overflow-y: auto;
    padding: 1.5rem;
  }

  .content-section {
    max-width: 100%;
  }

  .section-title {
    font-size: 1.125rem;
    font-weight: 600;
    margin: 0 0 0.25rem 0;
    color: var(--text-color);
  }

  .section-description {
    font-size: 0.8125rem;
    color: var(--text-secondary);
    margin: 0 0 1.25rem 0;
  }

  .settings-form {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .form-group {
    display: flex;
    flex-direction: column;
    gap: 0.375rem;
  }

  .form-group label {
    font-weight: 500;
    color: var(--text-color);
    font-size: 0.8125rem;
  }

  .form-control {
    padding: 0.5rem 0.625rem;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    background-color: var(--surface-color);
    color: var(--text-color);
    font-size: 0.8125rem;
    transition: border-color 0.15s, box-shadow 0.15s;
  }

  .form-control:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 3px var(--primary-light);
  }

  .form-control:disabled {
    opacity: 0.6;
    cursor: not-allowed;
    background-color: var(--background-color);
  }

  .form-text {
    font-size: 0.75rem;
    color: var(--text-secondary);
    margin-top: 0.125rem;
  }

  .password-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .toggle-password {
    background: none;
    border: none;
    cursor: pointer;
    padding: 4px;
    color: var(--text-secondary);
    display: flex;
    align-items: center;
    border-radius: 4px;
    transition: background-color 0.2s;
  }

  .toggle-password:hover {
    background-color: var(--background-color);
    color: var(--text-color);
  }

  .checkbox-label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    cursor: pointer;
    font-weight: normal;
    font-size: 0.8125rem;
  }

  .checkbox-label input[type="checkbox"] {
    width: 16px;
    height: 16px;
    cursor: pointer;
  }

  .form-actions {
    display: flex;
    gap: 0.75rem;
    margin-top: 0.75rem;
  }

  .btn {
    padding: 0.5rem 1rem;
    border-radius: 6px;
    border: none;
    font-size: 0.8125rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
  }

  .btn-primary {
    background-color: var(--primary-color);
    color: white;
  }

  .btn-primary:hover:not(:disabled) {
    background-color: var(--primary-hover);
  }

  .btn-primary:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-secondary {
    background-color: var(--background-color);
    color: var(--text-color);
    border: 1px solid var(--border-color);
  }

  .btn-secondary:hover:not(:disabled) {
    background-color: var(--border-color);
  }

  .btn-secondary:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-warning {
    background-color: var(--warning-color);
    color: white;
  }

  .btn-warning:hover:not(:disabled) {
    filter: brightness(0.9);
  }

  .btn-danger {
    background-color: var(--error-color);
    color: white;
  }

  .btn-danger:hover:not(:disabled) {
    filter: brightness(0.9);
  }

  .btn-small {
    padding: 0.25rem 0.625rem;
    font-size: 0.75rem;
  }

  .alert {
    padding: 0.625rem 0.875rem;
    border-radius: 6px;
    margin-bottom: 1rem;
    font-size: 0.8125rem;
  }

  .alert-success {
    background-color: #d1fae5;
    color: #065f46;
    border: 1px solid #6ee7b7;
  }

  .alert-error {
    background-color: #fee2e2;
    color: #991b1b;
    border: 1px solid #fca5a5;
  }

  :global([data-theme='dark']) .alert-success {
    background-color: #064e3b;
    color: #6ee7b7;
    border-color: #065f46;
  }

  :global([data-theme='dark']) .alert-error {
    background-color: #7f1d1d;
    color: #fca5a5;
    border-color: #991b1b;
  }

  .stats-actions {
    margin-bottom: 1rem;
  }

  .loading-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    color: var(--text-secondary);
  }

  .loading-state p {
    margin: 0;
    font-size: 0.8125rem;
  }

  .spinner {
    width: 32px;
    height: 32px;
    border: 3px solid var(--border-color);
    border-top-color: var(--primary-color);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin-bottom: 12px;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 1rem;
    margin-bottom: 1.5rem;
  }

  .stat-card {
    background-color: var(--background-color);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 1rem;
  }

  .stat-card-with-bar {
    display: flex;
    flex-direction: column;
  }

  .stat-card-content {
    flex: 1;
    display: flex;
    flex-direction: column;
    margin-bottom: 0.75rem;
  }

  .stat-card h4 {
    font-size: 0.6875rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-secondary);
    margin: 0 0 0.5rem 0;
  }

  .stat-value {
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--text-color);
    margin-bottom: 0.375rem;
  }

  .stat-detail {
    font-size: 0.75rem;
    color: var(--text-secondary);
    margin-bottom: 0.125rem;
  }

  .stat-detail span {
    display: block;
    margin-bottom: 0.125rem;
  }

  .progress-bar {
    width: 100%;
    height: 8px;
    background-color: var(--border-color);
    border-radius: 4px;
    overflow: hidden;
    margin-top: 0;
  }

  .progress-fill {
    height: 100%;
    background-color: var(--primary-color);
    transition: width 0.3s ease;
  }

  .recent-tasks {
    margin-top: 1.5rem;
  }

  .recent-tasks h4 {
    font-size: 0.9375rem;
    font-weight: 600;
    color: var(--text-color);
    margin: 0 0 0.75rem 0;
  }

  .table-container {
    overflow-x: auto;
    border: 1px solid var(--border-color);
    border-radius: 8px;
  }

  .data-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.8125rem;
  }

  .data-table thead {
    background-color: var(--background-color);
  }

  .data-table th {
    padding: 0.5rem 0.75rem;
    text-align: left;
    font-size: 0.6875rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-secondary);
    border-bottom: 1px solid var(--border-color);
  }

  .data-table td {
    padding: 0.625rem 0.75rem;
    border-bottom: 1px solid var(--border-color);
    color: var(--text-color);
  }

  .data-table tbody tr:last-child td {
    border-bottom: none;
  }

  .data-table tbody tr:hover {
    background-color: var(--background-color);
  }

  .status-badge {
    display: inline-block;
    padding: 0.125rem 0.5rem;
    border-radius: 10px;
    font-size: 0.6875rem;
    font-weight: 500;
    text-transform: capitalize;
  }

  .status-completed,
  .status-success {
    background-color: #d1fae5;
    color: #065f46;
  }

  .status-running,
  .status-processing {
    background-color: #dbeafe;
    color: #1e40af;
  }

  .status-pending {
    background-color: #fef3c7;
    color: #92400e;
  }

  .status-failed,
  .status-error {
    background-color: #fee2e2;
    color: #991b1b;
  }

  :global([data-theme='dark']) .status-completed,
  :global([data-theme='dark']) .status-success {
    background-color: #064e3b;
    color: #6ee7b7;
  }

  :global([data-theme='dark']) .status-running,
  :global([data-theme='dark']) .status-processing {
    background-color: #1e3a8a;
    color: #93c5fd;
  }

  :global([data-theme='dark']) .status-pending {
    background-color: #78350f;
    color: #fde68a;
  }

  :global([data-theme='dark']) .status-failed,
  :global([data-theme='dark']) .status-error {
    background-color: #7f1d1d;
    color: #fca5a5;
  }

  .task-health-grid {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .health-card {
    background-color: var(--background-color);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 1rem;
  }

  .health-card h4 {
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--text-color);
    margin: 0 0 0.75rem 0;
  }

  .action-buttons {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .placeholder-message {
    text-align: center;
    padding: 2rem;
    color: var(--text-secondary);
    font-size: 0.8125rem;
  }

  .empty-state {
    text-align: center;
    padding: 1rem;
    color: var(--text-secondary);
    font-size: 0.8125rem;
    font-style: italic;
  }

  /* Responsive Design */
  @media (max-width: 768px) {
    .settings-modal {
      width: 100vw;
      height: 100vh;
      max-width: none;
      max-height: none;
      border-radius: 0;
    }

    .settings-modal-container {
      flex-direction: column;
    }

    .settings-sidebar {
      width: 100%;
      border-right: none;
      border-bottom: 1px solid var(--border-color);
      padding: 1rem 0;
      max-height: 200px;
    }

    .settings-title {
      margin: 0 1rem 1rem;
    }

    .section-heading {
      margin: 0 1rem 0.5rem;
    }

    .nav-item {
      padding: 0.625rem 1rem;
    }

    .settings-content {
      padding: 1.5rem;
    }

    .stats-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
