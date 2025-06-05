<script>
  import { Link, useNavigate, useLocation } from "svelte-navigator";
  import { user, logout, fetchUserInfo } from "../stores/auth";
  import { onMount, onDestroy } from "svelte";
  import NotificationsPanel from "./NotificationsPanel.svelte";
  import ThemeToggle from "./ThemeToggle.svelte";
  
  // Import the centralized notification store
  import { showNotificationsPanel, toggleNotificationsPanel, notifications } from '../stores/notifications';
  import { unreadCount } from '../stores/websocket';
  
  // Import logo asset for proper Vite processing
  import logoBanner from '../assets/logo-banner.png';
  
  // Location for active state detection
  const location = useLocation();
  
  // Reactive statements for active page detection
  $: currentPath = $location.pathname;
  $: isGalleryActive = currentPath === '/' || currentPath === '';
  $: isTasksActive = currentPath === '/file-status' || currentPath.startsWith('/file-status');
  $: showGalleryLink = !isGalleryActive && !isTasksActive; // Show gallery link when not on gallery or tasks
  
  // Navigation
  const navigate = useNavigate();
  
  // User dropdown state
  /** @type {boolean} */
  let showDropdown = false;
  
  /** @type {HTMLDivElement | null} */
  let dropdownRef = null;
  
  // Notification panel state
  let showNotifs = false;
  const unsubscribe = showNotificationsPanel.subscribe(value => {
    showNotifs = value;
  });
  
  /**
   * Handle user logout
   */
  function handleLogout() {
    logout();
    navigate("/login");
  }
  
  /**
   * Toggle the user dropdown menu
   * @param {MouseEvent} event - The mouse click event
   */
  function toggleDropdown(event) {
    event.stopPropagation(); // Prevent event from bubbling up
    showDropdown = !showDropdown;
    // Close notifications panel when opening user dropdown
    if (showDropdown && showNotifs) {
      showNotificationsPanel.set(false);
    }
  }
  
  /**
   * Toggle the notifications panel
   * @param {MouseEvent} event - The mouse click event
   */
  function handleToggleNotifications(event) {
    event.stopPropagation(); // Prevent event from bubbling up
    toggleNotificationsPanel();
    // Close user dropdown when opening notifications
    if (showDropdown && !showNotifs) {
      showDropdown = false;
    }
  }
  
  /**
   * Handle clicks outside the dropdown to close it
   * @param {MouseEvent} event - The mouse event
   */
  function handleClickOutside(event) {
    if (dropdownRef && !dropdownRef.contains(/** @type {Node} */ (event.target))) {
      showDropdown = false;
    }
  }
  
  // Setup and cleanup event listeners
  onMount(() => {
    document.addEventListener('click', handleClickOutside);
    
    // Refresh user data to ensure we have the latest profile information
    // This ensures the navbar always shows the most up-to-date user info
    fetchUserInfo().catch(err => {
      console.error('Error refreshing user data in Navbar:', err);
    });
  });
  
  onDestroy(() => {
    document.removeEventListener('click', handleClickOutside);
    unsubscribe();
  });
</script>

