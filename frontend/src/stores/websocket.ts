import { writable, derived, type Writable } from 'svelte/store';
import * as authStore from './auth';
import { downloadStore } from './downloads';

// Define notification types
export type NotificationType = 
  | 'transcription_status' 
  | 'summarization_status'
  | 'analytics_status'
  | 'download_progress'
  | 'connection_established'
  | 'echo';

// Notification interface
export interface Notification {
  id: string;
  type: NotificationType;
  title: string;
  message: string;
  timestamp: Date;
  read: boolean;
  data?: any;
}

// WebSocket connection status
export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error';

// Store state interface
interface WebSocketState {
  socket: WebSocket | null;
  status: ConnectionStatus;
  notifications: Notification[];
  reconnectAttempts: number;
  error: string | null;
}

// Load notifications from localStorage if available
const loadNotificationsFromStorage = (): Notification[] => {
  if (typeof window !== 'undefined') {
    try {
      const stored = localStorage.getItem('notifications');
      if (stored) {
        const parsed = JSON.parse(stored);
        // Convert timestamp strings back to Date objects
        return parsed.map((n: any) => ({
          ...n,
          timestamp: new Date(n.timestamp)
        }));
      }
    } catch (error) {
      console.warn('Failed to load notifications from localStorage:', error);
    }
  }
  return [];
};

// Save notifications to localStorage
const saveNotificationsToStorage = (notifications: Notification[]) => {
  if (typeof window !== 'undefined') {
    try {
      localStorage.setItem('notifications', JSON.stringify(notifications));
    } catch (error) {
      console.warn('Failed to save notifications to localStorage:', error);
    }
  }
};

// Initial state
const initialState: WebSocketState = {
  socket: null,
  status: 'disconnected',
  notifications: loadNotificationsFromStorage(),
  reconnectAttempts: 0,
  error: null
};

