import { writable, derived, type Writable } from 'svelte/store';
import * as authStore from './auth';
import { downloadStore } from './downloads';

// Define notification types
export type NotificationType =
  | 'transcription_status'
  | 'summarization_status'
  | 'topic_extraction_status'
  | 'youtube_processing_status'
  | 'analytics_status'
  | 'download_progress'
  | 'audio_extraction_status'
  | 'connection_established'
  | 'echo'
  | 'file_upload'
  | 'file_created'
  | 'file_updated'
  | 'file_deleted';

// Notification interface
export interface Notification {
  id: string;
  type: NotificationType;
  title: string;
  message: string;
  timestamp: Date;
  read: boolean;
  data?: any;
  // Progressive notification fields
  progressId?: string; // Used to group progressive notifications
  currentStep?: string; // Current processing step
  progress?: {
    current: number;
    total: number;
    percentage: number;
  };
  status?: 'processing' | 'completed' | 'error';
  dismissible?: boolean; // false while processing
  silent?: boolean; // if true, don't show in notification panel (for gallery-only updates)
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
                                  (typeof document === 'undefined' || !document.hidden);
            
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

            // Handle progressive notifications
            const isProgressiveType = data.type === 'transcription_status' || data.type === 'summarization_status' || data.type === 'topic_extraction_status' || data.type === 'youtube_processing_status';

            // Handle silent notifications (gallery-only updates)
            const isSilentType = data.type === 'file_created' || data.type === 'file_updated';
            
            
            if (isProgressiveType && data.data.file_id) {
              const progressId = `${data.type}_${data.data.file_id}`;
              const currentStep = data.data.message || 'Processing...';
              const status = data.data.status || 'processing';
              const progress = {
                current: Math.floor(data.data.progress || 0),
                total: 100,
                percentage: data.data.progress || 0
              };
              
              
              update((s: WebSocketState) => {
                // Find existing progressive notification
                const existingIndex = s.notifications.findIndex(n => n.progressId === progressId);
                
                if (existingIndex !== -1) {
                  // Update existing notification with new data (important for summary completion)
                  const updatedNotification = {
                    ...s.notifications[existingIndex],
                    message: currentStep,
                    timestamp: new Date(),
                    currentStep,
                    progress,
                    status: status as 'processing' | 'completed' | 'error',
                    dismissible: status === 'completed' || status === 'failed' || status === 'error' || status === 'not_configured' || (data.type === 'youtube_processing_status' && status === 'pending'),
                    read: false, // Mark as unread for updates
                    data: { ...s.notifications[existingIndex].data, ...data.data } // Merge old and new data
                  };
                  
                  // Remove from current position and add to front to maintain most-recent-first ordering
                  s.notifications.splice(existingIndex, 1);
                  s.notifications.unshift(updatedNotification);
                  
                } else {
                  // Create new progressive notification
                  const notification: Notification = {
                    id: generateId(),
                    progressId,
                    type: data.type as NotificationType,
                    title: getNotificationTitle(data.type),
                    message: currentStep,
                    timestamp: new Date(),
                    read: false,
                    data: data.data,
                    currentStep,
                    progress,
                    status: status as 'processing' | 'completed' | 'error',
                    dismissible: status === 'completed' || status === 'failed' || status === 'error' || (data.type === 'youtube_processing_status' && status === 'pending')
                  };
                  
                  s.notifications = [notification, ...s.notifications.slice(0, 99)];
                  
                }
                
                saveNotificationsToStorage(s.notifications);
                return s;
              });
            } else if (isSilentType) {
              // Create a silent notification for gallery updates only
              const notification: Notification = {
                id: generateId(),
                type: data.type as NotificationType,
                title: getNotificationTitle(data.type),
                message: data.data.message || 'Gallery update',
                timestamp: new Date(),
                read: false,
                data: data.data,
                dismissible: true,
                silent: true // This prevents it from showing in notification panel
              };

              // Add notification (MediaLibrary will see it, but NotificationsPanel will filter it out)
              update((s: WebSocketState) => {
                s.notifications = [notification, ...s.notifications.slice(0, 99)];
                // Don't save silent notifications to localStorage to keep it clean
                return s;
              });
            } else {
              // Create a regular notification for other non-progressive types
              const notification: Notification = {
                id: generateId(),
                type: data.type as NotificationType,
                title: getNotificationTitle(data.type),
                message: data.data.message || 'No message provided',
                timestamp: new Date(),
                read: false,
                data: data.data,
                dismissible: true
              };

              // Add notification
              update((s: WebSocketState) => {
                s.notifications = [notification, ...s.notifications.slice(0, 99)]; // Keep max 100 notifications
                saveNotificationsToStorage(s.notifications);
                return s;
              });
            }
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
  
