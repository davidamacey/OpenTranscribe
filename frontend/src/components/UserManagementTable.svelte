<script>
  import { onMount } from 'svelte';
  import axiosInstance from '../lib/axios';
  import { user } from '../stores/auth';
  
  /**
   * @typedef {Object} User
   * @property {string} id
   * @property {string} username
   * @property {string} email
   * @property {string} role
   * @property {string} created_at
   * @property {string|null} [last_login]
   * @property {boolean} [is_active]
   * @property {string} [full_name]
   */
  
  /** @type {Array<User>} */
  export let users = [];

  /** @type {boolean} */
  export let loading = false;

  /** @type {string|null} */
  export const error = null; // For external reference only

  /** @type {Function} */
  export let onRefresh = () => {};

  /** @type {string} */
  let newUsername = '';

  /** @type {string} */
  let newEmail = '';

  /** @type {string} */
  let newPassword = '';

  /** @type {string} */
  let newRole = 'user';

  /** @type {boolean} */
  let showAddUserForm = false;
  
  /** @type {string} */
  let searchTerm = '';
  
  /** @type {Array<User>} */
  let filteredUsers = [];
  
  /** @type {string|null} */
  let currentUserId = null;
  
  // Subscribe to the user store to get the current user ID
  $: if ($user) {
    currentUserId = $user.id;
  } else {
    currentUserId = null;
  }
  
  /** @type {string|null} */
  let successMessage = null;
  
  /** @type {string|null} */
  let errorMessage = null;

  // Initialize component
  onMount(() => {
    filterUsers();
  });

  /**
   * Filter users based on search term
   */
  function filterUsers() {
    if (!searchTerm.trim()) {
      filteredUsers = [...users];
      return;
    }
    
    const term = searchTerm.toLowerCase();
    filteredUsers = users.filter(user => 
      user.username.toLowerCase().includes(term) ||
      (user.email && user.email.toLowerCase().includes(term)) ||
      (user.full_name && user.full_name.toLowerCase().includes(term))
    );
  }

  /**
   * Create a new user
   */
  async function createUser() {
    if (!newUsername || !newEmail || !newPassword) {
      errorMessage = 'Please fill out all required fields';
      return;
    }
    
    try {
      // The backend expects full_name as a required field
      // Using username as the full_name since that's what we collect
      const response = await axiosInstance.post('/api/admin/users', {
        email: newEmail,
        password: newPassword,
        full_name: newUsername, // Required field
        role: newRole,
        is_active: true,
        is_superuser: newRole === 'admin' // Set superuser based on role
      });
      
      // Add new user to the list and reset form
      newUsername = '';
      newEmail = '';
      newPassword = '';
      newRole = 'user';
      showAddUserForm = false;
      
      successMessage = 'User created successfully';
      
      // Refresh the user list
      onRefresh();
    } catch (err) {
      console.error('Error creating user:', err);
      errorMessage = err instanceof Error ? err.message : 'Failed to create user';
    }
  }

  /**
   * Delete a user
   * @param {string} userId
   */
  async function deleteUser(userId) {
    if (!confirm('Are you sure you want to delete this user? This action cannot be undone.')) {
      return;
    }
    
    try {
      await axiosInstance.delete(`/api/users/${userId}`);
      successMessage = 'User deleted successfully';
      
      // Refresh user list
      onRefresh();
    } catch (err) {
      console.error('Error deleting user:', err);
      errorMessage = err instanceof Error ? err.message : 'Failed to delete user';
    }
  }
  
  /**
   * Update a user's role
   * @param {string} userId
   * @param {string} role
   */
  async function updateUserRole(userId, role) {
    try {
      await axiosInstance.put(`/api/users/${userId}`, { role });
      successMessage = `User role updated to ${role}`;
      
      // Refresh user list
      onRefresh();
    } catch (err) {
      console.error('Error updating user role:', err);
      errorMessage = err instanceof Error ? err.message : 'Failed to update user role';
    }
  }
  
  /**
   * Handle role change event
   * @param {string} userId
   * @param {Event} e
   */
  function handleUserRoleChange(userId, e) {
    if (e.target && 'value' in e.target) {
      updateUserRole(userId, /** @type {HTMLSelectElement} */ (e.target).value);
    }
  }

  /**
   * Process search input
   * @param {Event} e
   */
  function handleSearchInput(e) {
    if (e.target && 'value' in e.target) {
      searchTerm = /** @type {HTMLInputElement} */ (e.target).value;
      filterUsers();
    }
  }

  /**
   * Format date to locale string
   * @param {string} dateString
   * @returns {string}
   */
  function formatDate(dateString) {
    if (!dateString) return 'N/A';
    
    const date = new Date(dateString);
    return date.toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  }
  
  /**
   * Clear any messages
   */
  function clearMessages() {
    successMessage = null;
    errorMessage = null;
  }
  
  /**
   * Toggle add user form
   */
  function toggleAddUserForm() {
    showAddUserForm = !showAddUserForm;
    // Reset form when toggling
    if (showAddUserForm) {
      newUsername = '';
      newEmail = '';
      newPassword = '';
      newRole = 'user';
    }
  }
  
  // Ensure users are filtered when they change
  $: {
    users; // Track changes to users
    filterUsers();
  }
