<script lang="ts">
  import { useNavigate, Link } from "svelte-navigator";
  import { login, authStore, isAuthenticated } from "../stores/auth";
  import { onMount } from 'svelte';
  
  // Import logo asset for proper Vite processing
  import logoBanner from '../assets/logo-banner.png';
  
  // Explicitly declare props to prevent warnings
  export const location = null;
  export const navigate = null;
  const navigateHook = useNavigate();
  
  // Form data
  let email = "";
  let password = "";
  let error = "";
  let loading = false;
  let formSubmitted = false;
  let showPassword = false;
  let successMessage = "";
  
  // Validation
  let emailValid = true;
  let passwordValid = true;
  
  // Focus the email field on mount
  onMount(() => {
    const emailInput = document.getElementById('email');
    if (emailInput) emailInput.focus();
  });
  
  // Validate email format
  /**
   * Validates an email address format
   * @param {string} email - The email address to validate
   * @returns {boolean} True if the email is valid, false otherwise
   */
  function validateEmail(email: string) {
    const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return regex.test(String(email).toLowerCase());
  }
  
  // Check form validity
  function validateForm() {
    formSubmitted = true;
    emailValid = email.trim() !== '' && validateEmail(email);
    passwordValid = password.trim() !== '';
    
    return emailValid && passwordValid;
  }
  
  // Handle form submission
  async function handleSubmit() {
    error = "";
    successMessage = "";
    
    // Validate required fields first
    if (!email.trim()) {
      error = "Email address is required.";
      document.getElementById('email')?.focus();
      return;
    }
    
    if (!validateEmail(email.trim())) {
      error = "Please enter a valid email address.";
      document.getElementById('email')?.focus();
      return;
    }
    
    if (!password.trim()) {
      error = "Password is required.";
      document.getElementById('password')?.focus();
      return;
    }
    
    if (!validateForm()) {
      return;
    }
    
    loading = true;
    
    try {
      // Call the login function from our auth store
      const result = await login(email.trim(), password);
      
      if (result.success) {
        successMessage = "Login successful! Redirecting...";
        
        // Add a small delay before redirecting for better UX
        setTimeout(() => {
          // Use window.location for a full page refresh to ensure auth state is properly loaded
          window.location.href = "/";
        }, 1000);
      } else {
        console.error('Login.svelte: Login failed:', result.message);
        error = result.message || "Login failed. Please check your credentials and try again.";
        
        // Focus appropriate field based on error type
        if (result.message && result.message.toLowerCase().includes('email')) {
          document.getElementById('email')?.focus();
        } else if (result.message && (result.message.toLowerCase().includes('password') || result.message.toLowerCase().includes('credentials'))) {
          document.getElementById('password')?.focus();
          // Clear password on failed authentication for security
          password = "";
        }
      }
    } catch (err) {
      console.error("Login.svelte: Login error:", err);
      error = "An unexpected error occurred. Please try again later.";
    } finally {
      loading = false;
    }
  }
  
  // Toggle password visibility
  function togglePasswordVisibility() {
    showPassword = !showPassword;
  }
</script>

