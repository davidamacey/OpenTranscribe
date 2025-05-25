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

// Connection config
const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_INTERVAL = 3000;

let socket = null;
let reconnectAttempts = 0;
let reconnectTimer = null;
let apiBaseUrl = '';

/**
 * Set up the WebSocket connection to the backend
 * @param {string} baseUrl - API base URL
 * @param {string} authToken - Authentication token (optional)
 */
export function setupWebsocketConnection(baseUrl, authToken = null) {
  apiBaseUrl = baseUrl;
  
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
    
    // Determine WebSocket URL
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
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
    
    console.log('WebSocket: Attempting connection to', wsUrl);
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
  console.log('WebSocket: Connected successfully');
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
    console.log('WebSocket: Received message', message);
    
    // Update last notification store
    lastNotification.set(message);
    
    // Handle specific message types
    if (message.type === 'transcription_status') {
      const fileUpdate = message.data;
      
      // Update the file status store
      fileStatusUpdates.update(statuses => {
        return {
          ...statuses,
          [fileUpdate.file_id]: fileUpdate
        };
      });
      
      console.log(`WebSocket: Updated file ${fileUpdate.file_id} status to ${fileUpdate.status}`);
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
  console.log(`WebSocket: Connection closed (code: ${event.code}, reason: ${event.reason})`);
  wsStatus.set('disconnected');
  socket = null;
  
  // Attempt to reconnect
  scheduleReconnect();
}

/**
 * Schedule WebSocket reconnection attempt
 */
function scheduleReconnect() {
  if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
    reconnectAttempts++;
    
    console.log(`WebSocket: Scheduling reconnect attempt ${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS} in ${RECONNECT_INTERVAL}ms`);
    
    reconnectTimer = setTimeout(() => {
      console.log(`WebSocket: Attempting reconnect ${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS}`);
      connectWebsocket();
    }, RECONNECT_INTERVAL);
  } else {
    console.error('WebSocket: Maximum reconnect attempts reached');
    wsStatus.set('failed');
  }
}
