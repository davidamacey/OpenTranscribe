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
    lastRead = new Date();
    
    // Mark all notifications as read
    markAllNotificationsAsRead();
    if (websocketStore.markAllAsRead) {
      websocketStore.markAllAsRead();
    }
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
      return `${minutes} ${minutes === 1 ? 'minute' : 'minutes'} ago`;
    } else if (diff < 86400) {
      const hours = Math.floor(diff / 3600);
      return `${hours} ${hours === 1 ? 'hour' : 'hours'} ago`;
    } else {
      const days = Math.floor(diff / 86400);
      return `${days} ${days === 1 ? 'day' : 'days'} ago`;
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
  
  onMount(() => {
    // Add event listener for clicks outside the panel
    document.addEventListener('click', handleClickOutside);
  });
  
  onDestroy(() => {
    // Remove event listener when component is destroyed
    document.removeEventListener('click', handleClickOutside);
  });
</script>

<div class="notifications-container">
  {#if !hideButton}
  <button 
    class="notifications-button" 
    on:click={togglePanel} 
    on:keydown={(e) => e.key === 'Enter' && togglePanel()}
    title="View notifications and alerts{$wsUnreadCount > 0 ? ` (${$wsUnreadCount} unread)` : ''}"
  >
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path>
      <path d="M13.73 21a2 2 0 0 1-3.46 0"></path>
    </svg>
    {#if $wsUnreadCount > 0}
      <span class="notification-badge">{$wsUnreadCount}</span>
    {/if}
  </button>
  {/if}
  
  {#if showPanel}
    <div class="notifications-panel">
      <div class="panel-header">
        <h3>Notifications</h3>
        <button 
          class="clear-all" 
          on:click={clearAllNotifications}
          title="Remove all notifications from the list"
        >Clear All</button>
      </div>
      
      <div class="notifications-list">
        {#if $websocketStore.notifications.length === 0}
          <div class="empty-state">
            <p>No notifications</p>
          </div>
        {:else}
          {#each $websocketStore.notifications as notification (notification.id)}
            <div class="notification-item {notification.read ? '' : 'unread'}">
              <div class="notification-icon {notification.type}">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  {#if getNotificationIcon(notification.type) === 'file-text'}
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                    <polyline points="14 2 14 8 20 8"></polyline>
                    <line x1="16" y1="13" x2="8" y2="13"></line>
                    <line x1="16" y1="17" x2="8" y2="17"></line>
                    <polyline points="10 9 9 9 8 9"></polyline>
                  {:else if getNotificationIcon(notification.type) === 'bar-chart'}
                    <line x1="18" y1="20" x2="18" y2="10"></line>
                    <line x1="12" y1="20" x2="12" y2="4"></line>
                    <line x1="6" y1="20" x2="6" y2="14"></line>
                  {:else}
                    <circle cx="12" cy="12" r="10"></circle>
                    <line x1="12" y1="8" x2="12" y2="12"></line>
                    <line x1="12" y1="16" x2="12.01" y2="16"></line>
                  {/if}
                </svg>
              </div>
              
              <div class="notification-content">
                <div class="notification-header">
                  <h4>{notification.title}</h4>
                  <button 
                    class="remove-button" 
                    on:click={() => removeNotification(notification.id)}
                    title="Remove this notification"
                  >×</button>
                </div>
                
                <p>{notification.message}</p>
                
                {#if getFileLink(notification) !== null}
                  <Link to={getFileLink(notification) || ''} class="notification-link" on:click={() => showPanel = false}>
                    View File
                  </Link>
                {/if}
                
                <span class="notification-time">
                  {formatTimestamp(notification.timestamp)}
                </span>
              </div>
            </div>
          {/each}
        {/if}
      </div>
    </div>
  {/if}
</div>

<style>
  .notifications-container {
    position: fixed;
    top: 70px;
    right: 20px;
    z-index: 1000;
  }
  
  .notifications-button {
    position: relative;
    background-color: var(--surface-color);
    border: none;
    border-radius: 50%;
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  }
  
  .badge {
    position: absolute;
    top: -5px;
    right: -5px;
    background-color: var(--error-color);
    color: white;
    border-radius: 50%;
    width: 18px;
    height: 18px;
    font-size: 0.7rem;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  
  .notifications-panel {
    position: absolute;
    top: 50px;
    right: 0;
    width: 300px;
    max-width: 90vw;
    background-color: var(--surface-color);
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    max-height: 400px;
    display: flex;
    flex-direction: column;
  }
  
  .panel-header {
    padding: 12px 16px;
    border-bottom: 1px solid var(--border-color);
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  
  .panel-header h3 {
    margin: 0;
    font-size: 1rem;
  }
  
  .close-button {
    background: transparent;
    border: none;
    cursor: pointer;
    color: var(--text-light);
  }
  
  .panel-content {
    overflow-y: auto;
    flex: 1;
    max-height: 300px;
  }
  
  .empty-state {
    padding: 20px;
    text-align: center;
    color: var(--text-light);
  }
  
  .notification-list {
    list-style-type: none;
    padding: 0;
    margin: 0;
  }
  
  .notification-item {
    padding: 12px 16px;
    border-bottom: 1px solid var(--border-color);
  }
  
  .notification-item.unread {
    background-color: rgba(59, 130, 246, 0.05);
  }
  
  .notification-item.info {
    border-left: 3px solid var(--info-color);
  }
  
  .notification-item.success {
    border-left: 3px solid var(--success-color);
  }
  
  .notification-item.warning {
    border-left: 3px solid var(--warning-color);
  }
  
  .notification-item.error {
    border-left: 3px solid var(--error-color);
  }
  
  .notification-content p {
    margin: 0 0 5px 0;
    font-size: 0.9rem;
  }
  
  .timestamp {
    font-size: 0.8rem;
    color: var(--text-light);
  }
  
  .panel-footer {
    padding: 12px 16px;
    border-top: 1px solid var(--border-color);
    display: flex;
    justify-content: center;
  }
  
  .mark-read-button {
    background: transparent;
    border: none;
    color: var(--primary-color);
    cursor: pointer;
    font-size: 0.9rem;
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
</style>
