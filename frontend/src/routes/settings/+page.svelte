<script lang="ts">
  import { onMount } from 'svelte';
  import axiosInstance from '$lib/axios';
  import { authStore, fetchUserInfo } from '$stores/auth';
  import LLMSettings from '$components/settings/LLMSettings.svelte';
  import PromptSettings from '$components/settings/PromptSettings.svelte';
  import AudioExtractionSettings from '$components/settings/AudioExtractionSettings.svelte';
  import { UserSettingsApi, RecordingSettingsHelper, type RecordingSettings } from '$lib/api/userSettings';

  // Form data
  let fullName = '';
  let email = '';
  let currentPassword = '';
  let newPassword = '';
  let confirmPassword = '';
  
  // Form state
  let loading = false;
  let success = '';
  let error = '';
  let profileChanged = false;
  let passwordChanged = false;
  
  // Password visibility toggles
  let showCurrentPassword = false;
  let showNewPassword = false;
  let showConfirmPassword = false;

  // Recording settings - now persisted in database instead of localStorage
  let maxRecordingDuration = 120; // minutes (default 2 hours)
  let recordingQuality = 'high'; // 'standard', 'high', 'maximum'
  let autoStopEnabled = true;
  let recordingSettingsChanged = false;
  let recordingSettingsLoading = false; // Loading state for API operations
  
  // Tab management
  let activeTab = 'profile';
  const tabs = [
    { id: 'profile', label: 'Profile' },
    { id: 'password', label: 'Password' },
    { id: 'recording', label: 'Recording' },
    { id: 'audio-extraction', label: 'Audio Extraction' },
    { id: 'ai-prompts', label: 'AI Prompts' },
    { id: 'llm-provider', label: 'LLM Provider' }
  ];
  
  onMount(() => {
    // Initialize form data
    if ($authStore.user) {
      fullName = $authStore.user.full_name || '';
      email = $authStore.user.email || '';
    }
    loadRecordingSettings();
  });
  
  // Handle tab changes
  function switchTab(tabId: string) {
    activeTab = tabId;
    // Clear messages when switching tabs
    success = '';
    error = '';
  }
  
  // Handle AI settings changes
  function onAISettingsChange() {
    // This can be used to refresh data or show notifications
    // Currently just clearing any existing messages
    success = '';
    error = '';
  }
  
  // Update profile info
  async function updateProfile() {
    loading = true;
    error = '';
    success = '';
    
    try {
      const response = await axiosInstance.put('/users/me', {
        full_name: fullName
      });
      
      // Update store with new user info
      authStore.setUser(response.data);
      
      // Also update localStorage directly for immediate consistency
      localStorage.setItem('user', JSON.stringify(response.data));
      
      success = 'Profile updated successfully';
      profileChanged = false;

      // Force a refresh of all user data to ensure UI consistency
      await fetchUserInfo();
    } catch (err) {
      console.error('Error updating profile:', err);
      const error_obj = err as any;
      error = error_obj.response?.data?.detail || 'Failed to update profile';
    } finally {
      loading = false;
    }
  }
  
  // Change password
  async function changePassword() {
    // Validate passwords
    if (newPassword !== confirmPassword) {
      error = 'New passwords do not match';
      return;
    }
    
    if (newPassword.length < 8) {
      error = 'Password must be at least 8 characters long';
      return;
    }
    
    loading = true;
    error = '';
    success = '';
    
    try {
      // The password change uses the main user update endpoint
      await axiosInstance.put('/users/me', {
        password: newPassword,
        current_password: currentPassword
      });
      
      success = 'Password changed successfully';
      currentPassword = '';
      newPassword = '';
      confirmPassword = '';
      passwordChanged = false;
    } catch (err) {
      console.error('Error changing password:', err);
      const error_obj = err as any;
      error = error_obj.response?.data?.detail || 'Failed to change password';
    } finally {
      loading = false;
    }
  }
  
  // Check for changes in profile form
  $: profileChanged = !!($authStore.user && 
     ($authStore.user.full_name !== fullName));
  
  // Check for changes in password form
  $: passwordChanged = !!(currentPassword && newPassword && confirmPassword);
  
  // Password visibility toggle functions
  function toggleCurrentPasswordVisibility() {
    showCurrentPassword = !showCurrentPassword;
  }
  
  function toggleNewPasswordVisibility() {
    showNewPassword = !showNewPassword;
  }
  
  function toggleConfirmPasswordVisibility() {
    showConfirmPassword = !showConfirmPassword;
  }

  // Load recording settings from database
  async function loadRecordingSettings() {
    recordingSettingsLoading = true;
    error = '';
    
    try {
      // Load from database
      const settings = await UserSettingsApi.getRecordingSettings();
      maxRecordingDuration = settings.max_recording_duration;
      recordingQuality = settings.recording_quality;
      autoStopEnabled = settings.auto_stop_enabled;
      
    } catch (err) {
      console.warn('Error loading recording settings from database:', err);
      // Fall back to defaults
      maxRecordingDuration = 120;
      recordingQuality = 'high';
      autoStopEnabled = true;
    } finally {
      recordingSettingsLoading = false;
    }
  }

  // Save recording settings to database
  async function saveRecordingSettings() {
    recordingSettingsLoading = true;
    error = '';
    
    const settingsToSave = {
      max_recording_duration: maxRecordingDuration,
      recording_quality: recordingQuality,
      auto_stop_enabled: autoStopEnabled
    };
    
    // Validate settings client-side
    const validationErrors = RecordingSettingsHelper.validateSettings(settingsToSave);
    if (validationErrors.length > 0) {
      error = validationErrors[0]; // Show first error
      recordingSettingsLoading = false;
      return;
    }
    
    try {
      const updatedSettings = await UserSettingsApi.updateRecordingSettings(settingsToSave);
      
      // Update local state with server response
      maxRecordingDuration = updatedSettings.max_recording_duration;
      recordingQuality = updatedSettings.recording_quality;
      autoStopEnabled = updatedSettings.auto_stop_enabled;
      
      recordingSettingsChanged = false;
      success = 'Recording settings saved successfully';
      
      // Clear success message after 3 seconds
      setTimeout(() => {
        success = '';
      }, 3000);
      
    } catch (err) {
      console.error('Error saving recording settings:', err);
      const errorObj = err as any;
      error = errorObj.response?.data?.detail || 'Failed to save recording settings';
    } finally {
      recordingSettingsLoading = false;
    }
  }

  // Track recording settings changes
  function onRecordingSettingChange() {
    recordingSettingsChanged = true;
    success = '';
    error = '';
  }
