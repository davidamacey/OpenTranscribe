/**
 * WebSocket service for real-time communication with the backend
 * Handles connection, reconnection, and message processing
 */
import { writable } from 'svelte/store';

// Store for WebSocket status
export const wsStatus = writable('disconnected');
// Store for last received notification
export const lastNotification = writable(null);
// Store for file status updates
export const fileStatusUpdates = writable({});
// Store for unread notification count
export const unreadCount = writable(0);

// Connection config
const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_INTERVAL = 3000;

let socket = null;
let reconnectAttempts = 0;
let reconnectTimer = null;
let apiBaseUrl = '';
let currentAuthToken = null;

/**
 * Set up the WebSocket connection to the backend
 * @param {string} baseUrl - API base URL
 * @param {string} authToken - Authentication token (optional)
 */
export function setupWebsocketConnection(baseUrl, authToken = null) {
  apiBaseUrl = baseUrl;
  currentAuthToken = authToken;
  
  // Clear any existing connection
  if (socket) {
    socket.close();
    socket = null;
  }
  
  // Clear any reconnect timer
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  
  reconnectAttempts = 0;
  connectWebsocket(authToken);
}

/**
 * Create WebSocket connection
 * @param {string} authToken - Authentication token (optional)
 */
function connectWebsocket(authToken = null) {
  try {
    // Set connection status
    wsStatus.set('connecting');
    
    // Determine WebSocket URL - use same host as HTTP requests
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host; // This includes port if present
    
    // Use the same host/port that serves the frontend
    // The proxy will handle routing to the backend
    const wsUrl = `${protocol}//${host}/api/ws`;
    
    // Add auth token if provided
    const url = authToken ? `${wsUrl}?token=${authToken}` : wsUrl;
    
    
    // Create WebSocket connection
    socket = new WebSocket(url);
    
    // Handle connection events
    socket.addEventListener('open', handleOpen);
    socket.addEventListener('message', handleMessage);
    socket.addEventListener('error', handleError);
    socket.addEventListener('close', handleClose);
    
    // WebSocket: Attempting connection
  } catch (error) {
    console.error('WebSocket: Connection error', error);
    wsStatus.set('error');
    scheduleReconnect();
  }
}

/**
 * Handle successful WebSocket connection
 */
function handleOpen() {
  wsStatus.set('connected');
  reconnectAttempts = 0;
}

/**
 * Handle incoming WebSocket messages
 * @param {MessageEvent} event - WebSocket message event
 */
function handleMessage(event) {
  try {
    const message = JSON.parse(event.data);
    
    // Update last notification store
    lastNotification.set(message);
    
    // Update unread count
    unreadCount.update(count => count + 1);
    
    // Handle specific message types
    
    if (message.type === 'transcription_status') {
      const fileUpdate = message.data;
      
      // Convert file_id to string for consistent storage (backend sends as string)
      const fileId = String(fileUpdate.file_id);
      
      // Update the file status store
      fileStatusUpdates.update(statuses => {
        const newStatuses = {
          ...statuses,
          [fileId]: {
            file_id: parseInt(fileId), // Convert back to number for frontend use
            status: fileUpdate.status,
            progress: fileUpdate.progress || 100
          }
        };
        return newStatuses;
      });
    }
  } catch (error) {
    console.error('WebSocket: Error processing message', error);
  }
}

/**
 * Handle WebSocket errors
 * @param {Event} event - WebSocket error event
 */
function handleError(event) {
  console.error('WebSocket: Error event', event);
  wsStatus.set('error');
}

/**
 * Handle WebSocket connection close
 * @param {CloseEvent} event - WebSocket close event
 */
function handleClose(event) {
  wsStatus.set('disconnected');
  socket = null;
  
  // Don't reconnect if this was a deliberate close
  if (event.code === 1000) {
    return;
  }
  
  // Attempt to reconnect
  scheduleReconnect();
}

/**
 * Schedule WebSocket reconnection attempt
 */
function scheduleReconnect() {
  if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
    reconnectAttempts++;
    
    reconnectTimer = setTimeout(() => {
      connectWebsocket(currentAuthToken);
    }, RECONNECT_INTERVAL);
  } else {
    wsStatus.set('failed');
  }
}