  // Mark notification as read (with auto-regeneration for processing notifications)
  const markAsRead = (id: string) => {
    update((state: WebSocketState) => {
      const index = state.notifications.findIndex((n: Notification) => n.id === id);
      if (index !== -1) {
        const notification = state.notifications[index];
        
        // If it's a processing notification, auto-regenerate it
        if (notification.status === 'processing' && !notification.dismissible) {
          // Mark as read but keep the notification
          state.notifications[index].read = true;
          // Re-add as unread after a short delay (simulated by creating a duplicate)
          setTimeout(() => {
            update((s: WebSocketState) => {
              const stillExists = s.notifications.find(n => n.id === id && n.status === 'processing');
              if (stillExists) {
                stillExists.read = false;
                saveNotificationsToStorage(s.notifications);
              }
              return s;
            });
          }, 100);
        } else {
          // Regular dismissal for completed/error notifications
          state.notifications[index].read = true;
        }
        
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
      case 'topic_extraction_status':
        return 'Topic Extraction';
      case 'youtube_processing_status':
        return 'YouTube Processing';
      case 'analytics_status':
        return 'Analytics Update';
      case 'download_progress':
        return 'Download Progress';
      case 'audio_extraction_status':
        return 'Audio Extraction';
      case 'file_upload':
        return 'File Upload';
      case 'file_created':
        return 'File Created';
      case 'file_updated':
        return 'File Updated';
      case 'file_deleted':
        return 'File Deleted';
      default:
        return 'Notification';
    }
  };

  // Add a notification manually (for client-side events like audio extraction)
  const addNotification = (notification: Omit<Notification, 'id' | 'timestamp' | 'read'>) => {
    update((state: WebSocketState) => {
      const newNotification: Notification = {
        ...notification,
        id: generateId(),
        timestamp: new Date(),
        read: false
      };

      // If this is a progressive notification, check if we should update existing one
      if (notification.progressId) {
        const existingIndex = state.notifications.findIndex(n => n.progressId === notification.progressId);
        if (existingIndex !== -1) {
          // Update existing notification
          state.notifications[existingIndex] = {
            ...state.notifications[existingIndex],
            ...newNotification,
            id: state.notifications[existingIndex].id, // Keep original ID
            timestamp: state.notifications[existingIndex].timestamp, // Keep original timestamp
          };
        } else {
          // Add new notification at the beginning
          state.notifications = [newNotification, ...state.notifications];
        }
      } else {
        // Add new notification at the beginning
        state.notifications = [newNotification, ...state.notifications];
      }

      saveNotificationsToStorage(state.notifications);
      return state;
    });
  };

  // Update an existing notification (for progressive updates)
  const updateNotification = (progressId: string, updates: Partial<Notification>) => {
    update((state: WebSocketState) => {
      const existingIndex = state.notifications.findIndex(n => n.progressId === progressId);
      if (existingIndex !== -1) {
        state.notifications[existingIndex] = {
          ...state.notifications[existingIndex],
          ...updates
        };
        saveNotificationsToStorage(state.notifications);
      }
      return state;
    });
  };
  
  // Remove notification (with auto-regeneration for processing notifications)
  const removeNotification = (id: string) => {
    update((state: WebSocketState) => {
      const notification = state.notifications.find(n => n.id === id);
      
      if (notification && notification.status === 'processing' && !notification.dismissible) {
        // Auto-regenerate processing notifications
        setTimeout(() => {
          update((s: WebSocketState) => {
            // Only re-add if it doesn't already exist
            const exists = s.notifications.find(n => n.progressId === notification.progressId && n.status === 'processing');
            if (!exists) {
              const regenerated: Notification = {
                ...notification,
                id: generateId(),
                timestamp: new Date(),
                read: false
              };
              s.notifications = [regenerated, ...s.notifications];
              saveNotificationsToStorage(s.notifications);
            }
            return s;
          });
        }, 100);
      }
      
      // Remove the notification
      state.notifications = state.notifications.filter(n => n.id !== id);
      saveNotificationsToStorage(state.notifications);
      return state;
    });
  };

  return {
    subscribe,
    connect,
    disconnect,
    send,
    markAsRead,
    markAllAsRead,
    clearAll,
    removeNotification,
    addNotification,
    updateNotification
  };
}

// Create the WebSocket store
export const websocketStore = createWebSocketStore();

// Derived store for unread notifications count (excluding silent notifications)
export const unreadCount = derived(
  websocketStore,
  ($websocketStore: WebSocketState) => $websocketStore.notifications.filter((n: Notification) => !n.read && !n.silent).length
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