// Create the store
function createWebSocketStore() {
  const { subscribe, set, update } = writable<WebSocketState>(initialState);
  
  // Keep track of reconnect timeout
  let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
  
  // Generate notification ID
  const generateId = () => {
    return Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
  };

  // Get current state without subscribing
  const getState = (): WebSocketState => {
    let currentState: WebSocketState = initialState;
    const unsubscribe = subscribe(state => {
      currentState = state;
    });
    unsubscribe();
    return currentState;
  };
  
  // Connect to WebSocket server
  const connect = (token: string) => {
    update((state: WebSocketState) => {
      // Clean up previous connection if exists
      if (state.socket) {
        state.socket.onclose = null;
        state.socket.onerror = null;
        state.socket.onmessage = null;
        state.socket.onopen = null;
        state.socket.close();
      }
      
      // Clear any previous reconnect timeout
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
        reconnectTimeout = null;
      }
      
      try {
        // Always construct WebSocket URL dynamically based on current location
        // This ensures it works in dev, production, and when accessed from different computers
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.host;
        const wsUrl = `${protocol}//${host}/api/ws?token=${token}`;
        
        // Create new WebSocket
        const socket = new WebSocket(wsUrl);
        
        // Set connecting status
        state.status = 'connecting';
        state.socket = socket;
        state.error = null;
        
        // WebSocket event handlers
        socket.onopen = () => {
          update((s: WebSocketState) => {
            s.status = 'connected';
            s.reconnectAttempts = 0;
            return s;
          });
        };
        
        socket.onclose = (event) => {
          update((s: WebSocketState) => {
            s.status = 'disconnected';
            s.socket = null;
            
            // Don't attempt to reconnect if closed cleanly or if page is hidden
            const shouldReconnect = event.code !== 1000 && 
                                  event.code !== 1001 && 
                                  !document.hidden;
            
            if (shouldReconnect) {
              tryReconnect(token);
            }
            
            return s;
          });
        };
        
        socket.onerror = () => {
          update((s: WebSocketState) => {
            s.status = 'error';
            s.error = 'WebSocket connection error';
            return s;
          });
        };
        
        socket.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            
            // Handle different message types
            if (data.type === 'connection_established') {
              // Just a connection confirmation, no notification needed
              return;
            } else if (data.type === 'echo') {
              // Echo messages are just for debugging/heartbeat
              return;
            } else if (data.type === 'download_progress') {
              // Handle download progress messages specially
              handleDownloadProgress(data);
              return;
            }
            
            // Create a notification for other message types
            const notification: Notification = {
              id: generateId(),
              type: data.type as NotificationType,
              title: getNotificationTitle(data.type),
              message: data.data.message || 'No message provided',
              timestamp: new Date(),
              read: false,
              data: data.data
            };
            
            // Add notification
            update((s: WebSocketState) => {
              s.notifications = [notification, ...s.notifications.slice(0, 99)]; // Keep max 100 notifications
              saveNotificationsToStorage(s.notifications);
              return s;
            });
          } catch (error) {
            console.error('Error processing WebSocket message:', error);
          }
        };
      } catch (error) {
        state.status = 'error';
        state.error = 'Failed to connect to WebSocket server';
        console.error('WebSocket connection error:', error);
      }
      
      return state;
    });
  };
  
  // Try to reconnect with exponential backoff
  const tryReconnect = (token: string) => {
    update((state: WebSocketState) => {
      state.reconnectAttempts += 1;
      return state;
    });
    
    // Calculate backoff time (max 30 seconds)
    const backoffTime = Math.min(Math.pow(2, Math.min(10, getState().reconnectAttempts)) * 1000, 30000);
    
    reconnectTimeout = setTimeout(() => {
      connect(token);
    }, backoffTime);
  };
  
  // Disconnect
  const disconnect = () => {
    update((state: WebSocketState) => {
      if (state.socket) {
        state.socket.close(1000, 'User logged out');
        state.socket = null;
      }
      
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
        reconnectTimeout = null;
      }
      
      state.status = 'disconnected';
      return state;
    });
  };
  
  // Send message
  const send = (message: any) => {
    update((state: WebSocketState) => {
      if (state.socket && state.status === 'connected') {
        state.socket.send(JSON.stringify(message));
      } else {
        console.warn('Cannot send message, WebSocket not connected');
      }
      return state;
    });
  };
  
  // Mark notification as read
  const markAsRead = (id: string) => {
    update((state: WebSocketState) => {
      const index = state.notifications.findIndex((n: Notification) => n.id === id);
      if (index !== -1) {
        state.notifications[index].read = true;
        saveNotificationsToStorage(state.notifications);
      }
      return state;
    });
  };
  
  // Mark all notifications as read
  const markAllAsRead = () => {
    update((state: WebSocketState) => {
      state.notifications = state.notifications.map((n: Notification) => ({ ...n, read: true }));
      saveNotificationsToStorage(state.notifications);
      return state;
    });
  };
  
  // Clear all notifications
  const clearAll = () => {
    update((state: WebSocketState) => {
      state.notifications = [];
      saveNotificationsToStorage(state.notifications);
      return state;
    });
  };
  
  // Handle download progress messages
  const handleDownloadProgress = (data: any) => {
    const { file_id, status, progress, error } = data.data;
    
    if (file_id) {
      downloadStore.updateStatus(file_id, status, progress, error);
    }
  };
  
  // Get a suitable title based on notification type
  const getNotificationTitle = (type: string): string => {
    switch (type) {
      case 'transcription_status':
        return 'Transcription Update';
      case 'summarization_status':
        return 'Summarization Update';
      case 'analytics_status':
        return 'Analytics Update';
      case 'download_progress':
        return 'Download Progress';
      default:
        return 'Notification';
    }
  };
  
  return {
    subscribe,
    connect,
    disconnect,
    send,
    markAsRead,
    markAllAsRead,
    clearAll
  };
}

// Create the WebSocket store
export const websocketStore = createWebSocketStore();

// Derived store for unread notifications count
export const unreadCount = derived(
  websocketStore,
  ($websocketStore: WebSocketState) => $websocketStore.notifications.filter((n: Notification) => !n.read).length
);

// Initialize WebSocket when auth changes
authStore.token.subscribe((token: string | null) => {
  if (token) {
    websocketStore.connect(token);
  } else {
    websocketStore.disconnect();
  }
});

// Handle page visibility changes to reconnect when page becomes visible
if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
      // Page became visible, check if we need to reconnect
      let shouldReconnect = false;
      let token: string | null = null;
      
      const unsubscribe = websocketStore.subscribe((state: WebSocketState) => {
        if (state.status === 'disconnected' || state.status === 'error') {
          token = localStorage.getItem('token');
          if (token) {
            shouldReconnect = true;
          }
        }
      });
      unsubscribe();
      
      if (shouldReconnect && token) {
        websocketStore.connect(token);
      }
    }
  });
}