<div class="auth-container">
  <div class="auth-card">
    <div class="auth-header">
      <div class="auth-logo">
        <img src={logoBanner} alt="OpenTranscribe" class="logo-banner" />
      </div>
      <h1>Login</h1>
      <p>Sign in to your account</p>
    </div>
    
    <form on:submit|preventDefault={handleSubmit} class="auth-form">
      {#if error}
        <div class="error-message" role="alert" aria-live="polite">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="10"/>
            <line x1="15" y1="9" x2="9" y2="15"/>
            <line x1="9" y1="9" x2="15" y2="15"/>
          </svg>
          <span>{error}</span>
        </div>
      {/if}
      
      {#if successMessage}
        <div class="success-message" role="alert" aria-live="polite">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <polyline points="20,6 9,17 4,12"/>
          </svg>
          <span>{successMessage}</span>
        </div>
      {/if}
      
      <div class="form-group {!emailValid && formSubmitted ? 'has-error' : ''}">
        <label for="email">Email</label>
        <input 
          type="email" 
          id="email" 
          bind:value={email} 
          placeholder="Enter your email"
          aria-invalid={!emailValid && formSubmitted}
          autocomplete="email"
          title="Enter the email address associated with your account"
        />
        {#if !emailValid && formSubmitted}
          <div class="field-error">Please enter a valid email address</div>
        {/if}
      </div>
      
      <div class="form-group {!passwordValid && formSubmitted ? 'has-error' : ''}">
        <div class="password-header">
          <label for="password">Password</label>
          <button 
            type="button" 
            class="toggle-password" 
            on:click={togglePasswordVisibility}
            aria-label={showPassword ? 'Hide password' : 'Show password'}
            title={showPassword ? 'Hide password text' : 'Show password text'}
          >
            {#if showPassword}
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
        {#if showPassword}
          <input 
            type="text"
            id="password" 
            bind:value={password} 
            placeholder="Enter your password"
            aria-invalid={!passwordValid && formSubmitted}
            autocomplete="current-password"
            title="Enter your account password"
          />
        {:else}
          <input 
            type="password"
            id="password" 
            bind:value={password} 
            placeholder="Enter your password"
            aria-invalid={!passwordValid && formSubmitted}
            autocomplete="current-password"
            title="Enter your account password"
          />
        {/if}
        {#if !passwordValid && formSubmitted}
          <div class="field-error">Password is required</div>
        {/if}
      </div>
      
      <button 
        type="submit" 
        class="auth-button" 
        disabled={loading}
        title="Sign in to your OpenTranscribe account"
      >
        {#if loading}
          <span class="spinner"></span> Signing In...
        {:else}
          Sign In
        {/if}
      </button>
    </form>
    
    <div class="auth-links">
      <Link 
        to="/register" 
        class="auth-link"
        title="Create a new OpenTranscribe account"
      >Need an account? Register</Link>
    </div>
  </div>
</div>

<style>
  .auth-container {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 100vh;
    padding: 1rem;
    background-color: var(--background-color);
  }
  
  .auth-card {
    background-color: var(--surface-color);
    border-radius: 8px;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    width: 100%;
    max-width: 400px;
    padding: 2rem;
  }
  
  .auth-header {
    text-align: center;
    margin-bottom: 2rem;
  }
  
  .auth-header h1 {
    font-size: 1.5rem;
    color: var(--text-color);
    margin-bottom: 0.5rem;
  }
  
  .auth-header p {
    color: var(--text-light);
    font-size: 0.9rem;
  }
  
  .auth-form {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
  }
  
  .form-group {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  
  .form-group label {
    font-size: 0.9rem;
    font-weight: 500;
  }
  
  .form-group input {
    padding: 0.75rem 1rem;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    font-size: 1rem;
    transition: border-color 0.2s;
  }
  
  .form-group input:focus {
    outline: none;
    border-color: var(--primary-color);
  }
  
  .auth-button {
    background-color: #3b82f6;
    color: white;
    border: none;
    border-radius: 10px;
    padding: 0.6rem 1.2rem;
    font-size: 0.95rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
  }
  
  .auth-button:hover:not(:disabled) {
    background-color: #2563eb;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }
  
  .auth-button:active:not(:disabled) {
    transform: translateY(0);
  }
  
  .auth-button:disabled {
    background-color: var(--border-color);
    cursor: not-allowed;
  }
  
  
  .auth-links {
    margin-top: 1.5rem;
    text-align: center;
    color: var(--text-light);
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
  
  .field-error {
    color: var(--error-color);
    font-size: 0.85rem;
    margin-top: 0.25rem;
  }
  
  .has-error input {
    border-color: var(--error-color);
  }
  
  .success-message {
    background-color: var(--success-color-light);
    color: var(--success-color);
    padding: 0.75rem;
    border-radius: 4px;
    border: 1px solid rgba(34, 197, 94, 0.2);
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-weight: 500;
  }
  
  .success-message svg {
    flex-shrink: 0;
    opacity: 0.8;
  }
  
  .spinner {
    display: inline-block;
    width: 1rem;
    height: 1rem;
    border: 2px solid rgba(255, 255, 255, 0.3);
    border-radius: 50%;
    border-top-color: #fff;
    animation: spin 1s ease-in-out infinite;
    margin-right: 0.5rem;
  }
  
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  
  .error-message {
    background-color: rgba(239, 68, 68, 0.1);
    color: var(--error-color);
    padding: 0.75rem;
    border-radius: 4px;
    border: 1px solid rgba(239, 68, 68, 0.2);
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-weight: 500;
  }
  
  .error-message svg {
    flex-shrink: 0;
    opacity: 0.8;
  }
  
  .auth-logo {
    text-align: center;
    margin-bottom: 1.5rem;
  }
  
  .auth-logo .logo-banner {
    height: 60px;
    width: auto;
    object-fit: contain;
    border-radius: 8px;
  }
</style>
