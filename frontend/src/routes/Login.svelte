<script>
  import { useNavigate, Link } from "svelte-navigator";
  import { login, authStore, isAuthenticated } from "../stores/auth";
  import { onMount } from 'svelte';
  
  // Explicitly declare props to prevent warnings
  export let location = null;
  export let navigate = null;
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
  function validateEmail(email) {
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
        <img src="/src/assets/logo-banner.png" alt="OpenTranscribe" class="logo-banner" />
      </div>
      <h1>Login</h1>
      <p>Sign in to your account</p>
      <div class="info-message">
        <p><strong>Default Admin Credentials:</strong></p>
        <p>Email: admin@example.com</p>
        <p>Password: password</p>
      </div>
    </div>
    
    <form on:submit|preventDefault={handleSubmit} class="auth-form">
      {#if error}
        <div class="error-message">
          {error}
        </div>
      {/if}
      
      {#if successMessage}
        <div class="success-message">
          {successMessage}
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
        <label for="password">Password</label>
        <div class="password-container">
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
          <button 
            type="button" 
            class="toggle-password" 
            on:click={togglePasswordVisibility}
            aria-label={showPassword ? 'Hide password' : 'Show password'}
            title={showPassword ? 'Hide password text' : 'Show password text'}
          >
            {showPassword ? '👁️' : '👁️‍🗨️'}
          </button>
        </div>
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
    background-color: var(--primary-color);
    color: white;
    border: none;
    border-radius: 4px;
    padding: 0.75rem 1rem;
    font-size: 1rem;
    font-weight: 500;
    cursor: pointer;
    transition: background-color 0.2s;
  }
  
  .auth-button:hover {
    background-color: var(--primary-dark);
  }
  
  .auth-button:disabled {
    background-color: var(--border-color);
    cursor: not-allowed;
  }
  
  .info-message {
    margin-top: 1.5rem;
    padding: 1rem;
    background-color: rgba(255, 255, 255, 0.1);
    border-radius: 0.5rem;
    font-size: 0.9rem;
  }
  
  .info-message p {
    margin: 0.25rem 0;
  }
  
  .auth-links {
    margin-top: 1.5rem;
    text-align: center;
    color: var(--text-light);
  }
  
  
  .password-container {
    position: relative;
  }
  
  .toggle-password {
    position: absolute;
    right: 10px;
    top: 50%;
    transform: translateY(-50%);
    background: none;
    border: none;
    cursor: pointer;
    font-size: 1.2rem;
    padding: 0;
    color: var(--text-light);
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
    padding: 1rem;
    border-radius: 4px;
    margin-bottom: 1rem;
    font-weight: 500;
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
