<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { user as userStore, authStore, fetchUserInfo } from '$stores/auth';
  import { settingsModalStore, type SettingsSection } from '$stores/settingsModalStore';
  import { toastStore } from '$stores/toast';
  import axiosInstance from '$lib/axios';
  import { UserSettingsApi, RecordingSettingsHelper, type RecordingSettings } from '$lib/api/userSettings';

  // Import settings components
  import LLMSettings from '$components/settings/LLMSettings.svelte';
  import PromptSettings from '$components/settings/PromptSettings.svelte';
  import AudioExtractionSettings from '$components/settings/AudioExtractionSettings.svelte';
  import TranscriptionSettings from '$components/settings/TranscriptionSettings.svelte';
  import RetrySettings from '$components/settings/RetrySettings.svelte';
  import LanguageSettings from '$components/settings/LanguageSettings.svelte';
  import UserManagementTable from '$components/UserManagementTable.svelte';
  import ConfirmationModal from '$components/ConfirmationModal.svelte';

  // Import i18n
  import { t } from '$stores/locale';

  // Modal state
  let modalElement: HTMLElement;
  let showCloseConfirmation = false;

  // Settings state
  $: isOpen = $settingsModalStore.isOpen;
  $: activeSection = $settingsModalStore.activeSection;
  $: isAdmin = $userStore?.role === 'admin';
  $: isLocalUser = $userStore?.auth_type === 'local';

  // User Profile section
  let fullName = '';
  let email = '';
  let profileChanged = false;
  let profileLoading = false;

  // Password section
  let currentPassword = '';
  let newPassword = '';
  let confirmPassword = '';
  let passwordChanged = false;
  let passwordLoading = false;
  let showCurrentPassword = false;
  let showNewPassword = false;
  let showConfirmPassword = false;

  // Recording settings section
  let maxRecordingDuration = 120;
  let recordingQuality: 'standard' | 'high' | 'maximum' = 'high';
  let autoStopEnabled = true;
  let recordingSettingsChanged = false;
  let recordingSettingsLoading = false;

  // Admin Users section
  let users: any[] = [];
  let usersLoading = false;

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
    models: {
      whisper: { name: 'N/A', description: 'N/A', purpose: 'N/A' },
      diarization: { name: 'N/A', description: 'N/A', purpose: 'N/A' },
      alignment: { name: 'N/A', description: 'N/A', purpose: 'N/A' }
    },
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

  // Admin Task Health section
  let taskHealthData: any = null;
  let taskHealthLoading = false;
  let showConfirmModal = false;
  let confirmModalTitle = '';
  let confirmModalMessage = '';
  let confirmCallback: (() => void) | null = null;

  // Define sidebar sections
  $: sidebarSections = [
    {
      title: $t('settings.sections.system'),
      items: [
        { id: 'system-statistics' as SettingsSection, label: $t('settings.statistics.title'), icon: 'chart' }
      ]
    },
    ...(isAdmin ? [
      {
        title: $t('settings.sections.administration'),
        items: [
          { id: 'admin-users' as SettingsSection, label: $t('settings.users.title'), icon: 'users' },
          { id: 'admin-task-health' as SettingsSection, label: $t('settings.taskHealth.title'), icon: 'health' },
          { id: 'admin-settings' as SettingsSection, label: $t('settings.systemSettings.title'), icon: 'settings' }
        ]
      }
    ] : []),
    {
      title: $t('settings.sections.userSettings'),
      items: [
        { id: 'profile' as SettingsSection, label: $t('settings.profile.title'), icon: 'user' },
        { id: 'language' as SettingsSection, label: $t('settings.language.title'), icon: 'globe' },
        { id: 'recording' as SettingsSection, label: $t('settings.recording.title'), icon: 'mic' },
        { id: 'audio-extraction' as SettingsSection, label: $t('settings.audioExtraction.title'), icon: 'file-audio' },
        { id: 'transcription' as SettingsSection, label: $t('settings.transcription.title'), icon: 'waveform' },
        { id: 'ai-prompts' as SettingsSection, label: $t('settings.aiPrompts.title'), icon: 'message' },
        { id: 'llm-provider' as SettingsSection, label: $t('settings.llmProvider.title'), icon: 'brain' }
      ]
    }
  ];

  // Reactive profile change detection
  $: if ($authStore.user) {
    profileChanged = $authStore.user.full_name !== fullName;
  }

  // Reactive password change detection
  $: {
    passwordChanged = !!(currentPassword || newPassword || confirmPassword);
  }

  // Combined profile dirty state (profile changes OR password changes)
  $: {
    const isDirty = profileChanged || passwordChanged;
    settingsModalStore.setDirty('profile', isDirty);
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

    // Load statistics for any user
    if (activeSection === 'system-statistics') {
      loadStats();
    }

    // Load admin data if admin
    if (isAdmin) {
      if (activeSection === 'admin-users') {
        loadAdminUsers();
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
      if (activeSection === 'system-statistics') {
        loadStats();
      } else if (activeSection === 'admin-users' && isAdmin) {
        loadAdminUsers();
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

    // Reset password
    currentPassword = '';
    newPassword = '';
    confirmPassword = '';
    showCurrentPassword = false;
    showNewPassword = false;
    showConfirmPassword = false;

    // Reset recording settings
    loadRecordingSettings();

    // Clear all dirty states
    settingsModalStore.clearAllDirty();
  }

  function switchSection(sectionId: SettingsSection) {
    settingsModalStore.setActiveSection(sectionId);

    // Load data for specific sections
    if (sectionId === 'system-statistics') {
      loadStats();
    } else if (sectionId === 'admin-users') {
      loadAdminUsers();
    } else if (sectionId === 'admin-task-health') {
      loadTaskHealth();
    }
  }

  // Profile functions
  async function updateProfile() {
    profileLoading = true;

    try {
      const response = await axiosInstance.put('/users/me', {
        full_name: fullName
      });

      authStore.setUser(response.data);
      localStorage.setItem('user', JSON.stringify(response.data));

      toastStore.success($t('settings.toast.profileUpdated'));
      profileChanged = false;
      settingsModalStore.clearDirty('profile');

      await fetchUserInfo();
    } catch (err: any) {
      console.error('Error updating profile:', err);
      const message = err.response?.data?.detail || $t('settings.toast.profileUpdateFailed');
      toastStore.error(message);
    } finally {
      profileLoading = false;
    }
  }

  // Password functions
  async function updatePassword() {
    passwordLoading = true;

    // Validation
    if (!currentPassword || !newPassword || !confirmPassword) {
      toastStore.error($t('settings.toast.passwordFieldsRequired'));
      passwordLoading = false;
      return;
    }

    if (newPassword !== confirmPassword) {
      toastStore.error($t('settings.toast.passwordsNotMatch'));
      passwordLoading = false;
      return;
    }

    if (newPassword.length < 8) {
      toastStore.error($t('settings.toast.passwordTooShort'));
      passwordLoading = false;
      return;
    }

    try {
      await axiosInstance.put('/users/me', {
        password: newPassword,
        current_password: currentPassword
      });

      toastStore.success($t('settings.toast.passwordUpdated'));

      // Clear password fields
      currentPassword = '';
      newPassword = '';
      confirmPassword = '';
      showCurrentPassword = false;
      showNewPassword = false;
      showConfirmPassword = false;
      passwordChanged = false;
      // Note: dirty state is managed reactively based on profileChanged || passwordChanged
    } catch (err: any) {
      console.error('Error updating password:', err);
      const message = err.response?.data?.detail || $t('settings.toast.passwordUpdateFailed');
      toastStore.error(message);
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
      const message = err.response?.data?.detail || $t('settings.toast.recordingSettingsSaveFailed');
      toastStore.error(message);
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

    // Validate settings
    const settingsToValidate: RecordingSettings = {
      max_recording_duration: maxRecordingDuration,
      recording_quality: recordingQuality,
      auto_stop_enabled: autoStopEnabled
    };

    const validationErrors = RecordingSettingsHelper.validateSettings(settingsToValidate);
    if (validationErrors.length > 0) {
      toastStore.error(validationErrors[0]);
      recordingSettingsLoading = false;
      return;
    }

    try {
      await UserSettingsApi.updateRecordingSettings(settingsToValidate);
      toastStore.success($t('settings.toast.recordingSettingsSaved'));
      recordingSettingsChanged = false;
      settingsModalStore.clearDirty('recording');
    } catch (err: any) {
      console.error('Error saving recording settings:', err);
      const message = err.response?.data?.detail || $t('settings.toast.recordingSettingsSaveFailed');
      toastStore.error(message);
    } finally {
      recordingSettingsLoading = false;
    }
  }

  async function resetRecordingSettings() {
    recordingSettingsLoading = true;

    try {
      await UserSettingsApi.resetRecordingSettings();
      await loadRecordingSettings();
      toastStore.success($t('settings.toast.recordingSettingsReset'));
      recordingSettingsChanged = false;
      settingsModalStore.clearDirty('recording');
    } catch (err: any) {
      console.error('Error resetting recording settings:', err);
      const message = err.response?.data?.detail || $t('settings.toast.recordingSettingsResetFailed');
      toastStore.error(message);
    } finally {
      recordingSettingsLoading = false;
    }
  }

  // Admin functions
  async function loadAdminUsers(showLoading = true) {
    // Only show loading spinner on initial load, not on refresh
    if (showLoading) {
      usersLoading = true;
    }

    try {
      const response = await axiosInstance.get('/admin/users');
      users = response.data;
    } catch (err: any) {
      console.error('Error loading admin users:', err);
      const message = err.response?.data?.detail || $t('settings.toast.usersLoadFailed');
      toastStore.error(message);
    } finally {
      if (showLoading) {
        usersLoading = false;
      }
    }
  }

  async function refreshAdminUsers() {
    // Silent refresh - don't show loading spinner to reduce flicker
    await loadAdminUsers(false);
  }

  async function recoverUserFiles(userId: string) {
    try {
      await axiosInstance.post(`/tasks/system/recover-user-files/${userId}`);
      toastStore.success($t('settings.toast.userRecoveryInitiated'));
    } catch (err: any) {
      console.error('Error recovering user files:', err);
      const message = err.response?.data?.detail || $t('settings.toast.userRecoveryFailed');
      toastStore.error(message);
    }
  }

  async function loadStats() {
    statsLoading = true;

    try {
      const response = await axiosInstance.get('/system/stats');
      stats = response.data;
    } catch (err: any) {
      console.error('Error loading stats:', err);
      const message = err.response?.data?.detail || $t('settings.toast.statisticsLoadFailed');
      toastStore.error(message);
    } finally {
      statsLoading = false;
    }
  }

  async function refreshStats() {
    await loadStats();
  }

  async function loadTaskHealth() {
    taskHealthLoading = true;

    try {
      const response = await axiosInstance.get('/tasks/system/health');
      taskHealthData = response.data;
    } catch (err: any) {
      console.error('Error loading task health:', err);
      const message = err.response?.data?.detail || $t('settings.toast.taskHealthLoadFailed');
      toastStore.error(message);
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
      $t('settings.taskHealth.recoverStuck'),
      $t('settings.taskHealth.confirmRecoverStuck'),
      async () => {
        try {
          await axiosInstance.post('/tasks/recover-stuck-tasks');
          toastStore.success($t('settings.toast.stuckTasksRecoveryInitiated'));
          await refreshTaskHealth();
        } catch (err: any) {
          console.error('Error recovering stuck tasks:', err);
          const message = err.response?.data?.detail || $t('settings.toast.stuckTasksRecoveryFailed');
          toastStore.error(message);
        }
      }
    );
  }

  async function fixInconsistentFiles() {
    showConfirmation(
      $t('settings.taskHealth.fixInconsistent'),
      $t('settings.taskHealth.confirmFixInconsistent'),
      async () => {
        try {
          await axiosInstance.post('/tasks/fix-inconsistent-files');
          toastStore.success($t('settings.toast.inconsistentFilesFixInitiated'));
          await refreshTaskHealth();
        } catch (err: any) {
          console.error('Error fixing inconsistent files:', err);
          const message = err.response?.data?.detail || $t('settings.toast.inconsistentFilesFixFailed');
          toastStore.error(message);
        }
      }
    );
  }

  async function startupRecovery() {
    showConfirmation(
      $t('settings.taskHealth.startupRecovery'),
      $t('settings.taskHealth.confirmStartupRecovery'),
      async () => {
        try {
          await axiosInstance.post('/tasks/system/startup-recovery');
          toastStore.success($t('settings.toast.startupRecoveryInitiated'));
          await refreshTaskHealth();
        } catch (err: any) {
          console.error('Error running startup recovery:', err);
          const message = err.response?.data?.detail || $t('settings.toast.startupRecoveryFailed');
          toastStore.error(message);
        }
      }
    );
  }

  async function recoverAllUserFiles() {
    showConfirmation(
      $t('settings.taskHealth.recoverAllUsers'),
      $t('settings.taskHealth.confirmRecoverAllUsers'),
      async () => {
        try {
          await axiosInstance.post('/tasks/system/recover-all-user-files');
          toastStore.success($t('settings.toast.allUserFilesRecoveryInitiated'));
          await refreshTaskHealth();
        } catch (err: any) {
          console.error('Error recovering all user files:', err);
          const message = err.response?.data?.detail || $t('settings.toast.allUserFilesRecoveryFailed');
          toastStore.error(message);
        }
      }
    );
  }

  async function retryTask(taskId: number) {
    try {
      await axiosInstance.post(`/tasks/system/recover-task/${taskId}`);
      toastStore.success($t('settings.toast.taskRetryInitiated'));
      await refreshTaskHealth();
    } catch (err: any) {
      console.error('Error retrying task:', err);
      const message = err.response?.data?.detail || $t('settings.toast.taskRetryFailed');
      toastStore.error(message);
    }
  }

  async function retryFile(fileId: string) {
    try {
      await axiosInstance.post(`/tasks/retry-file/${fileId}`);
      toastStore.success($t('settings.toast.fileRetryInitiated'));
      await refreshTaskHealth();
    } catch (err: any) {
      console.error('Error retrying file:', err);
      const message = err.response?.data?.detail || $t('settings.toast.fileRetryFailed');
      toastStore.error(message);
    }
  }

  // AI settings change handlers
  function onAISettingsChange() {
    // Handler for AI settings changes - can be extended for additional logic
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

  // Helper function for formatting status text
  function formatStatus(status: string): string {
    // Translate status values
    const statusMap: Record<string, string> = {
      'completed': $t('common.completed'),
      'processing': $t('common.processing'),
      'pending': $t('common.pending'),
      'error': $t('common.error'),
      'failed': $t('fileStatus.failed'),
      'in_progress': $t('fileStatus.inProgress'),
      'success': $t('common.success'),
    };
    return statusMap[status.toLowerCase()] || status.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
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
      <button class="modal-close-button" on:click={attemptClose} aria-label={$t('settings.modal.closeSettings')} title={$t('settings.modal.closeSettingsTitle')}>
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="18" y1="6" x2="6" y2="18"></line>
          <line x1="6" y1="6" x2="18" y2="18"></line>
        </svg>
      </button>

      <div class="settings-modal-container">
        <!-- Sidebar -->
        <aside class="settings-sidebar">
          <h2 id="settings-modal-title" class="settings-title">{$t('settings.title')}</h2>

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
                      <span class="dirty-indicator" title={$t('settings.unsavedChanges')}>●</span>
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
              <h3 class="section-title">{$t('settings.profile.title')}</h3>
              <p class="section-description">{$t('settings.profile.description')}</p>

              <form on:submit|preventDefault={updateProfile} class="settings-form">
                <div class="form-group">
                  <label for="email">{$t('auth.email')}</label>
                  <input
                    type="email"
                    id="email"
                    class="form-control"
                    value={email}
                    disabled
                  />
                  <small class="form-text">{$t('settings.profile.emailCannotChange')}</small>
                </div>

                <div class="form-group">
                  <label for="fullName">{$t('settings.profile.fullName')}</label>
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
                    {profileLoading ? $t('common.saving') : $t('common.saveChanges')}
                  </button>
                </div>
              </form>

              <!-- Password Change Section -->
              {#if isLocalUser}
              <div class="password-section-divider">
                <h4 class="subsection-title">{$t('settings.profile.changePassword')}</h4>
              </div>

              <form on:submit|preventDefault={updatePassword} class="settings-form">
                <div class="form-group">
                  <div class="password-header">
                    <label for="currentPassword">{$t('settings.profile.currentPassword')}</label>
                    <button
                      type="button"
                      class="toggle-password"
                      on:click={() => showCurrentPassword = !showCurrentPassword}
                      tabindex="-1"
                      aria-label={showCurrentPassword ? $t('auth.hidePassword') : $t('auth.showPassword')}
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
                  />
                </div>

                <div class="form-group">
                  <div class="password-header">
                    <label for="newPassword">{$t('settings.profile.newPassword')}</label>
                    <button
                      type="button"
                      class="toggle-password"
                      on:click={() => showNewPassword = !showNewPassword}
                      tabindex="-1"
                      aria-label={showNewPassword ? $t('auth.hidePassword') : $t('auth.showPassword')}
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
                  />
                  <small class="form-text">{$t('auth.passwordMinLength')}</small>
                </div>

                <div class="form-group">
                  <div class="password-header">
                    <label for="confirmPassword">{$t('settings.profile.confirmNewPassword')}</label>
                    <button
                      type="button"
                      class="toggle-password"
                      on:click={() => showConfirmPassword = !showConfirmPassword}
                      tabindex="-1"
                      aria-label={showConfirmPassword ? $t('auth.hidePassword') : $t('auth.showPassword')}
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
                  />
                </div>

                <div class="form-actions">
                  <button
                    type="submit"
                    class="btn btn-primary"
                    disabled={!passwordChanged || passwordLoading}
                  >
                    {passwordLoading ? $t('common.updating') : $t('settings.profile.updatePassword')}
                  </button>
                </div>
              </form>
              {/if}
            </div>
          {/if}

          <!-- Language Settings Section -->
          {#if activeSection === 'language'}
            <div class="content-section">
              <h3 class="section-title">{$t('settings.language.title')}</h3>
              <p class="section-description">{$t('settings.language.description')}</p>
              <LanguageSettings />
            </div>
          {/if}

          <!-- Recording Settings Section -->
          {#if activeSection === 'recording'}
            <div class="content-section">
              <h3 class="section-title">{$t('settings.recording.title')}</h3>
              <p class="section-description">{$t('settings.recording.description')}</p>

              <form on:submit|preventDefault={saveRecordingSettings} class="settings-form">
                <div class="form-group">
                  <label for="maxRecordingDuration">{$t('settings.recording.maxDuration')}</label>
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
                  <small class="form-text">{$t('settings.recording.durationRange')}</small>
                </div>

                <div class="form-group">
                  <label for="recordingQuality">{$t('settings.recording.quality')}</label>
                  <select
                    id="recordingQuality"
                    class="form-control"
                    bind:value={recordingQuality}
                    on:change={handleRecordingSettingsChange}
                  >
                    <option value="standard">{$t('settings.recording.qualityStandard')}</option>
                    <option value="high">{$t('settings.recording.qualityHigh')}</option>
                    <option value="maximum">{$t('settings.recording.qualityMaximum')}</option>
                  </select>
                  <small class="form-text">{$t('settings.recording.qualityHelp')}</small>
                </div>

                <div class="form-group">
                  <label class="checkbox-label">
                    <input
                      type="checkbox"
                      bind:checked={autoStopEnabled}
                      on:change={handleRecordingSettingsChange}
                    />
                    <span>{$t('settings.recording.autoStop')}</span>
                  </label>
                  <small class="form-text">{$t('settings.recording.autoStopHelp')}</small>
                </div>

                <div class="form-actions">
                  <button
                    type="submit"
                    class="btn btn-primary"
                    disabled={!recordingSettingsChanged || recordingSettingsLoading}
                  >
                    {recordingSettingsLoading ? $t('common.saving') : $t('common.saveSettings')}
                  </button>

                  <button
                    type="button"
                    class="btn btn-secondary"
                    on:click={resetRecordingSettings}
                    disabled={recordingSettingsLoading}
                  >
                    {$t('common.resetToDefaults')}
                  </button>
                </div>
              </form>
            </div>
          {/if}

          <!-- Audio Extraction Settings Section -->
          {#if activeSection === 'audio-extraction'}
            <div class="content-section">
              <h3 class="section-title">{$t('settings.audioExtraction.title')}</h3>
              <p class="section-description">{$t('settings.audioExtraction.description')}</p>
              <AudioExtractionSettings />
            </div>
          {/if}

          <!-- Transcription Settings Section -->
          {#if activeSection === 'transcription'}
            <div class="content-section">
              <h3 class="section-title">{$t('settings.transcription.title')}</h3>
              <p class="section-description">{$t('settings.transcription.description')}</p>
              <TranscriptionSettings />
            </div>
          {/if}

          <!-- AI Prompts Section -->
          {#if activeSection === 'ai-prompts'}
            <div class="content-section">
              <h3 class="section-title">{$t('settings.aiPrompts.title')}</h3>
              <p class="section-description">{$t('settings.aiPrompts.description')}</p>
              <PromptSettings onSettingsChange={onAISettingsChange} />
            </div>
          {/if}

          <!-- LLM Provider Section -->
          {#if activeSection === 'llm-provider'}
            <div class="content-section">
              <h3 class="section-title">{$t('settings.llmProvider.title')}</h3>
              <p class="section-description">{$t('settings.llmProvider.description')}</p>
              <LLMSettings onSettingsChange={onAISettingsChange} />
            </div>
          {/if}

          <!-- Admin Users Section -->
          {#if activeSection === 'admin-users' && isAdmin}
            <div class="content-section">
              <h3 class="section-title">{$t('settings.users.title')}</h3>
              <p class="section-description">{$t('settings.users.description')}</p>
              <UserManagementTable
                {users}
                loading={usersLoading}
                onRefresh={refreshAdminUsers}
                onUserRecovery={recoverUserFiles}
              />
            </div>
          {/if}

          <!-- System Statistics Section -->
          {#if activeSection === 'system-statistics'}
            <div class="content-section">
              <h3 class="section-title">{$t('settings.statistics.title')}</h3>
              <p class="section-description">{$t('settings.statistics.description')}</p>

              <div class="stats-actions">
                <button
                  type="button"
                  class="btn btn-secondary"
                  on:click={refreshStats}
                  disabled={statsLoading}
                >
                  {statsLoading ? $t('settings.statistics.loading') : $t('settings.statistics.refresh')}
                </button>
              </div>

              {#if statsLoading}
                <div class="loading-state">
                  <div class="spinner"></div>
                  <p>{$t('settings.statistics.loadingMessage')}</p>
                </div>
              {:else}
                <div class="stats-grid">
                  <!-- User Stats -->
                  <div class="stat-card">
                    <h4>{$t('settings.statistics.users')}</h4>
                    <div class="stat-value">{stats.users?.total || 0}</div>
                    <div class="stat-detail">{$t('settings.statistics.newUsers')}: {stats.users?.new || 0}</div>
                  </div>

                  <!-- Media Stats -->
                  <div class="stat-card">
                    <h4>{$t('settings.statistics.mediaFiles')}</h4>
                    <div class="stat-value">{stats.files?.total || 0}</div>
                    <div class="stat-detail">{$t('settings.statistics.new')}: {stats.files?.new || 0}</div>
                    <div class="stat-detail">{$t('settings.statistics.segments')}: {stats.files?.segments || 0}</div>
                  </div>

                  <!-- Task Stats -->
                  <div class="stat-card">
                    <h4>{$t('settings.statistics.tasks')}</h4>
                    <div class="stat-detail">{$t('settings.statistics.pending')}: {stats.tasks?.pending || 0}</div>
                    <div class="stat-detail">{$t('settings.statistics.running')}: {stats.tasks?.running || 0}</div>
                    <div class="stat-detail">{$t('settings.statistics.completed')}: {stats.tasks?.completed || 0}</div>
                    <div class="stat-detail">{$t('settings.statistics.failed')}: {stats.tasks?.failed || 0}</div>
                    <div class="stat-detail">{$t('settings.statistics.successRate')}: {stats.tasks?.success_rate || 0}%</div>
                  </div>

                  <!-- Performance Stats -->
                  <div class="stat-card">
                    <h4>{$t('settings.statistics.performance')}</h4>
                    <div class="stat-detail">{$t('settings.statistics.avgProcessTime')}: {formatTime(stats.tasks?.avg_processing_time || 0)}</div>
                    <div class="stat-detail">{$t('settings.statistics.speakers')}: {stats.speakers?.total || 0}</div>
                  </div>

                  <!-- AI Models -->
                  <div class="stat-card model-card">
                    <h4>{$t('settings.statistics.aiModels')}</h4>
                    {#if stats.models}
                      <div class="model-info">
                        <div class="model-item">
                          <span class="model-label">{$t('settings.statistics.whisperModel')}:</span>
                          <span class="model-value">{stats.models.whisper?.name || 'N/A'}</span>
                        </div>
                        <div class="model-item">
                          <span class="model-label">{$t('settings.statistics.diarization')}:</span>
                          <span class="model-value">{stats.models.diarization?.name || 'N/A'}</span>
                        </div>
                        <div class="model-item">
                          <span class="model-label">{$t('settings.statistics.alignment')}:</span>
                          <span class="model-value">{stats.models.alignment?.name || 'N/A'}</span>
                        </div>
                      </div>
                    {:else}
                      <div class="stat-detail">{$t('settings.statistics.modelNotAvailable')}</div>
                    {/if}
                  </div>

                  <!-- System Resources: CPU & Memory -->
                  <div class="stat-card stat-card-stacked">
                    <div class="stat-section">
                      <h4>{$t('settings.statistics.cpuUsage')}</h4>
                      <div class="stat-value">{stats.system?.cpu?.total_percent || '0%'}</div>
                      <div class="progress-bar">
                        <div class="progress-fill" style="width: {parseFloat(stats.system?.cpu?.total_percent) || 0}%"></div>
                      </div>
                    </div>

                    <div class="stat-section">
                      <h4>{$t('settings.statistics.memoryUsage')}</h4>
                      <div class="stat-value">{stats.system?.memory?.percent || '0%'}</div>
                      <div class="stat-detail-compact">
                        {stats.system?.memory?.used || $t('common.unknown')} / {stats.system?.memory?.total || $t('common.unknown')}
                      </div>
                      <div class="progress-bar">
                        <div class="progress-fill" style="width: {parseFloat(stats.system?.memory?.percent) || 0}%"></div>
                      </div>
                    </div>
                  </div>

                  <div class="stat-card stat-card-with-bar">
                    <div class="stat-card-content">
                      <h4>{$t('settings.statistics.diskUsage')}</h4>
                      <div class="stat-value">{stats.system?.disk?.percent || '0%'}</div>
                      <div class="stat-detail">
                        <span>{$t('settings.statistics.total')}: {stats.system?.disk?.total || $t('common.unknown')}</span>
                        <span>{$t('settings.statistics.used')}: {stats.system?.disk?.used || $t('common.unknown')}</span>
                        <span>{$t('settings.statistics.free')}: {stats.system?.disk?.free || $t('common.unknown')}</span>
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
                        <h4>{$t('settings.statistics.gpuVram')}</h4>
                        <div class="stat-value">{stats.system.gpu.memory_percent || '0%'}</div>
                        <div class="stat-detail">
                          <span>{$t('settings.statistics.gpu')}: {stats.system.gpu.name || $t('common.unknown')}</span>
                          <span>{$t('settings.statistics.total')}: {stats.system.gpu.memory_total || $t('common.unknown')}</span>
                          <span>{$t('settings.statistics.used')}: {stats.system.gpu.memory_used || $t('common.unknown')}</span>
                          <span>{$t('settings.statistics.free')}: {stats.system.gpu.memory_free || $t('common.unknown')}</span>
                        </div>
                      </div>
                      <div class="progress-bar">
                        <div class="progress-fill" style="width: {parseFloat(stats.system.gpu.memory_percent) || 0}%"></div>
                      </div>
                    {:else}
                      <div class="stat-card-content">
                        <h4>{$t('settings.statistics.gpuVram')}</h4>
                        <div class="stat-value">N/A</div>
                        <div class="stat-detail">{stats.system?.gpu?.name || $t('settings.statistics.noGpu')}</div>
                      </div>
                    {/if}
                  </div>
                </div>

                <!-- Recent Tasks Table -->
                {#if stats.tasks?.recent && stats.tasks.recent.length > 0}
                  <div class="recent-tasks">
                    <h4>{$t('settings.statistics.recentTasks')}</h4>
                    <div class="table-container">
                      <table class="data-table">
                        <thead>
                          <tr>
                            <th>{$t('settings.statistics.taskId')}</th>
                            <th>{$t('settings.statistics.type')}</th>
                            <th>{$t('settings.statistics.status')}</th>
                            <th>{$t('settings.statistics.created')}</th>
                            <th>{$t('settings.statistics.elapsed')}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {#each stats.tasks.recent as task}
                            <tr>
                              <td>{task.id.substring(0, 8)}...</td>
                              <td>{task.type}</td>
                              <td>
                                <span class="status-badge status-{task.status}">{formatStatus(task.status)}</span>
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
                    <h4>{$t('settings.statistics.recentTasks')}</h4>
                    <p class="empty-state">{$t('settings.statistics.noRecentTasks')}</p>
                  </div>
                {/if}
              {/if}
            </div>
          {/if}

          <!-- Admin Task Health Section -->
          {#if activeSection === 'admin-task-health' && isAdmin}
            <div class="content-section">
              <h3 class="section-title">{$t('settings.taskHealth.title')}</h3>
              <p class="section-description">{$t('settings.taskHealth.description')}</p>

              <div class="stats-actions">
                <button
                  type="button"
                  class="btn btn-secondary"
                  on:click={refreshTaskHealth}
                  disabled={taskHealthLoading}
                >
                  {taskHealthLoading ? $t('settings.taskHealth.loading') : $t('settings.taskHealth.refresh')}
                </button>
              </div>

              {#if taskHealthLoading}
                <div class="loading-state">
                  <div class="spinner"></div>
                  <p>{$t('settings.taskHealth.loadingMessage')}</p>
                </div>
              {:else if taskHealthData}
                <div class="task-health-grid">
                  <!-- Recovery Actions -->
                  <div class="health-card">
                    <h4>{$t('settings.taskHealth.systemRecovery')}</h4>
                    <div class="action-buttons">
                      <button class="btn btn-warning" on:click={recoverStuckTasks}>
                        {$t('settings.taskHealth.recoverStuck')} ({taskHealthData.stuck_tasks?.length || 0})
                      </button>
                      <button class="btn btn-warning" on:click={fixInconsistentFiles}>
                        {$t('settings.taskHealth.fixInconsistent')} ({taskHealthData.inconsistent_files?.length || 0})
                      </button>
                      <button class="btn btn-primary" on:click={startupRecovery}>
                        {$t('settings.taskHealth.startupRecovery')}
                      </button>
                      <button class="btn btn-primary" on:click={recoverAllUserFiles}>
                        {$t('settings.taskHealth.recoverAllUsers')}
                      </button>
                    </div>
                  </div>

                  <!-- Stuck Tasks -->
                  {#if taskHealthData.stuck_tasks && taskHealthData.stuck_tasks.length > 0}
                    <div class="health-card">
                      <h4>{$t('settings.taskHealth.stuckTasks')}</h4>
                      <div class="table-container">
                        <table class="data-table">
                          <thead>
                            <tr>
                              <th>{$t('settings.taskHealth.id')}</th>
                              <th>{$t('settings.statistics.type')}</th>
                              <th>{$t('settings.statistics.status')}</th>
                              <th>{$t('settings.statistics.created')}</th>
                              <th>{$t('settings.taskHealth.actions')}</th>
                            </tr>
                          </thead>
                          <tbody>
                            {#each taskHealthData.stuck_tasks as task}
                              <tr>
                                <td>{task.id}</td>
                                <td>{task.task_type}</td>
                                <td><span class="status-badge status-{task.status}">{formatStatus(task.status)}</span></td>
                                <td>{new Date(task.created_at).toLocaleString()}</td>
                                <td>
                                  <button class="btn-small btn-primary" on:click={() => retryTask(task.id)}>
                                    {$t('settings.taskHealth.retry')}
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
                      <h4>{$t('settings.taskHealth.inconsistentFiles')}</h4>
                      <div class="table-container">
                        <table class="data-table">
                          <thead>
                            <tr>
                              <th>{$t('settings.taskHealth.id')}</th>
                              <th>{$t('settings.taskHealth.filename')}</th>
                              <th>{$t('settings.statistics.status')}</th>
                              <th>{$t('settings.taskHealth.actions')}</th>
                            </tr>
                          </thead>
                          <tbody>
                            {#each taskHealthData.inconsistent_files as file}
                              <tr>
                                <td>{file.uuid}</td>
                                <td>{file.filename}</td>
                                <td><span class="status-badge status-{file.status}">{formatStatus(file.status)}</span></td>
                                <td>
                                  <button class="btn-small btn-primary" on:click={() => retryFile(file.uuid)}>
                                    {$t('settings.taskHealth.retry')}
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
                  <p>{$t('settings.taskHealth.clickRefresh')}</p>
                </div>
              {/if}
            </div>
          {/if}

          <!-- Admin System Settings Section -->
          {#if activeSection === 'admin-settings' && isAdmin}
            <div class="content-section">
              <h3 class="section-title">{$t('settings.systemSettings.title')}</h3>
              <p class="section-description">{$t('settings.systemSettings.description')}</p>

              <!-- Retry Settings -->
              <div class="settings-subsection">
                <RetrySettings />
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
  title={$t('settings.unsavedChanges')}
  message={$t('settings.unsavedChangesMessage')}
  confirmText={$t('settings.closeWithoutSaving')}
  cancelText={$t('settings.keepEditing')}
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
  confirmText={$t('settings.confirm')}
  cancelText={$t('settings.cancel')}
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

  .password-section-divider {
    margin-top: 2rem;
    padding-top: 1.5rem;
    border-top: 1px solid var(--border-color);
  }

  .subsection-title {
    font-size: 0.9375rem;
    font-weight: 600;
    margin: 0 0 1rem 0;
    color: var(--text-color);
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

  .stat-card-stacked {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .stat-section {
    display: flex;
    flex-direction: column;
  }

  .stat-section h4 {
    font-size: 0.6875rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-secondary);
    margin: 0 0 0.5rem 0;
  }

  .stat-section .stat-value {
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--text-color);
    margin-bottom: 0.375rem;
  }

  .stat-detail-compact {
    font-size: 0.6875rem;
    color: var(--text-secondary);
    margin-bottom: 0.375rem;
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
  .status-processing,
  .status-in_progress {
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
  :global([data-theme='dark']) .status-processing,
  :global([data-theme='dark']) .status-in_progress {
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

  .settings-subsection {
    background-color: var(--background-color);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 1.25rem;
    margin-bottom: 1rem;
  }

  .empty-state {
    text-align: center;
    padding: 1rem;
    color: var(--text-secondary);
    font-size: 0.8125rem;
    font-style: italic;
  }

  /* AI Models Card Styles */
  .model-card {
    grid-column: span 1;
  }

  .model-info {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .model-item {
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
  }

  .model-label {
    font-size: 0.6875rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-secondary);
  }

  .model-value {
    font-size: 0.8125rem;
    font-weight: 500;
    color: var(--text-color);
    font-family: 'Courier New', Courier, monospace;
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
