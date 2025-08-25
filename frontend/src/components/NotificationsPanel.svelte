<script>
  import { onMount, onDestroy } from 'svelte';
  import { derived } from 'svelte/store';
  import { Link } from 'svelte-navigator';
  import { token } from '../stores/auth';
  import { websocketStore } from '../stores/websocket';
  import { notifications, showNotificationsPanel, markAllAsRead as markAllNotificationsAsRead } from '../stores/notifications';
  
  // Prop to control whether to show the notification bell button
  export let hideButton = false;
  
  // Subscribe to the showNotificationsPanel store
  let showPanel = false;
  const unsubscribePanel = showNotificationsPanel.subscribe(value => {
    showPanel = value;
  });

  // Reactive statement to manage body scroll when panel state changes
  $: {
    if (typeof document !== 'undefined') {
      if (showPanel) {
        document.body.style.overflow = 'hidden';
      } else {
        document.body.style.overflow = 'auto';
      }
    }
  }
  
  /** @type {Date} */
  let lastRead = new Date();
  
  // Derived store for unread count
  const wsUnreadCount = derived(websocketStore, ($store) => {
    return $store.notifications ? $store.notifications.filter(n => !n.read).length : 0;
  });
  
  // Toggle notification panel
  function togglePanel() {
    showNotificationsPanel.update(value => !value);
  }
  
  // Close the notifications panel
  function closePanel() {
    showNotificationsPanel.set(false);
    // Don't automatically mark as read - let user do it manually
  }
  
  /**
   * Close panel when clicking outside
   * @param {MouseEvent} event - The click event
   */
  function handleClickOutside(event) {
    const panel = document.querySelector('.notifications-panel');
    const button = document.querySelector('.notifications-button');
    const target = event.target;
    
    if (panel && button && target instanceof Node && !panel.contains(target) && !button.contains(target)) {
      showPanel = false;
    }
  }
  
  /**
   * Remove a notification
   * @param {string} id - The notification ID
   */
  function removeNotification(id) {
    websocketStore.markAsRead(id);
  }
  
  // Clear all notifications
  function clearAllNotifications() {
    websocketStore.clearAll();
  }

  // Mark all notifications as read
  function markAllWebSocketNotificationsAsRead() {
    if (websocketStore.markAllAsRead) {
      websocketStore.markAllAsRead();
    }
  }
  
  /**
   * Get appropriate icon for notification type
   * @param {string} type - The notification type
   * @returns {string} - Icon name
   */
  function getNotificationIcon(type) {
    switch (type) {
      case 'transcription_status':
        return 'file-text';
      case 'summarization_status':
        return 'file-text';
      case 'analytics_status':
        return 'bar-chart';
      default:
        return 'bell';
    }
  }
  
  /**
   * Format timestamp to relative time (e.g. "5 minutes ago")
   * @param {Date} date - The date to format
   * @returns {string} - Formatted relative time
   */
  function formatTimestamp(date) {
    const now = new Date();
    const diff = Math.floor((now.getTime() - date.getTime()) / 1000);
    
    if (diff < 60) {
      return 'Just now';
    } else if (diff < 3600) {
      const minutes = Math.floor(diff / 60);
      return `${minutes}m ago`;
    } else if (diff < 86400) {
      const hours = Math.floor(diff / 3600);
      return `${hours}h ago`;
    } else {
      const days = Math.floor(diff / 86400);
      return `${days}d ago`;
    }
  }
  
  /**
   * Get file link based on notification data
   * @param {Object} notification - The notification object
   * @param {Object} [notification.data] - Optional notification data
   * @param {string} [notification.data.file_id] - Optional file ID
   * @returns {string|null} - File link or null if no file_id
   */
  function getFileLink(notification) {
    if (notification.data && notification.data.file_id) {
      return `/files/${notification.data.file_id}`;
    }
    return null;
  }

  /**
   * Get status color for notification type
   * @param {Object} notification - The notification object
   * @returns {string} - CSS class for status
   */
  function getNotificationStatus(notification) {
    if (notification.data?.status) {
      const status = notification.data.status;
      switch (status) {
        case 'completed':
          return 'success';
        case 'error':
        case 'failed':
          return 'error';
        case 'processing':
        case 'in_progress':
          return 'info';
        default:
          return 'default';
      }
    }
    return 'default';
  }
  
  onMount(() => {
    // Add event listener for clicks outside the panel
    document.addEventListener('click', handleClickOutside);
  });
  
  onDestroy(() => {
    // Remove event listener when component is destroyed
    document.removeEventListener('click', handleClickOutside);
    unsubscribePanel();
    
    // Restore body scroll when component is destroyed
    if (typeof document !== 'undefined') {
      document.body.style.overflow = 'auto';
    }
  });
