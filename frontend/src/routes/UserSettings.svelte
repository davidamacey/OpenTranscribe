<script lang="ts">
  import { onMount } from 'svelte';
  import axios from 'axios';
  import axiosInstance from '../lib/axios';
  import { authStore, fetchUserInfo } from '../stores/auth';
  
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
  
  onMount(() => {
    // Initialize form data
    if ($authStore.user) {
      fullName = $authStore.user.full_name || '';
      email = $authStore.user.email || '';
    }
  });
  
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
</script>

<div class="settings-container">
  <h1>User Settings</h1>
  
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
  
  <div class="settings-section">
    <h2>Profile Information</h2>
    
    <form on:submit|preventDefault={updateProfile} class="settings-form">
      <div class="form-group">
        <label for="email">Email</label>
        <input 
          type="email" 
          id="email" 
          value={email} 
          disabled 
          class="form-control"
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
        />
      </div>
      
      <div class="form-actions">
        <button 
          type="submit" 
          class="button primary-button" 
          disabled={loading || !profileChanged}
        >
          {loading ? 'Saving...' : 'Save Changes'}
        </button>
      </div>
    </form>
  </div>
  
  <div class="settings-section">
    <h2>Change Password</h2>
    
    <form on:submit|preventDefault={changePassword} class="settings-form">
      <div class="form-group">
        <label for="currentPassword">Current Password</label>
        <input 
          type="password" 
          id="currentPassword" 
          bind:value={currentPassword} 
          class="form-control"
        />
      </div>
      
      <div class="form-group">
        <label for="newPassword">New Password</label>
        <input 
          type="password" 
          id="newPassword" 
          bind:value={newPassword} 
          class="form-control"
        />
        <p class="form-text">Must be at least 8 characters long</p>
      </div>
      
      <div class="form-group">
        <label for="confirmPassword">Confirm New Password</label>
        <input 
          type="password" 
          id="confirmPassword" 
          bind:value={confirmPassword} 
          class="form-control"
        />
      </div>
      
      <div class="form-actions">
        <button 
          type="submit" 
          class="button primary-button" 
          disabled={loading || !passwordChanged}
        >
          {loading ? 'Changing...' : 'Change Password'}
        </button>
      </div>
    </form>
  </div>
</div>

<style>
  .settings-container {
    max-width: 800px;
    margin: 0 auto;
    padding: 1rem;
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
  
  @media (min-width: 768px) {
    .settings-container {
      padding: 2rem;
    }
  }
</style>