</script>

<div class="user-management">
  {#if errorMessage}
    <div class="alert alert-error">
      <p>{errorMessage}</p>
      <button on:click={clearMessages}>×</button>
    </div>
  {/if}
  
  {#if successMessage}
    <div class="alert alert-success">
      <p>{successMessage}</p>
      <button on:click={clearMessages}>×</button>
    </div>
  {/if}
  
  <div class="table-controls">
    <div class="search-container">
      <input 
        type="text" 
        placeholder="Search users..." 
        on:input={handleSearchInput}
        value={searchTerm}
        title="Search users by name, email, or role"
      />
    </div>
    
    <button 
      on:click={toggleAddUserForm} 
      class="add-button"
      title="{showAddUserForm ? 'Cancel adding a new user' : 'Create a new user account'}"
    >
      {showAddUserForm ? 'Cancel' : 'Add User'}
    </button>
  </div>
  
  {#if showAddUserForm}
    <div class="add-user-form">
      <h3>Add New User</h3>
      <div class="form-group">
        <label for="username">Username</label>
        <input 
          type="text" 
          id="username" 
          bind:value={newUsername} 
          placeholder="Username"
          required
        />
      </div>
      
      <div class="form-group">
        <label for="email">Email</label>
        <input 
          type="email" 
          id="email" 
          bind:value={newEmail} 
          placeholder="Email"
          required
        />
      </div>
      
      <div class="form-group">
        <label for="password">Password</label>
        <input 
          type="password" 
          id="password" 
          bind:value={newPassword} 
          placeholder="Password"
          required
        />
      </div>
      
      <div class="form-group">
        <label for="role">Role</label>
        <select id="role" bind:value={newRole}>
          <option value="user">User</option>
          <option value="admin">Admin</option>
        </select>
      </div>
      
      <button 
        on:click={createUser} 
        class="create-button"
        title="Create the new user account with the provided information"
      >Create User</button>
    </div>
  {/if}
  
  {#if loading}
    <div class="loading-state">
      <p>Loading users...</p>
    </div>
  {:else if !users || users.length === 0}
    <div class="empty-state">
      <p>No users found.</p>
    </div>
  {:else}
    <table class="users-table user-management-table">
      <thead>
        <tr>
          <th>Username</th>
          <th>Email</th>
          <th>Role</th>
          <th>Created</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        {#each filteredUsers as currentUser (currentUser.id)}
          <tr>
            <td>{currentUser.username}</td>
            <td>{currentUser.email}</td>
            <td>
              {#if currentUser.id !== currentUserId}
                <select 
                  value={currentUser.role}
                  on:change={(e) => handleUserRoleChange(currentUser.id, e)}
                  title="Change the role for {currentUser.full_name || currentUser.email}"
                >
                  <option value="user">User</option>
                  <option value="admin">Admin</option>
                </select>
              {:else}
                <span class="current-role">{currentUser.role}</span>
              {/if}
            </td>
            <td>{formatDate(currentUser.created_at)}</td>
            <td>
              <div class="table-actions">
                {#if currentUser.id !== currentUserId}
                  <button 
                    class="delete-button"
                    on:click={() => deleteUser(currentUser.id)}
                    title="Permanently delete {currentUser.full_name || currentUser.email}'s account"
                  >
                    Delete
                  </button>
                {:else}
                  <span class="self-user">Current User</span>
                {/if}
              </div>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</div>

<style>
  .user-management {
    width: 100%;
    margin-bottom: 2rem;
  }
  
  .table-controls {
    display: flex;
    justify-content: space-between;
    margin-bottom: 1rem;
  }
  
  .search-container {
    flex: 1;
    margin-right: 1rem;
  }
  
  .search-container input {
    width: 100%;
    padding: 0.5rem;
    border: 1px solid #ccc;
    border-radius: 4px;
  }
  
  .add-button {
    background-color: #3b82f6;
    color: white;
    border: none;
    padding: 0.6rem 1.2rem;
    border-radius: 10px;
    cursor: pointer;
    font-size: 0.95rem;
    font-weight: 500;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }
  
  .add-button:hover:not(:disabled),
  .add-button:focus:not(:disabled) {
    background-color: #2563eb;
    color: white;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
    text-decoration: none;
  }
  
  .add-button:active:not(:disabled) {
    transform: translateY(0);
  }
  
  .add-user-form {
    background-color: var(--card-background);
    padding: 1rem;
    border-radius: 4px;
    margin-bottom: 1rem;
    border: 1px solid var(--border-color);
    color: var(--text-color);
  }
  
  .form-group {
    margin-bottom: 0.5rem;
  }
  
  .form-group label {
    display: block;
    margin-bottom: 0.25rem;
  }
  
  .form-group input, .form-group select {
    width: 100%;
    padding: 0.5rem;
    border: 1px solid #ccc;
    border-radius: 4px;
  }
  
  .create-button {
    background-color: #3b82f6;
    color: white;
    border: none;
    padding: 0.6rem 1.2rem;
    border-radius: 10px;
    cursor: pointer;
    font-size: 0.95rem;
    font-weight: 500;
    margin-top: 0.5rem;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }
  
  .create-button:hover:not(:disabled),
  .create-button:focus:not(:disabled) {
    background-color: #2563eb;
    color: white;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
    text-decoration: none;
  }
  
  .create-button:active:not(:disabled) {
    transform: translateY(0);
  }
  
  .users-table {
    width: 100%;
    border-collapse: collapse;
    background-color: var(--card-background);
    border-radius: 6px;
    overflow: hidden;
    box-shadow: var(--card-shadow);
  }
  
  .users-table th, .users-table td {
    padding: 0.75rem;
    border-bottom: 1px solid var(--border-color);
    text-align: left;
    color: var(--text-color);
  }
  
  .users-table th {
    background-color: var(--table-header-bg);
    font-weight: bold;
  }
  
  .users-table tr:hover {
    background-color: var(--table-row-hover);
  }
  
  .table-actions {
    display: flex;
    gap: 0.5rem;
  }
  
  .delete-button {
    background-color: #ef4444;
    color: white;
    border: none;
    padding: 0.6rem 1.2rem;
    border-radius: 10px;
    cursor: pointer;
    font-size: 0.95rem;
    font-weight: 500;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(239, 68, 68, 0.2);
  }
  
  .delete-button:hover:not(:disabled),
  .delete-button:focus:not(:disabled) {
    background-color: #d32f2f;
    color: white;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(239, 68, 68, 0.25);
    text-decoration: none;
  }
  
  .delete-button:active:not(:disabled) {
    transform: translateY(0);
  }
  
  .delete-button:disabled {
    background-color: #6c757d;
    cursor: not-allowed;
  }
  
  .current-role {
    font-weight: bold;
    text-transform: capitalize;
  }
  
  .self-user {
    font-style: italic;
    color: var(--text-secondary);
  }
  
  .alert {
    padding: 0.75rem;
    margin-bottom: 1rem;
    border-radius: 4px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  
  .alert-error {
    background-color: #f8d7da;
    color: #721c24;
    border: 1px solid #f5c6cb;
  }
  
  .alert-success {
    background-color: #d4edda;
    color: #155724;
    border: 1px solid #c3e6cb;
  }
  
  .alert button {
    background: none;
    border: none;
    font-size: 1.25rem;
    cursor: pointer;
    color: inherit;
  }
  
  .loading-state, .empty-state {
    padding: 2rem;
    text-align: center;
    background-color: var(--card-background);
    border-radius: 4px;
    margin-top: 1rem;
    color: var(--text-color);
  }
</style>
