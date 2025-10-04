<script lang="ts">
  import { useNavigate } from "svelte-navigator";
  import { register, login } from "../stores/auth";
  import { toastStore } from '../stores/toast';

  // Import logo asset for proper Vite processing
  import logoBanner from '../assets/logo-banner.png';

  // Explicitly declare props to prevent warnings
  export const location = null;
  export const navigate = null;
  const navigateHook = useNavigate();

  // Form data
  let username = "";
  let email = "";
  let password = "";
  let confirmPassword = "";
  let loading = false;
  let showPassword = false;
  let showConfirmPassword = false;
  
  // Validate form
  function validateForm() {
    if (!username || !email || !password || !confirmPassword) {
      toastStore.error("All fields are required");
      return false;
    }

    if (password !== confirmPassword) {
      toastStore.error("Passwords do not match");
      return false;
    }

    if (password.length < 8) {
      toastStore.error("Password must be at least 8 characters long");
      return false;
    }

    // Simple email validation
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      toastStore.error("Please enter a valid email address");
      return false;
    }

    return true;
  }

  // Handle form submission
  async function handleSubmit() {
    loading = true;

    if (!validateForm()) {
      loading = false;
      return;
    }

    try {
      // Make sure we're using the right parameters in the right order:
      // register(email, fullName, password) is expected by our auth store
      const result = await register(email, username, password);

      if (result.success) {
        // Log the user in automatically after registration
        const loginResult = await login(email, password);
        if (loginResult.success) {
          toastStore.success("Registration successful! Redirecting...");
          navigateHook("/");
        } else {
          toastStore.error("Registration successful, but login failed. Please try logging in manually.");
        }
      } else {
        toastStore.error(result.message || "Registration failed. Please try again.");
      }
    } catch (err) {
      console.error("Registration error:", err);
      toastStore.error("An unexpected error occurred. Please try again.");
    } finally {
      loading = false;
    }
  }
  
  // Toggle password visibility
  function togglePasswordVisibility() {
    showPassword = !showPassword;
  }
  
  function toggleConfirmPasswordVisibility() {
    showConfirmPassword = !showConfirmPassword;
  }
</script>

<div class="auth-container">
  <div class="auth-card">
    <div class="auth-header">
      <div class="auth-logo">
        <img src={logoBanner} alt="OpenTranscribe" class="logo-banner" />
      </div>
      <h1>Register</h1>
      <p>Create a new account</p>
    </div>
    
    <form on:submit|preventDefault={handleSubmit} class="auth-form">
      <div class="form-group">
        <label for="username">Username</label>
        <input
          id="username"
          type="text"
          bind:value={username}
          placeholder="Choose a username"
          disabled={loading}
          title="Enter a unique username for your account"
        />
      </div>
      
      <div class="form-group">
        <label for="email">Email</label>
        <input
          id="email"
          type="email"
          bind:value={email}
          placeholder="Enter your email"
          disabled={loading}
          title="Enter a valid email address for your account"
        />
      </div>
      
      <div class="form-group">
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
            id="password"
            type="text"
            bind:value={password}
            placeholder="Choose a password"
            disabled={loading}
            title="Choose a secure password (minimum 8 characters)"
          />
        {:else}
          <input
            id="password"
            type="password"
            bind:value={password}
            placeholder="Choose a password"
            disabled={loading}
            title="Choose a secure password (minimum 8 characters)"
          />
        {/if}
      </div>
      
      <div class="form-group">
        <div class="password-header">
          <label for="confirmPassword">Confirm Password</label>
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
            id="confirmPassword"
            type="text"
            bind:value={confirmPassword}
            placeholder="Confirm your password"
            disabled={loading}
            title="Re-enter your password to confirm it matches"
          />
        {:else}
          <input
            id="confirmPassword"
            type="password"
            bind:value={confirmPassword}
            placeholder="Confirm your password"
            disabled={loading}
            title="Re-enter your password to confirm it matches"
          />
        {/if}
      </div>
      
      <button 
        type="submit" 
        class="auth-button" 
        disabled={loading}
        title="Create your new OpenTranscribe account"
      >
        {loading ? "Creating account..." : "Create Account"}
      </button>
      
      <div class="auth-footer">
        <p>
          Already have an account? <a 
            href="/login" 
            class="auth-link"
            title="Sign in to your existing OpenTranscribe account"
          >Login</a>
        </p>
      </div>
    </form>
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
  
  .auth-footer {
    text-align: center;
    font-size: 0.9rem;
    color: var(--text-light);
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
</style>