</script>

<div class="settings-container">
  <h1>User Settings</h1>
  
  <!-- Tab Navigation -->
  <div class="tabs">
    <button 
      class="tab-button {activeTab === 'profile' ? 'active' : ''}"
      on:click={() => switchTab('profile')}
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
        <circle cx="12" cy="7" r="4"></circle>
      </svg>
      Profile
    </button>
    <button 
      class="tab-button {activeTab === 'password' ? 'active' : ''}"
      on:click={() => switchTab('password')}
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
        <circle cx="12" cy="16" r="1"></circle>
        <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
      </svg>
      Password
    </button>
    <button 
      class="tab-button {activeTab === 'recording' ? 'active' : ''}"
      on:click={() => switchTab('recording')}
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 1a4 4 0 0 0-4 4v7a4 4 0 0 0 8 0V5a4 4 0 0 0-4-4z"></path>
        <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
        <line x1="12" y1="19" x2="12" y2="23"></line>
        <line x1="8" y1="23" x2="16" y2="23"></line>
      </svg>
      Recording
    </button>
    <button
      class="tab-button {activeTab === 'audio-extraction' ? 'active' : ''}"
      on:click={() => switchTab('audio-extraction')}
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M9 18V5l12-2v13"></path>
        <circle cx="6" cy="18" r="3"></circle>
        <circle cx="18" cy="16" r="3"></circle>
      </svg>
      Audio Extraction
    </button>
    <button
      class="tab-button {activeTab === 'ai-prompts' ? 'active' : ''}"
      on:click={() => switchTab('ai-prompts')}
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
      </svg>
      AI Prompts
    </button>
    <button 
      class="tab-button {activeTab === 'llm-provider' ? 'active' : ''}"
      on:click={() => switchTab('llm-provider')}
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect>
        <line x1="8" y1="21" x2="16" y2="21"></line>
        <line x1="12" y1="17" x2="12" y2="21"></line>
      </svg>
      LLM Provider
    </button>
  </div>
  
  <!-- Tab Content -->
  <div class="tab-content">
    {#if activeTab === 'profile'}
      <div class="settings-section">
        <h2>Profile Information</h2>
        
        {#if success}
          <div class="success-message">
            {success}
          </div>
        {/if}
        
        {#if error}
          <div class="error-message">
            {error}
          </div>
        {/if}
    
    <form on:submit|preventDefault={updateProfile} class="settings-form">
      <div class="form-group">
        <label for="email">Email</label>
        <input 
          type="email" 
          id="email" 
          value={email} 
          disabled 
          class="form-control"
          title="Your email address cannot be changed after account creation"
        />
        <p class="form-text">Email cannot be changed</p>
      </div>
      
      <div class="form-group">
        <label for="fullName">Full Name</label>
        <input 
          type="text" 
          id="fullName" 
          bind:value={fullName} 
          class="form-control"
          title="Enter your full name as you want it to appear in the application"
        />
      </div>
      
      <div class="form-actions">
        <button 
          type="submit" 
          class="button primary-button" 
          disabled={loading || !profileChanged}
          title="Save changes to your profile information"
        >
          {loading ? 'Saving...' : 'Save Changes'}
        </button>
        </div>
      </form>
      </div>
    {/if}
    
    {#if activeTab === 'password'}
      <div class="settings-section">
        <h2>Change Password</h2>
        
        {#if success}
          <div class="success-message">
            {success}
          </div>
        {/if}
        
        {#if error}
          <div class="error-message">
            {error}
          </div>
        {/if}
        
        <form on:submit|preventDefault={changePassword} class="settings-form">
      <div class="form-group">
        <div class="password-header">
          <label for="currentPassword">Current Password</label>
          <button 
            type="button" 
            class="toggle-password" 
            on:click={toggleCurrentPasswordVisibility}
            aria-label={showCurrentPassword ? 'Hide current password' : 'Show current password'}
            title={showCurrentPassword ? 'Hide current password text' : 'Show current password text'}
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
        {#if showCurrentPassword}
          <input 
            type="text" 
            id="currentPassword" 
            bind:value={currentPassword} 
            class="form-control"
            title="Enter your current password to verify your identity"
          />
        {:else}
          <input 
            type="password" 
            id="currentPassword" 
            bind:value={currentPassword} 
            class="form-control"
            title="Enter your current password to verify your identity"
          />
        {/if}
      </div>
      
      <div class="form-group">
        <div class="password-header">
          <label for="newPassword">New Password</label>
          <button 
            type="button" 
            class="toggle-password" 
            on:click={toggleNewPasswordVisibility}
            aria-label={showNewPassword ? 'Hide new password' : 'Show new password'}
            title={showNewPassword ? 'Hide new password text' : 'Show new password text'}
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
        {#if showNewPassword}
          <input 
            type="text" 
            id="newPassword" 
            bind:value={newPassword} 
            class="form-control"
            title="Enter a new password (must be at least 8 characters long)"
          />
        {:else}
          <input 
            type="password" 
            id="newPassword" 
            bind:value={newPassword} 
            class="form-control"
            title="Enter a new password (must be at least 8 characters long)"
          />
        {/if}
        <p class="form-text">Must be at least 8 characters long</p>
      </div>
      
      <div class="form-group">
        <div class="password-header">
          <label for="confirmPassword">Confirm New Password</label>
          <button 
            type="button" 
            class="toggle-password" 
            on:click={toggleConfirmPasswordVisibility}
            aria-label={showConfirmPassword ? 'Hide confirm password' : 'Show confirm password'}
            title={showConfirmPassword ? 'Hide confirm password text' : 'Show confirm password text'}
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
        {#if showConfirmPassword}
          <input 
            type="text" 
            id="confirmPassword" 
            bind:value={confirmPassword} 
            class="form-control"
            title="Re-enter your new password to confirm it matches"
          />
        {:else}
          <input 
            type="password" 
            id="confirmPassword" 
            bind:value={confirmPassword} 
            class="form-control"
            title="Re-enter your new password to confirm it matches"
          />
        {/if}
      </div>
      
      <div class="form-actions">
        <button 
          type="submit" 
          class="button primary-button" 
          disabled={loading || !passwordChanged}
          title="Change your account password to the new password"
        >
          {loading ? 'Changing...' : 'Change Password'}
        </button>
        </div>
      </form>
      </div>
    {/if}
    
    {#if activeTab === 'recording'}
      <div class="settings-section">
        <h2>Recording Settings</h2>
        
        {#if success}
          <div class="success-message">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
            {success}
          </div>
        {/if}
        
        {#if error}
          <div class="error-message">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="8" x2="12" y2="12"></line>
              <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
            {error}
          </div>
        {/if}
        
        <div class="form-group">
          <label for="maxRecordingDuration">Maximum Recording Duration</label>
          <select 
            id="maxRecordingDuration" 
            bind:value={maxRecordingDuration}
            on:change={onRecordingSettingChange}
            class="form-control"
            title="Set the maximum duration for audio recordings"
          >
            <option value={15}>15 minutes</option>
            <option value={30}>30 minutes</option>
            <option value={60}>1 hour</option>
            <option value={120}>2 hours</option>
            <option value={240}>4 hours</option>
            <option value={480}>8 hours</option>
          </select>
          <small class="form-text">Maximum recording length. Recordings will be automatically stopped when this limit is reached (if auto-stop is enabled below).</small>
        </div>

        <div class="form-group">
          <label for="recordingQuality">Audio Quality</label>
          <select 
            id="recordingQuality" 
            bind:value={recordingQuality}
            on:change={onRecordingSettingChange}
            class="form-control"
            title="Choose the audio quality for recordings"
          >
            <option value="standard">Standard (64 kbps)</option>
            <option value="high">High (128 kbps)</option>
            <option value="maximum">Maximum (256 kbps)</option>
          </select>
          <small class="form-text">Higher quality settings produce larger files but better audio.</small>
        </div>

        <div class="form-group">
          <div class="toggle-group">
            <div class="toggle-header">
              <label for="autoStopEnabled" class="toggle-label">
                <span class="label-text">Automatically stop at maximum duration</span>
                <span class="label-description">
                  When enabled, recordings will be automatically stopped when the maximum duration is reached. When disabled, you can record beyond the limit but will need to manually stop.
                </span>
              </label>
              <label class="toggle-switch">
                <input
                  type="checkbox"
                  id="autoStopEnabled"
                  bind:checked={autoStopEnabled}
                  on:change={onRecordingSettingChange}
                  title="Automatically stop recording at the maximum duration"
                />
                <span class="toggle-slider"></span>
              </label>
            </div>
          </div>
        </div>

        <div class="form-actions">
          <button 
            type="button" 
            on:click={saveRecordingSettings}
            disabled={!recordingSettingsChanged || recordingSettingsLoading}
            class="button primary-button"
            title="Save your recording preferences"
          >
            {#if recordingSettingsLoading}
              Saving...
            {:else}
              Save Recording Settings
            {/if}
          </button>
        </div>
      </div>
    {/if}

    {#if activeTab === 'audio-extraction'}
      <div class="settings-section">
        <AudioExtractionSettings />
      </div>
    {/if}

    {#if activeTab === 'ai-prompts'}
      <div class="settings-section">
        <PromptSettings onSettingsChange={onAISettingsChange} />
      </div>
    {/if}

    {#if activeTab === 'llm-provider'}
      <div class="settings-section">
        <LLMSettings onSettingsChange={onAISettingsChange} />
      </div>
    {/if}
  </div>
</div>

<style>
  .settings-container {
    max-width: 1000px;
    margin: 0 auto;
    padding: 1rem;
  }

  .tabs {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 2rem;
  }

  .tab-button {
    color: var(--text-color);
    background: none;
    border: none;
    padding: 0.5rem 1rem;
    border-radius: 6px;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-family: inherit;
    font-size: 1rem;
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
  }

  .tab-content {
    min-height: 400px;
  }
  
  h1 {
    font-size: 1.5rem;
    margin-bottom: 1.5rem;
    color: var(--text-color);
  }
  
  .settings-section {
    background-color: var(--surface-color);
    border-radius: 8px;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  }
  
  h2 {
    font-size: 1.2rem;
    margin-top: 0;
    margin-bottom: 1.5rem;
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
    gap: 0.5rem;
    margin-bottom: 1.5rem;
  }

  .form-group:last-of-type {
    margin-bottom: 1rem;
  }

  .password-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.5rem;
  }
  
  .toggle-password {
    background: none;
    border: none;
    cursor: pointer;
    padding: 4px;
    color: var(--text-light);
    display: flex;
    align-items: center;
    border-radius: 4px;
    transition: background-color 0.2s;
  }
  
  .toggle-password:hover {
    background-color: var(--surface-hover, rgba(0, 0, 0, 0.05));
  }
  
  label {
    font-weight: 500;
    font-size: 0.9rem;
  }
  
  .form-control {
    padding: 0.75rem;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    font-size: 0.9rem;
    background-color: var(--background-color);
    color: var(--text-color);
    width: 100%;
  }
  
  .form-control:disabled {
    background-color: rgba(0, 0, 0, 0.05);
    color: var(--text-light);
  }
  
  .form-text {
    font-size: 0.8rem;
    color: var(--text-light);
    margin: 0.25rem 0 0;
  }

  /* Toggle Switch Styles */
  .toggle-group {
    padding: 1rem;
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    transition: all 0.2s ease;
  }

  .toggle-group:hover {
    border-color: var(--primary-color);
  }

  .toggle-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
  }

  .toggle-label {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    cursor: pointer;
  }

  .label-text {
    font-weight: 500;
    color: var(--text-color);
    font-size: 0.9rem;
  }

  .label-description {
    font-size: 0.8rem;
    color: var(--text-light);
    line-height: 1.4;
    font-weight: 400;
  }

  .toggle-switch {
    position: relative;
    display: inline-block;
    width: 48px;
    height: 24px;
    flex-shrink: 0;
    cursor: pointer;
  }

  .toggle-switch input {
    opacity: 0;
    width: 0;
    height: 0;
  }

  .toggle-slider {
    position: absolute;
    cursor: pointer;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: var(--border-color);
    transition: 0.3s;
    border-radius: 24px;
  }

  .toggle-slider:before {
    position: absolute;
    content: "";
    height: 18px;
    width: 18px;
    left: 3px;
    bottom: 3px;
    background-color: white;
    transition: 0.3s;
    border-radius: 50%;
  }

  input:checked + .toggle-slider {
    background-color: var(--primary-color);
  }

  input:checked + .toggle-slider:before {
    transform: translateX(24px);
  }

  .form-actions {
    display: flex;
    justify-content: flex-end;
    margin-top: 1rem;
  }
  
  .button {
    padding: 0.6rem 1.2rem;
    border-radius: 10px;
    font-size: 0.95rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    border: 1px solid var(--border-color);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }
  
  .button:hover:not(:disabled),
  .button:focus:not(:disabled) {
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
    text-decoration: none !important;
  }
  
  .button:active:not(:disabled) {
    transform: translateY(0);
  }
  
  .primary-button {
    background-color: #3b82f6; /* Use explicit color instead of variable */
    color: white !important; /* Force white text */
    border: none;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }
  
  .primary-button:hover:not(:disabled),
  .primary-button:focus:not(:disabled) {
    background-color: #2563eb; /* Darker blue on hover */
    color: white !important;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }
  
  .primary-button:disabled {
    background-color: var(--primary-light);
    cursor: not-allowed;
  }
  
  .success-message {
    background-color: rgba(16, 185, 129, 0.1);
    color: var(--success-color);
    padding: 0.75rem;
    border-radius: 4px;
    margin-bottom: 1rem;
  }
  
  .error-message {
    background-color: rgba(239, 68, 68, 0.1);
    color: var(--error-color);
    padding: 0.75rem;
    border-radius: 4px;
    margin-bottom: 1rem;
  }
  
  .checkbox-wrapper {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .checkbox-wrapper input[type="checkbox"] {
    width: 18px;
    height: 18px;
    cursor: pointer;
  }

  .checkbox-wrapper label {
    margin: 0;
    cursor: pointer;
    font-weight: 500;
  }

  /* Dark mode adjustments */
  :global([data-theme='dark']) .toggle-slider:before {
    background-color: #e5e7eb;
  }

  @media (max-width: 768px) {
    .tab-button {
      padding: 0.6rem 1rem;
      font-size: 0.8rem;
      flex-shrink: 0;
    }

    .tab-content {
      min-height: 300px;
    }

    .toggle-header {
      flex-direction: column;
    }
  }

  @media (min-width: 769px) {
    .settings-container {
      padding: 2rem;
    }
  }
</style>
