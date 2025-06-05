<script>
  import { useNavigate } from "svelte-navigator";
  import { register, login } from "../stores/auth";
  
  // Import logo asset for proper Vite processing
  import logoBanner from '../assets/logo-banner.png';
  
  // Explicitly declare props to prevent warnings
  export let location = null;
  export let navigate = null;
  const navigateHook = useNavigate();
  
  // Form data
  let username = "";
  let email = "";
  let password = "";
  let confirmPassword = "";
  let error = "";
  let loading = false;
  
  // Validate form
  function validateForm() {
    if (!username || !email || !password || !confirmPassword) {
      error = "All fields are required";
      return false;
    }
    
    if (password !== confirmPassword) {
      error = "Passwords do not match";
      return false;
    }
    
    if (password.length < 8) {
      error = "Password must be at least 8 characters long";
      return false;
    }
    
    // Simple email validation
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      error = "Please enter a valid email address";
      return false;
    }
    
    return true;
  }
  
  // Handle form submission
  async function handleSubmit() {
    error = "";
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
          navigateHook("/");
        } else {
          error = "Registration successful, but login failed. Please try logging in manually.";
        }
      } else {
        error = result.message || "Registration failed. Please try again.";
      }
    } catch (err) {
      console.error("Registration error:", err);
      error = "An unexpected error occurred. Please try again.";
    } finally {
      loading = false;
    }
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
      {#if error}
        <div class="error-message">
          {error}
        </div>
      {/if}
      
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
        <label for="password">Password</label>
        <input
          id="password"
          type="password"
          bind:value={password}
          placeholder="Choose a password"
          disabled={loading}
          title="Choose a secure password (minimum 8 characters)"
        />
      </div>
      
      <div class="form-group">
        <label for="confirmPassword">Confirm Password</label>
        <input
          id="confirmPassword"
          type="password"
          bind:value={confirmPassword}
          placeholder="Confirm your password"
          disabled={loading}
          title="Re-enter your password to confirm it matches"
        />
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
  
  .auth-footer {
    text-align: center;
    font-size: 0.9rem;
    color: var(--text-light);
  }
  
  .error-message {
    background-color: rgba(239, 68, 68, 0.1);
    color: var(--error-color);
    padding: 0.75rem;
    border-radius: 4px;
    font-size: 0.9rem;
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