</script>

{#if showPanel}
  <!-- Backdrop for mobile/tablet -->
  <div class="notifications-backdrop" on:click={closePanel}></div>
  
  <div class="notifications-panel">
    <!-- Header -->
    <div class="notifications-header">
      <div class="header-left">
        <h3 class="header-title">Notifications</h3>
        {#if $wsUnreadCount > 0}
          <span class="unread-badge">{$wsUnreadCount}</span>
        {/if}
      </div>
      <div class="header-actions">
        {#if $wsUnreadCount > 0}
          <button 
            class="action-btn mark-read-btn" 
            on:click={markAllWebSocketNotificationsAsRead}
            title="Mark all notifications as read"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
            Mark read
          </button>
        {/if}
        {#if $websocketStore.notifications.length > 0}
          <button 
            class="action-btn clear-btn" 
            on:click={clearAllNotifications}
            title="Clear all notifications"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="3 6 5 6 21 6"></polyline>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
            </svg>
            Clear all
          </button>
        {/if}
        <button 
          class="action-btn close-btn" 
          on:click={closePanel}
          title="Close notifications panel"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
      </div>
    </div>
    
    <!-- Notifications List -->
    <div class="notifications-content">
      {#if $websocketStore.notifications.length === 0}
        <div class="empty-state">
          <div class="empty-icon">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path>
              <path d="M13.73 21a2 2 0 0 1-3.46 0"></path>
            </svg>
          </div>
          <p class="empty-title">No notifications</p>
          <p class="empty-subtitle">You're all caught up!</p>
        </div>
      {:else}
        <div class="notifications-list">
          {#each $websocketStore.notifications as notification (notification.id)}
            <div class="notification-item {notification.read ? 'read' : 'unread'} status-{getNotificationStatus(notification)}">
              <!-- Status indicator -->
              <div class="notification-indicator"></div>
              
              <!-- Icon -->
              <div class="notification-icon">
                {#if getNotificationIcon(notification.type) === 'file-text'}
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                    <polyline points="14 2 14 8 20 8"></polyline>
                    <line x1="16" y1="13" x2="8" y2="13"></line>
                    <line x1="16" y1="17" x2="8" y2="17"></line>
                  </svg>
                {:else if getNotificationIcon(notification.type) === 'bar-chart'}
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="18" y1="20" x2="18" y2="10"></line>
                    <line x1="12" y1="20" x2="12" y2="4"></line>
                    <line x1="6" y1="20" x2="6" y2="14"></line>
                  </svg>
                {:else}
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path>
                    <path d="M13.73 21a2 2 0 0 1-3.46 0"></path>
                  </svg>
                {/if}
              </div>
              
              <!-- Content -->
              <div class="notification-content">
                <div class="notification-main">
                  <h4 class="notification-title">{notification.title}</h4>
                  <p class="notification-message">{notification.message}</p>
                  
                  <!-- Action link if available -->
                  {#if getFileLink(notification) !== null}
                    <Link 
                      to={getFileLink(notification) || ''} 
                      class="notification-action" 
                      on:click={() => {
                        showPanel = false;
                        // Mark this specific notification as read when navigating to file
                        if (!notification.read) {
                          websocketStore.markAsRead(notification.id);
                        }
                      }}
                    >
                      View File →
                    </Link>
                  {/if}
                </div>
                
                <div class="notification-meta">
                  <span class="notification-time">{formatTimestamp(notification.timestamp)}</span>
                </div>
              </div>
              
              <!-- Dismiss button -->
              <button 
                class="notification-dismiss" 
                on:click={() => removeNotification(notification.id)}
                title="Dismiss notification"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18"></line>
                  <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
              </button>
            </div>
          {/each}
        </div>
      {/if}
    </div>
  </div>
{/if}

<style>
  .notifications-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: transparent;
    z-index: 999;
  }
  
  .notifications-panel {
    position: fixed;
    top: 70px;
    right: 16px;
    width: 380px;
    max-width: calc(100vw - 32px);
    max-height: calc(100vh - 90px);
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    box-shadow: 
      0 20px 25px -5px rgba(0, 0, 0, 0.1),
      0 10px 10px -5px rgba(0, 0, 0, 0.04),
      0 0 0 1px rgba(0, 0, 0, 0.05);
    z-index: 1000;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  
  :global(.dark) .notifications-panel {
    box-shadow: 
      0 20px 25px -5px rgba(0, 0, 0, 0.4),
      0 10px 10px -5px rgba(0, 0, 0, 0.2),
      0 0 0 1px rgba(255, 255, 255, 0.05);
  }
  
  /* Header */
  .notifications-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 20px;
    border-bottom: 1px solid var(--border-color);
    background: var(--surface-color);
    border-radius: 12px 12px 0 0;
  }
  
  .header-left {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  
  .header-title {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
    color: var(--text-color);
  }
  
  .unread-badge {
    background: var(--primary-color);
    color: white;
    font-size: 11px;
    font-weight: 600;
    padding: 2px 6px;
    border-radius: 10px;
    min-width: 16px;
    height: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  
  .header-actions {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  
  .action-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 8px;
    background: none;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    color: var(--text-secondary);
    font-size: 13px;
    font-weight: 500;
    transition: all 0.2s ease;
  }
  
  .action-btn:hover {
    background: var(--hover-color, rgba(0, 0, 0, 0.05));
    color: var(--text-color);
  }
  
  .mark-read-btn {
    color: var(--success-color);
  }
  
  .mark-read-btn:hover {
    background: rgba(16, 185, 129, 0.1);
    color: var(--success-color);
  }

  .clear-btn {
    color: var(--error-color);
  }
  
  .clear-btn:hover {
    background: rgba(239, 68, 68, 0.1);
    color: var(--error-color);
  }
  
  .close-btn {
    padding: 6px;
  }
  
  /* Content */
  .notifications-content {
    flex: 1;
    overflow-y: auto;
    min-height: 0;
  }
  
  .notifications-list {
    display: flex;
    flex-direction: column;
  }
  
  /* Empty State */
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 48px 24px;
    text-align: center;
  }
  
  .empty-icon {
    margin-bottom: 16px;
    color: var(--text-secondary);
    opacity: 0.6;
  }
  
  .empty-title {
    margin: 0 0 4px 0;
    font-size: 15px;
    font-weight: 600;
    color: var(--text-color);
  }
  
  .empty-subtitle {
    margin: 0;
    font-size: 13px;
    color: var(--text-secondary);
  }
  
  /* Notification Items */
  .notification-item {
    position: relative;
    display: flex;
    align-items: flex-start;
    gap: 12px;
    padding: 16px 20px;
    border-bottom: 1px solid var(--border-color);
    transition: all 0.2s ease;
    background: var(--background-color);
  }
  
  .notification-item:last-child {
    border-bottom: none;
  }
  
  .notification-item:hover {
    background: var(--hover-color, rgba(0, 0, 0, 0.025));
  }
  
  .notification-item.unread {
    background: rgba(59, 130, 246, 0.04);
  }
  
  :global(.dark) .notification-item.unread {
    background: rgba(59, 130, 246, 0.08);
  }
  
  /* Status indicators */
  .notification-indicator {
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 3px;
    background: transparent;
  }
  
  .notification-item.status-success .notification-indicator {
    background: var(--success-color);
  }
  
  .notification-item.status-error .notification-indicator {
    background: var(--error-color);
  }
  
  .notification-item.status-info .notification-indicator {
    background: var(--primary-color);
  }
  
  .notification-item.unread .notification-indicator {
    background: var(--primary-color);
  }
  
  /* Icon */
  .notification-icon {
    flex-shrink: 0;
    width: 32px;
    height: 32px;
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    color: var(--text-secondary);
    margin-top: 2px;
  }
  
  .notification-item.status-success .notification-icon {
    background: rgba(16, 185, 129, 0.1);
    border-color: rgba(16, 185, 129, 0.2);
    color: var(--success-color);
  }
  
  .notification-item.status-error .notification-icon {
    background: rgba(239, 68, 68, 0.1);
    border-color: rgba(239, 68, 68, 0.2);
    color: var(--error-color);
  }
  
  .notification-item.status-info .notification-icon {
    background: rgba(59, 130, 246, 0.1);
    border-color: rgba(59, 130, 246, 0.2);
    color: var(--primary-color);
  }
  
  /* Content */
  .notification-content {
    flex: 1;
    min-width: 0;
  }
  
  .notification-main {
    margin-bottom: 8px;
  }
  
  .notification-title {
    margin: 0 0 4px 0;
    font-size: 14px;
    font-weight: 600;
    color: var(--text-color);
    line-height: 1.4;
  }
  
  .notification-message {
    margin: 0 0 8px 0;
    font-size: 13px;
    color: var(--text-secondary);
    line-height: 1.4;
    word-wrap: break-word;
  }
  
  .notification-action {
    display: inline-flex;
    align-items: center;
    font-size: 12px;
    font-weight: 600;
    color: var(--primary-color);
    text-decoration: none;
    transition: color 0.2s ease;
  }
  
  .notification-action:hover {
    color: var(--primary-color-dark, #2563eb);
    text-decoration: none;
  }
  
  .notification-meta {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  
  .notification-time {
    font-size: 11px;
    font-weight: 500;
    color: var(--text-secondary);
    opacity: 0.8;
  }
  
  /* Dismiss Button */
  .notification-dismiss {
    flex-shrink: 0;
    width: 24px;
    height: 24px;
    background: none;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    color: var(--text-secondary);
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
    opacity: 0.6;
  }
  
  .notification-dismiss:hover {
    background: var(--error-background, rgba(239, 68, 68, 0.1));
    color: var(--error-color);
    opacity: 1;
  }
  
  /* Scrollbar Styling */
  .notifications-content::-webkit-scrollbar {
    width: 6px;
  }
  
  .notifications-content::-webkit-scrollbar-track {
    background: transparent;
  }
  
  .notifications-content::-webkit-scrollbar-thumb {
    background: var(--border-color);
    border-radius: 3px;
  }
  
  .notifications-content::-webkit-scrollbar-thumb:hover {
    background: var(--text-secondary);
  }
  
  /* Responsive Design */
  @media (max-width: 480px) {
    .notifications-panel {
      right: 8px;
      left: 8px;
      width: auto;
      max-width: none;
    }
    
    .notifications-header {
      padding: 14px 16px;
    }
    
    .notification-item {
      padding: 14px 16px;
      gap: 10px;
    }
    
    .notification-icon {
      width: 28px;
      height: 28px;
    }
    
    .header-title {
      font-size: 15px;
    }
  }
  
  /* Reduced motion support */
  @media (prefers-reduced-motion: reduce) {
    .notification-item,
    .action-btn,
    .notification-dismiss,
    .notification-action {
      transition: none;
    }
  }
  
  /* High contrast mode support */
  @media (prefers-contrast: high) {
    .notifications-panel {
      border-width: 2px;
    }
    
    .notification-item {
      border-bottom-width: 2px;
    }
    
    .notification-indicator {
      width: 4px;
    }
  }
</style>