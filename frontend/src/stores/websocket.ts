import { writable, derived, type Writable } from 'svelte/store';
import * as authStore from './auth';

// Define notification types
export type NotificationType = 
  | 'transcription_status' 
  | 'summarization_status'
  | 'analytics_status'
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

// Initial state
const initialState: WebSocketState = {
  socket: null,
  status: 'disconnected',
  notifications: [],
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
        // Construct WebSocket URL with token
        // Use environment variable if available, otherwise fall back to dynamic construction
        const wsBaseUrl = import.meta.env.VITE_WS_BASE_URL;
        let wsUrl;
        
        if (wsBaseUrl) {
          // Use configured WebSocket base URL
          wsUrl = `${wsBaseUrl}?token=${token}`;
        } else {
          // Fall back to dynamic construction for development
          const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
          const baseUrl = window.location.host;
          wsUrl = `${protocol}//${baseUrl}/api/ws?token=${token}`;
        }
        
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
            
            // Don't attempt to reconnect if closed cleanly
            if (event.code !== 1000 && event.code !== 1001) {
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
  
  // Get current state without subscribing
  const getState = (): WebSocketState => {
    let currentState: WebSocketState = initialState;
    const unsubscribe = subscribe(state => {
      currentState = state;
    });
    unsubscribe();
    return currentState;
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
      }
      return state;
    });
  };
  
  // Mark all notifications as read
  const markAllAsRead = () => {
    update((state: WebSocketState) => {
      state.notifications = state.notifications.map((n: Notification) => ({ ...n, read: true }));
      return state;
    });
  };
  
  // Clear all notifications
  const clearAll = () => {
    update((state: WebSocketState) => {
      state.notifications = [];
      return state;
    });
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