<nav class="navbar">
  <div class="navbar-container">
    <div class="navbar-brand">
      <Link 
        to="/"
        title="Go to OpenTranscribe home page"
      >
        <img src={logoBanner} alt="OpenTranscribe" class="logo-banner" />
      </Link>
    </div>
    
    <div class="nav-links">
      <!-- Gallery link - only show when not on gallery/file pages -->
      {#if showGalleryLink}
        <a 
          href="/"
          title="Go back to your media library and files"
          class="nav-link"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
            <circle cx="8.5" cy="8.5" r="1.5"></circle>
            <polyline points="21 15 16 10 5 21"></polyline>
          </svg>
          Back to Gallery
        </a>
      {/if}
      
      <!-- Notifications button -->
      <button 
        class="notifications-btn" 
        on:click={handleToggleNotifications}
        title="View notifications and alerts{$unreadCount > 0 ? ` (${$unreadCount} unread)` : ''}"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path>
          <path d="M13.73 21a2 2 0 0 1-3.46 0"></path>
        </svg>
        {#if $unreadCount > 0}
          <span class="notification-badge">{$unreadCount}</span>
        {/if}
      </button>
      
      <!-- Theme toggle switch -->
      <div class="theme-toggle-container">
        <ThemeToggle />
      </div>
      
      <!-- User profile dropdown -->
      <div class="user-dropdown" bind:this={dropdownRef}>
        <button 
          class="user-button" 
          on:click={toggleDropdown}
          title="Open user menu for settings, admin access, and logout"
        >
          <div class="user-avatar">
            <!-- First letter of full name as avatar -->
            {#if $user && $user.full_name}
              {$user.full_name[0].toUpperCase()}
            {:else}
              U
            {/if}
          </div>
          <span class="username">{$user ? $user.full_name : 'User'}</span>
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="dropdown-icon">
            <polyline points="6 9 12 15 18 9"></polyline>
          </svg>
        </button>
        
        {#if showDropdown}
          <div class="dropdown-menu">
            <div class="dropdown-header">
              <span>Signed in as</span>
              <strong>{$user ? $user.email : 'User'}</strong>
            </div>
            <div class="dropdown-divider"></div>
            <Link 
              to="/settings" 
              class="dropdown-item" 
              on:click={() => showDropdown = false}
              title="Manage your account settings and preferences"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="3"></circle>
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
              </svg>
              <span>Settings</span>
            </Link>
            
            {#if $user && $user.role === "admin"}
              <Link 
                to="/admin" 
                class="dropdown-item" 
                on:click={() => showDropdown = false}
                title="Access admin dashboard for user management and system settings"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                  <circle cx="9" cy="7" r="4"></circle>
                  <path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
                  <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
                </svg>
                <span>Admin</span>
              </Link>
            {/if}
            
            <button 
              class="dropdown-item" 
              on:click={() => {
                // Get the current protocol and host
                const protocol = window.location.protocol;
                const host = window.location.hostname;
                const port = import.meta.env.VITE_FLOWER_PORT || '5555';
                const urlPrefix = import.meta.env.VITE_FLOWER_URL_PREFIX || 'flower';
                
                // Construct the URL properly with trailing slash
                const url = urlPrefix 
                  ? `${protocol}//${host}:${port}/${urlPrefix}/` 
                  : `${protocol}//${host}:${port}/`;
                
                // Open Flower in a new tab with the correct URL
                window.open(url, '_blank');
                showDropdown = false;
              }}
              aria-label="Open Flower Dashboard"
              title="Open Flower dashboard to monitor task queues and worker status"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
              </svg>
              <span>Flower Dashboard</span>
            </button>
            <div class="dropdown-divider"></div>
            <button 
              class="dropdown-item logout" 
              on:click={handleLogout}
              title="Sign out of your account"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
                <polyline points="16 17 21 12 16 7"></polyline>
                <line x1="21" y1="12" x2="9" y2="12"></line>
              </svg>
              Logout
            </button>
          </div>
        {/if}
      </div>
    </div>
    
    <div class="mobile-toggle">
      <button>
        <span class="sr-only">Menu</span>
        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="3" y1="12" x2="21" y2="12"></line>
          <line x1="3" y1="6" x2="21" y2="6"></line>
          <line x1="3" y1="18" x2="21" y2="18"></line>
        </svg>
      </button>
    </div>
  </div>
</nav>

<!-- Add the NotificationsPanel component -->
{#if showNotifs}
  <NotificationsPanel hideButton={true} />
{/if}

<style>
  .navbar {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    height: 60px;
    background-color: var(--surface-color);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    z-index: 1000;
  }
  
  .navbar-container {
    display: flex;
    justify-content: space-between;
    align-items: center;
    height: 100%;
    padding: 0 1rem;
    max-width: 1200px;
    margin: 0 auto;
  }
  
  .navbar-brand {
    display: flex;
    align-items: center;
  }
  
  .navbar-brand :global(a) {
    display: flex;
    align-items: center;
    text-decoration: none;
    color: var(--primary-color);
    font-weight: 600;
    font-size: 1.25rem;
  }
  
  .logo-banner {
    height: 36px;
    width: auto;
    object-fit: contain;
    border-radius: 6px;
  }
  
  .nav-links {
    display: flex;
    align-items: center;
    gap: 1.5rem;
  }
  
  .nav-link {
    color: var(--text-color);
    text-decoration: none;
    padding: 0.5rem 1rem;
    border-radius: 6px;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: none;
    border: none;
    font-family: inherit;
    font-size: 1rem;
    cursor: pointer;
    position: relative;
    font-weight: 500;
  }
  
  .nav-link:hover {
    background-color: var(--hover-color, rgba(0, 0, 0, 0.05));
    color: var(--primary-color);
  }
  
  /* Focus states for accessibility */
  .nav-link:focus {
    outline: 2px solid var(--primary-color);
    outline-offset: 2px;
  }
  
  /* Responsive adjustments for mobile */
  @media (max-width: 768px) {
    .nav-links {
      gap: 0.5rem;
    }
    
    .nav-link {
      padding: 0.4rem 0.8rem;
      font-size: 0.9rem;
    }
    
  }
  
  /* High contrast mode support */
  @media (prefers-contrast: high) {
    .nav-link:hover {
      border: 1px solid var(--primary-color);
    }
  }
  
  /* Reduced motion support */
  @media (prefers-reduced-motion: reduce) {
    .nav-link {
      transition: none;
    }
  }
  
  
  .theme-toggle-container {
    display: flex;
    align-items: center;
    margin: 0 8px;
  }
  
  .notifications-btn {
    background: none;
    border: none;
    padding: 8px;
    border-radius: 50%;
    cursor: pointer;
    color: var(--text-color);
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background-color 0.2s;
  }
  
  .notifications-btn:hover {
    background-color: rgba(0, 0, 0, 0.05);
  }
  
  .notification-badge {
    position: absolute;
    top: -5px;
    right: -5px;
    background-color: var(--error-color);
    color: white;
    width: 18px;
    height: 18px;
    font-size: 0.7rem;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    font-weight: bold;
  }
  
  /* User Dropdown Styles */
  .user-dropdown {
    position: relative;
  }
  
  .user-button {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: transparent;
    border: none;
    cursor: pointer;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    color: var(--text-color);
    font-family: inherit;
    font-size: 1rem;
  }
  
  .user-button:hover {
    background-color: rgba(0, 0, 0, 0.05);
  }
  
  .user-avatar {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background-color: var(--primary-color);
    color: white;
    font-weight: 600;
  }
  
  .username {
    font-weight: 500;
  }
  
  .dropdown-icon {
    margin-left: 0.25rem;
    opacity: 0.7;
  }
  
  .dropdown-menu {
    position: absolute;
    top: 100%;
    right: 0;
    width: 240px;
    background-color: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1);
    overflow: hidden;
    margin-top: 0.5rem;
    z-index: 1000;
    padding: 0.5rem 0;
    min-width: 200px;
    display: flex;
    flex-direction: column;
  }
  
  .dropdown-header {
    padding: 0.75rem 1rem;
    color: var(--text-color-secondary);
    font-size: 0.8rem;
    line-height: 1.4;
    white-space: normal;
  }
  
  .dropdown-header strong {
    display: block;
    color: var(--text-color);
    font-weight: 600;
    margin-top: 0.25rem;
    word-break: break-all;
  }
  
  .dropdown-divider {
    height: 1px;
    background-color: var(--border-color);
    margin: 0.125rem 0;
    border: none;
  }
  
  
  .dropdown-item {
    display: flex !important;
    align-items: center;
    gap: 0.75rem;
    padding: 0.5rem 1rem;
    color: var(--text-color) !important;
    text-decoration: none !important;
    transition: all 0.2s ease;
    font-size: 0.9rem;
    font-weight: 500;
    border: none;
    width: calc(100% - 1rem);
    text-align: left;
    background-color: transparent;
    cursor: pointer;
    font-family: inherit;
    box-sizing: border-box;
    margin: 0.125rem 0.5rem;
    border-radius: 6px;
    white-space: nowrap;
    position: relative;
  }
  
  /* Override any global link styles specifically for dropdown items */
  .dropdown-menu :global(a.dropdown-item) {
    color: var(--text-color) !important;
    text-decoration: none !important;
    display: flex !important;
    align-items: center !important;
    gap: 0.75rem !important;
    padding: 0.5rem 1rem !important;
    margin: 0.125rem 0.5rem !important;
    width: calc(100% - 1rem) !important;
    font-weight: 500 !important;
    border-radius: 6px !important;
    background-color: transparent !important;
    transition: all 0.2s ease !important;
  }
  
  .dropdown-menu :global(a.dropdown-item:hover) {
    color: var(--primary-color) !important;
    text-decoration: none !important;
    background-color: var(--hover-color, rgba(0, 0, 0, 0.05)) !important;
    transform: translateX(2px) !important;
  }
  
  .dropdown-menu :global(a.dropdown-item:visited) {
    color: var(--text-color) !important;
    text-decoration: none !important;
  }
  
  .dropdown-menu :global(a.dropdown-item:visited:hover) {
    color: var(--primary-color) !important;
    text-decoration: none !important;
  }
  
  .dropdown-item svg {
    width: 16px;
    height: 16px;
    flex-shrink: 0;
    opacity: 0.7;
    transition: all 0.2s ease;
  }
  
  /* Ensure SVGs in Link components behave the same as button SVGs */
  .dropdown-menu :global(a.dropdown-item svg) {
    width: 16px !important;
    height: 16px !important;
    flex-shrink: 0 !important;
    opacity: 0.7 !important;
    transition: all 0.2s ease !important;
  }
  
  .dropdown-menu :global(a.dropdown-item:hover svg) {
    opacity: 1 !important;
    color: var(--primary-color) !important;
  }
  
  .dropdown-item:hover {
    background-color: var(--hover-color, rgba(0, 0, 0, 0.05));
    color: var(--primary-color);
    transform: translateX(2px);
  }
  
  .dropdown-item:hover svg {
    opacity: 1;
    color: var(--primary-color);
  }
  
  .dropdown-item:focus {
    outline: 2px solid var(--primary-color);
    outline-offset: -2px;
  }
  
  .dropdown-item.logout {
    color: var(--error-color, #ef4444);
    margin-top: 0.125rem;
  }
  
  .dropdown-item.logout svg {
    opacity: 0.8;
  }
  
  .dropdown-item.logout:hover {
    background-color: rgba(239, 68, 68, 0.1);
    color: var(--error-color, #dc2626);
    transform: translateX(2px);
  }
  
  .dropdown-item.logout:hover svg {
    opacity: 1;
    color: var(--error-color, #dc2626);
  }
  
  /* Active state for dropdown items */
  .dropdown-item:active {
    transform: translateX(1px);
    background-color: var(--primary-color-light, rgba(59, 130, 246, 0.1));
  }
  
  /* Improved spacing between groups */
  .dropdown-item + .dropdown-divider {
    margin-top: 0.25rem;
  }
  
  .dropdown-divider + .dropdown-item {
    margin-top: 0.125rem;
  }
  
  .mobile-toggle {
    display: none;
  }
  
  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border-width: 0;
  }
  
  @media (max-width: 768px) {
    .nav-links {
      display: none;
    }
    
    .mobile-toggle {
      display: block;
    }
    
    .mobile-toggle button {
      background: transparent;
      border: none;
      cursor: pointer;
      color: var(--text-color);
    }
    
    /* Mobile dropdown adjustments */
    .dropdown-menu {
      width: 220px;
      right: -10px;
    }
    
    .dropdown-item {
      padding: 0.625rem 1rem;
      margin: 0.125rem 0.25rem;
      font-size: 0.95rem;
    }
    
    .dropdown-item:hover {
      transform: none; /* Disable transform on mobile for better touch experience */
    }
  }
  
  /* Reduced motion preferences */
  @media (prefers-reduced-motion: reduce) {
    .dropdown-item,
    .dropdown-item svg {
      transition: none;
    }
    
    .dropdown-item:hover {
      transform: none;
    }
  }
  
  /* High contrast mode support */
  @media (prefers-contrast: high) {
    .dropdown-item {
      border: 1px solid transparent;
    }
    
    .dropdown-item:hover {
      border-color: var(--primary-color);
      background-color: var(--hover-color);
    }
    
    .dropdown-item.logout:hover {
      border-color: var(--error-color);
    }
  }
</style>
