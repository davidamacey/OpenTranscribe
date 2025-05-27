<script>
  import { onMount, createEventDispatcher, tick } from 'svelte';
  import { slide } from 'svelte/transition';
  import { fly } from 'svelte/transition';
  // Use the shared axios instance so auth token is always sent
  import axiosInstance from '../lib/axios';
  import { authStore } from '../stores/auth';
  import TruncatedText from './TruncatedText.svelte';
  
  // The Svelte component is exported by default automatically
  
  /** @type {string} */
  export let fileId = "";
  /** @type {number} */
  export let currentTime = 0;
  
  /** @type {Array<{id: number, text: string, timestamp: number, user: {id: number, email?: string, full_name?: string, username?: string}, created_at: string}>} */
  let comments = [];
  /** @type {boolean} */
  let loading = true;
  /** @type {string|null} */
  let error = null;
  /** @type {string} */
  let newComment = '';
  /** @type {number|null} */
  let timestampInput = null;
  /** @type {number|null} */
  let editingCommentId = null;
  /** @type {string} */
  let editingCommentText = '';
  
  // Event dispatcher
  const dispatch = createEventDispatcher();
  
  // Fetch comments for the file
  onMount(() => {
    fetchComments();
  });
  
  async function fetchComments() {
    loading = true;
    error = null;
    try {
      // Get auth token from localStorage
      const token = localStorage.getItem('token');
      // Make sure we have a valid numeric file ID
      const numericFileId = Number(fileId);
      
      // Validate fileId is a valid number
      if (isNaN(numericFileId) || numericFileId <= 0) {
        console.error('%c [COMMENTS DEBUG] Invalid file ID:', 'background: #222; color: #ff6b6b; font-size: 14px;', fileId);
        error = 'Invalid file ID provided';
        loading = false;
        return;
      }
      
      if (!token) {
        console.error('%c [COMMENTS DEBUG] No auth token found in localStorage', 'background: #222; color: #ff6b6b; font-size: 14px;');
        error = 'You need to be logged in to view comments';
        loading = false;
        return;
      }
      
      console.log('%c [COMMENTS DEBUG] Fetching comments for file ' + numericFileId + ' with token present: ' + !!token, 'background: #222; color: #bada55; font-size: 14px');
      
      // Create custom headers with authentication token
      const headers = {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      };
      
      // Use the endpoint confirmed to be working in the API debugger
      let response;
      try {
        // Use the correct endpoint structure: /comments/files/{fileId}/comments
        const endpoint = `/comments/files/${numericFileId}/comments`;
        response = await axiosInstance.get(endpoint, { headers });
      } catch (/** @type {any} */ error) {
        // Log error information for debugging
        console.error('Error fetching comments:', error?.message, error?.response?.status, error?.response?.data);
        
        // If the error is a 401, this is an authentication issue
        if (error.response?.status === 401) {
          error = 'You need to be logged in to view comments';
          loading = false;
          return;
        }
        
        // Try alternate endpoints as fallback
        if (error.response?.status === 404) {
          try {
            // Try the legacy endpoint without leading slash as fallback
            console.log('%c [COMMENTS DEBUG] Trying legacy endpoint', 'background: #222; color: #ff9a3c; font-size: 14px;');
            response = await axiosInstance.get(`files/${numericFileId}/comments`, { headers });
            console.log('%c [COMMENTS DEBUG] Successfully fetched comments using legacy endpoint', 'background: #222; color: #6bff6b; font-size: 14px;');
          } catch (/** @type {any} */ legacyError) {
            try {
              // If that fails, try the query parameter approach as last resort
              console.log('%c [COMMENTS DEBUG] Trying query parameter approach as last resort', 'background: #222; color: #ff9a3c; font-size: 14px;');
              response = await axiosInstance.get('/comments', { 
                params: { media_file_id: numericFileId },
                headers 
              });
              console.log('%c [COMMENTS DEBUG] Successfully fetched comments using query param', 'background: #222; color: #6bff6b; font-size: 14px;');
            } catch (/** @type {any} */ lastError) {
              console.error('[CommentSection] All endpoints failed');
              error = `Failed to load comments: ${lastError.message}`;
              return;
            }
          }
        } else {
          error = `Failed to load comments: ${error.message}`;
          return;
        }
      }
      
      console.log('[CommentSection] Comments response:', response.status, response.headers);
      
      // Process comments to ensure they have user information
      console.log('%c [COMMENTS DEBUG] Processing ' + response.data.length + ' comments', 'background: #222; color: #bada55; font-size: 14px;');
      comments = response.data.map(/** @param {any} comment */ (comment) => {
        // If comment has no user info, add it from the stored user data
        if (!comment.user) {
          const userData = JSON.parse(localStorage.getItem('user') || '{}');
          return {
            ...comment,
            user: {
              id: comment.user_id,
              email: userData.email,
              full_name: userData.full_name || userData.email || 'User ' + comment.user_id
            }
          };
        }
        return comment;
      });
      
      if (!Array.isArray(comments) || comments.length === 0) {
        console.log('[CommentSection] No comments found for this file.');
      } else {
        console.log(`%c [COMMENTS DEBUG] Successfully processed ${comments.length} comments`, 'background: #222; color: #6bff6b; font-size: 14px; font-weight: bold;');
      }
      
      // Sort by timestamp
      comments.sort((/** @type {{timestamp: number}} */ a, /** @type {{timestamp: number}} */ b) => a.timestamp - b.timestamp);
    } catch (/** @type {any} */ err) { // Handle error with proper type
      console.error('[CommentSection] Error fetching comments:', err);
      console.error('[CommentSection] Error details:', {
        message: err.message,
        response: err.response,
        status: err.response?.status,
        data: err.response?.data
      });
      
      // Provide a more user-friendly error message
      if (err.response && err.response.status === 401) {
        error = 'You need to be logged in to view comments.';
      } else if (err.code === 'ERR_NETWORK') {
        error = 'Network error: Cannot connect to server.';
      } else {
        error = `Failed to load comments: ${err.message}`;
      }
    } finally {
      loading = false;
    }
  }
  
  // Add a new comment
  /** @param {Event=} event - Optional event parameter */
  async function addComment(event) {
    // Always prevent default form submission behavior
    if (event) {
      event.preventDefault();
      event.stopPropagation();
    }
    
    console.log('[CommentSection] Adding comment with button click');
    
    if (!newComment.trim()) return;
    
    // Use the timestamp input if it was explicitly set, otherwise use null
    const timestamp = timestampInput !== null ? timestampInput : null;
    
    // If timestamp is null at this point, inform the user they need to mark a time
    if (timestamp === null) {
      error = 'Please use "Mark Current Time" to set a timestamp for your comment.';
      return;
    }
    
    // Store locally for optimistic UI updates
    const commentText = newComment.trim();
    const currentTimestamp = timestamp;
    try {
      // Get user data from localStorage
      const userData = JSON.parse(localStorage.getItem('user') || '{}');
      
      // Get auth token from localStorage
      const token = localStorage.getItem('token');
      const numericFileId = Number(fileId);
      
      console.log('[CommentSection] Adding comment for file', numericFileId, 'with token present:', !!token);
      console.log('[CommentSection] Comment data:', { text: newComment, timestamp, media_file_id: numericFileId });

      if (!token) {
        console.error('[CommentSection] No auth token found in localStorage');
        error = 'You need to be logged in to add comments';
        return;
      }

      // Create custom headers with authentication token
      const headers = {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      };

      // Prepare the comment data
      const commentData = {
        text: newComment,
        timestamp,
        media_file_id: numericFileId
      };
      
      // Use the endpoint confirmed to be working in the API debugger
      let response;
      try {
        // The correct endpoint without leading slash (baseURL is '/api')
        // This will become /api/comments/files/{fileId}/comments
        const endpoint = `comments/files/${numericFileId}/comments`;
        console.log('%c [COMMENTS DEBUG] Adding comment with endpoint:', 'background: #222; color: #bada55; font-size: 14px;', endpoint);
        
        // Log the full URL that will be used
        const baseURL = axiosInstance.defaults.baseURL || '';
        const fullURL = baseURL + (baseURL.endsWith('/') ? '' : '/') + endpoint;
        console.log('%c [COMMENTS DEBUG] Full URL for adding comment:', 'background: #222; color: #bada55; font-size: 14px;', fullURL);
        
        // The backend expects media_file_id in the payload even though it's in the URL path
        const commentPayload = {
          text: newComment,
          timestamp: timestamp,
          media_file_id: numericFileId // Required by the CommentCreate schema
        };
        
        // Ensure token is included in the headers
        response = await axiosInstance.post(endpoint, commentPayload, { headers });
        
        console.log('[CommentSection] Successfully added comment');
      } catch (/** @type {any} */ error) {
        // Log detailed error information for debugging
        console.error('[CommentSection] Error adding comment:', error);
        console.error('[CommentSection] Error response:', 
          error.response?.status, 
          error.response?.data
        );
        
        // If the error is a 401, this is an authentication issue
        if (error.response?.status === 401) {
          error = 'You need to be logged in to add comments';
          return;
        }
        
        // Try alternate endpoints as fallback if we get a 404
        if (error.response?.status === 404) {
          try {
            // Try the legacy endpoint approach without leading slash
            console.log('%c [COMMENTS DEBUG] Trying legacy endpoint for adding comment', 'background: #222; color: #ff9a3c; font-size: 14px;');
            const legacyPayload = {
              text: newComment,
              timestamp: timestamp,
              media_file_id: numericFileId // Required by the CommentCreate schema
            };
            response = await axiosInstance.post(`files/${numericFileId}/comments`, legacyPayload, { headers });
            console.log('[CommentSection] Successfully added comment using main endpoint');
          } catch (/** @type {any} */ legacyError) {
            try {
              // Try the query parameter endpoint as last resort
              console.log('%c [COMMENTS DEBUG] Trying query parameter endpoint as last resort', 'background: #222; color: #ff9a3c; font-size: 14px;');
              response = await axiosInstance.post('comments', {
                text: newComment,
                timestamp,
                media_file_id: numericFileId // Required by the CommentCreate schema
              }, { headers });
              console.log('[CommentSection] Successfully added comment using root endpoint');
            } catch (/** @type {any} */ lastError) {
              console.error('[CommentSection] All endpoints failed for adding comment');
              error = `Failed to add comment: ${lastError.message}`;
              return;
            }
          }
        } else {
          error = `Failed to add comment: ${error.message}`;
          return;
        }
      }
      
      console.log('[CommentSection] Comment added:', response.data);
      
      // Ensure the comment has a user object with username
      const commentWithUser = {
        ...response.data,
        // Add user info from localStorage if not present in the response
        user: response.data.user || {
          id: response.data.user_id || userData.id || 0,
          email: userData.email,
          full_name: userData.full_name || userData.email || 'User ' + response.data.user_id
        }
      };
      
      comments = [...comments, commentWithUser];
      comments.sort((a, b) => Number(a.timestamp) - Number(b.timestamp));
      newComment = '';
      timestampInput = null;
      dispatch('commentAdded', commentWithUser);
    } catch (/** @type {any} */ err) { // Handle error with proper type
      console.error('[CommentSection] Error adding comment:', err);
      console.error('[CommentSection] Error details:', {
        message: err.message,
        response: err.response,
        status: err.response?.status,
        data: err.response?.data
      });
      
      // Provide a more user-friendly error message
      if (err.response && err.response.status === 401) {
        error = 'You need to be logged in to add comments.';
      } else if (err.code === 'ERR_NETWORK') {
        error = 'Network error: Cannot connect to server.';
      } else {
        error = `Failed to add comment: ${err.message}`;
      }
    }
  }
  
  // Edit a comment
  /**
   * Set a comment for editing
   * @param {number} id - The ID of the comment to edit
   * @param {string} text - The current text of the comment
   */
  function startEditing(id, text) {
    editingCommentId = id;
    editingCommentText = text;
  }
  
  /**
   * Cancel editing a comment
   */
  function cancelEditing() {
    editingCommentId = null;
    editingCommentText = '';
  }
  
  /**
   * Save edited comment
   */
  function saveEdit() {
    if (editingCommentId === null) return;
    editComment(editingCommentId, editingCommentText);
  }

  /**
   * Edit an existing comment
   * @param {number} commentId - The ID of the comment to edit
   * @param {string} newText - The new text for the comment
   */
  async function editComment(commentId, newText) {
    if (!newText || !newText.trim()) {
      error = 'Comment text cannot be empty';
      return;
    }
    
    try {
      console.log('[CommentSection] Editing comment:', commentId, newText);
      
      // Get auth token from localStorage
      const token = localStorage.getItem('token');
      
      if (!token) {
        error = 'You need to be logged in to edit comments';
        return;
      }
      
      // Create custom headers with authentication token
      const headers = {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      };
      
      // Use PUT as the backend expects PUT for updates
      // The backend route is /comments/{comment_id} - need to include the full path
      // Adding detailed debug logging to track the request
      console.log('%c [COMMENTS DEBUG] Editing comment ' + commentId + ' with text: ' + newText, 'background: #222; color: #bada55; font-size: 14px;');
      
      // Log detailed request info
      const isDevMode = typeof window !== 'undefined' && window.location.hostname === 'localhost';
      if (isDevMode) {
        console.log('%c [COMMENTS DEBUG] Request details:', 'background: #222; color: #bada55; font-size: 14px;', {
          url: `comments/${commentId}`,
          baseURL: axiosInstance.defaults.baseURL,
          headers: headers,
          data: { text: newText }
        });
      }
      
      const response = await axiosInstance.put(`comments/${commentId}`, {
        text: newText
      }, { headers });
      
      console.log('[CommentSection] Comment edited successfully');
      
      // Update the comment in the list
      comments = comments.map(c => c.id === commentId ? { ...c, text: newText } : c);
      
      // Reset editing state if we were editing this comment
      if (editingCommentId === commentId) {
        editingCommentId = null;
        editingCommentText = '';
      }
      
    } catch (/** @type {any} */ err) {
      console.error('[CommentSection] Error editing comment:', err);
      console.error('[CommentSection] Error details:', {
        message: err.message,
        response: err.response,
        status: err.response?.status,
        data: err.response?.data
      });
      
      // Provide a more user-friendly error message
      if (err.response && err.response.status === 401) {
        error = 'You need to be logged in to edit comments.';
      } else {
        error = `Failed to edit comment: ${err.message}`;
      }
    }
  }
  
  // Delete a comment
  /**
   * Delete a comment by ID
   * @param {number} commentId - The ID of the comment to delete
   */
  /**
   * Delete a comment
   * @param {number} commentId - The ID of the comment to delete
   */
  async function deleteComment(commentId) {
    if (!confirm('Are you sure you want to delete this comment?')) return;
    
    try {
      // Get auth token from localStorage
      const token = localStorage.getItem('token');
      console.log('[CommentSection] Deleting comment', commentId, 'with token:', token ? token.substring(0, 8) + '...' : '[none]');
      
      if (!token) {
        error = 'You need to be logged in to delete comments';
        return;
      }
      
      // Create custom headers with authentication token
      const headers = {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      };
      
      // The correct endpoint is under the comments router without leading slash
      console.log('%c [COMMENTS DEBUG] Deleting comment ' + commentId, 'background: #222; color: #ff9a3c; font-size: 14px;');
      
      // Log detailed request info
      const isDevMode = typeof window !== 'undefined' && window.location.hostname === 'localhost';
      if (isDevMode) {
        console.log('%c [COMMENTS DEBUG] Delete request details:', 'background: #222; color: #ff9a3c; font-size: 14px;', {
          url: `comments/${commentId}`,
          baseURL: axiosInstance.defaults.baseURL,
          headers: headers
        });
      }
      
      await axiosInstance.delete(`comments/${commentId}`, { headers });
      console.log('%c [COMMENTS DEBUG] Comment deleted successfully', 'background: #222; color: #6bff6b; font-size: 14px;');
      
      comments = comments.filter(c => c.id !== commentId);
    } catch (/** @type {any} */ err) { // Handle error with proper type
      console.error('[CommentSection] Error deleting comment:', err);
      console.error('[CommentSection] Error details:', {
        message: err.message,
        response: err.response,
        status: err.response?.status,
        data: err.response?.data
      });
      
      // Provide a more user-friendly error message
      if (err.response && err.response.status === 401) {
        error = 'You need to be logged in to delete comments.';
      } else {
        error = `Failed to delete comment: ${err.message}`;
      }
    }
  }
  
  // Format timestamp as MM:SS
  /**
   * Format timestamp as MM:SS
   * @param {number} seconds - The timestamp in seconds
   * @returns {string} Formatted timestamp
   */
  function formatTimestamp(seconds) {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
  }
  
  // Use the current playback time
  /** @param {Event} event */
  function useCurrentTime(event) {
    // Prevent default button behavior
    if (event && event.preventDefault) {
      event.preventDefault();
    }
    
    // Get the current time directly from the player
    // This ensures we get the exact current time from the player
    timestampInput = currentTime;
    console.log('[CommentSection] Set timestamp to current time:', timestampInput);
  }
  
  // Check if the current user is the author of a comment
  /**
   * Check if the current user is the author of a comment
   * @param {number} userId - The user ID to check
   * @returns {boolean} Whether the current user is the author
   */
  function isCommentAuthor(userId) {
    if (!$authStore.user) return false;
    
    // Convert both to numbers for comparison to avoid string vs number comparison issues
    return Number($authStore.user.id) === Number(userId);
  }
</script>

<!-- Main wrapper with fixed header and scrollable comments -->
<div class="comments-wrapper">
  <!-- Error message if needed -->
  {#if error}
    <div class="error-message">
      <p>{error}</p>
      <button on:click={fetchComments}>Try Again</button>
    </div>
  {/if}
  
  <!-- Fixed comment form at the top -->
  <div class="comment-form-container">
    <form class="comment-form" on:submit={addComment}>
      <textarea
        bind:value={newComment}
        placeholder="Add your comment here..."
        rows="2"
      ></textarea>
      <div class="form-actions">
        <div class="timestamp-actions">
          {#if timestampInput === null}
            <button
              type="button"
              class="timestamp-button"
              on:click={useCurrentTime}
            >
              <span class="button-icon">⏱</span>
              <span>Mark Current Time</span>
            </button>
          {:else}
            <div class="current-timestamp">
              <span class="timestamp-value">Marked {formatTimestamp(timestampInput)}</span>
              <button
                type="button"
                class="clear-button"
                on:click|stopPropagation={() => timestampInput = null}
                title="Clear timestamp"
              >
                ✖
              </button>
            </div>
          {/if}
        </div>
        <button type="submit" class="submit-button" disabled={!newComment.trim()}>
          Add Comment
        </button>
      </div>
    </form>
  </div>
  
  <!-- Scrollable comments list container -->
  <div class="comments-list-container">
    {#if loading && comments.length === 0}
      <div class="loading-state">
        <p>Loading comments...</p>
      </div>
    {:else if comments.length === 0}
      <div class="empty-state">
        <p>No comments yet. Be the first to add one!</p>
      </div>
    {:else}
      {#each comments as comment (comment.id)}
        <div class="comment-item" transition:slide={{duration: 300}}>
          <div class="comment-header">
            <div class="comment-user">
              {comment.user ? (comment.user.full_name || comment.user.email || `User ${comment.user.id}`) : 'Anonymous'}
            </div>
            <div class="comment-timestamp">
              {#if comment.timestamp !== null}
                <button
                  type="button"
                  class="timestamp-link"
                  on:click={() => dispatch('seekTo', comment.timestamp)}
                  on:keydown={(e) => e.key === 'Enter' && dispatch('seekTo', comment.timestamp)}
                  aria-label="Jump to timestamp {formatTimestamp(comment.timestamp)}"
                >
                  {formatTimestamp(comment.timestamp)}
                </button>
              {/if}
              <span>{new Date(comment.created_at).toLocaleDateString()}</span>
            </div>
          </div>
          
          {#if editingCommentId === comment.id}
            <form class="edit-comment-form" on:submit|preventDefault={() => editComment(comment.id, editingCommentText)}>
              <textarea
                bind:value={editingCommentText}
                rows="2"
              ></textarea>
              <div class="edit-buttons">
                <button type="button" class="cancel-button" on:click={() => editingCommentId = null}>
                  Cancel
                </button>
                <button type="submit" class="save-button">
                  Save
                </button>
              </div>
            </form>
          {:else}
            <div class="comment-body">
              <TruncatedText text={comment.text} maxLength={150} />
            </div>
            
            <!-- Only show edit/delete for comment author -->
            {#if isCommentAuthor(comment.user.id)}
              <div class="comment-actions">
                <button 
                  type="button"
                  class="edit-button" 
                  on:click={() => {
                    editingCommentId = comment.id;
                    editingCommentText = comment.text;
                  }}
                >
                  Edit
                </button>
                <button 
                  type="button"
                  class="delete-button"
                  on:click={() => deleteComment(comment.id)}
                >
                  Delete
                </button>
              </div>
            {/if}
          {/if}
        </div>
      {/each}
    {/if}
  </div>
</div>

<style>
  /* Main wrapper for the entire comments component */
  .comments-wrapper {
    display: flex;
    flex-direction: column;
    gap: 0;
    background-color: var(--background-color, #1e1e1e);
    border-radius: 12px;
    border: 1px solid rgba(120, 120, 120, 0.2);
    max-height: 600px; /* Maximum height for the entire component */
    overflow: hidden; /* Hide overflow, only the list will scroll */
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
  }
  
  /* Fixed comment form container at the top */
  .comment-form-container {
    position: sticky;
    top: 0;
    z-index: 5;
    background-color: var(--background-color, #1e1e1e);
    padding: 0.75rem;
    border-bottom: 1px solid var(--border-color);
  }
  
  /* Scrollable comments list container */
  .comment-form {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    width: 100%;
  }
  
  .comments-list-container {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    overflow-y: auto; /* Only this container will scroll */
    padding: 0.75rem;
    max-height: 400px; /* Maximum height for scrollable area */
    background-color: var(--background-color, #1e1e1e);
  }
  
  .comment-form-container {
    flex-shrink: 0; /* Prevent form from shrinking */
    margin-bottom: 1rem;
    border-bottom: 1px solid var(--border-color);
    padding-bottom: 1rem;
  }
  
  .comments-list-container {
    flex: 1; /* Take remaining space */
    overflow-y: auto; /* Add scroll to container */
    border-radius: 4px;
    padding-right: 0.5rem;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }
  
  .comment-form {
    background-color: rgba(255, 255, 255, 0.05);
    padding: 0.75rem;
    border-radius: var(--border-radius);
    border: 1px solid var(--border-color-soft);
  }

  textarea {
    width: 100%;
    padding: 0.85rem;
    border: 1px solid rgba(120, 120, 120, 0.2);
    border-radius: 10px;
    resize: vertical;
    min-height: 70px;
    font-family: inherit;
    font-size: 0.95rem;
    line-height: 1.5;
    margin-bottom: 0.75rem;
    background-color: rgba(255, 255, 255, 0.05);
    color: var(--text-color);
    box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.05);
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
  }
  
  textarea:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15);
  }



  .form-actions {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-top: 0.5rem;
    flex-wrap: wrap;
    gap: 0.5rem;
  }
  
  .timestamp-actions {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
    max-width: 100%;
    min-height: 2.5rem;
  }
  
  .timestamp-button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    background-color: rgba(59, 130, 246, 0.1);
    border: 1px solid rgba(59, 130, 246, 0.3);
    border-radius: 8px;
    color: var(--primary-color);
    padding: 0.5rem 1rem;
    font-size: 0.9rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    white-space: nowrap;
    height: 2.5rem;
  }
  
  .timestamp-button:hover {
    background-color: rgba(59, 130, 246, 0.2);
    border-color: var(--primary-color);
  }
  
  .button-icon {
    font-size: 1.1rem;
    display: flex;
    align-items: center;
  }
  
  .timestamp-link {
    background: none;
    border: 1px solid rgba(59, 130, 246, 0.2);
    padding: 0.2rem 0.4rem;
    border-radius: 4px;
    font-size: 0.85rem;
    color: var(--primary-color);
    cursor: pointer;
    transition: background-color 0.15s ease;
    font-weight: 500;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    white-space: nowrap;
  }
  
  .current-timestamp {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.75rem;
    background-color: rgba(59, 130, 246, 0.1);
    border: 1px solid rgba(59, 130, 246, 0.3);
    border-radius: 8px;
    color: var(--primary-color);
    padding: 0.5rem 1rem;
    font-size: 0.9rem;
    font-weight: 500;
    height: 2.5rem;
    white-space: nowrap;
  }
  
  .timestamp-value {
    font-weight: 500;
    color: var(--primary-color);
  }
  
  .clear-button {
    background: none;
    border: none;
    color: var(--text-color-secondary);
    cursor: pointer;
    width: 1.5rem;
    height: 1.5rem;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    padding: 0;
    margin-left: 0.5rem;
    opacity: 0.7;
    transition: all 0.2s ease;
  }

  .clear-button:hover {
    color: var(--error-color);
    background-color: rgba(239, 68, 68, 0.1);
    opacity: 1;
    transform: scale(1.1);
  }
  
  button {
    padding: 0.35rem 0.75rem;
    border: none;
    background-color: var(--primary-color);
    color: white;
    border-radius: 4px;
    cursor: pointer;
    font-weight: 500;
    transition: background-color 0.2s;
    margin: 0;
    white-space: nowrap;
    font-size: 0.85rem;
  }

  button:hover {
    background-color: var(--primary-color-dark);
  }
  
  button:disabled {
    background-color: var(--disabled-color, #a0aec0);
    cursor: not-allowed;
  }
  
  .submit-button {
    background-color: #3b82f6; /* Use explicit color instead of variable */
    color: white !important; /* Force white text */
    border: none;
    padding: 0.6rem 1.2rem;
    border-radius: 10px;
    font-size: 0.95rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }
  
  .submit-button:hover:not(:disabled),
  .submit-button:focus:not(:disabled),
  .submit-button:active:not(:disabled) {
    background-color: #2563eb; /* Darker blue on hover */
    color: white !important; /* Force white text on hover */
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
    text-decoration: none !important;
  }
  
  .submit-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  
  /* Styles for comments items within the list container */
  .comments-list-container {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }
  
  /* Comment form stays fixed at top */
  .comment-form-container {
    position: sticky;
    top: 0;
    background-color: var(--background-color-light);
    padding-bottom: 0.5rem;
    margin-bottom: 0.5rem;
    z-index: 5;
  }
  
  .comment-form {
    width: 100%;
    margin-bottom: 0;
  }
  
  .comment-item {
    padding: 1rem;
    border: 1px solid rgba(120, 120, 120, 0.15);
    border-radius: 10px;
    background-color: var(--surface-color, #333333);
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
    margin-bottom: 0.75rem;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
  }
  
  .comment-item:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.12);
  }
  
  .comment-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.5rem;
    font-size: 0.9rem;
  }
  
  .comment-timestamp {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: var(--text-light);
    font-size: 0.8rem;
  }
  
  .timestamp-link {
    color: var(--primary-color);
    cursor: pointer;
  }
  
  .timestamp-link:hover {
    text-decoration: none;
    background-color: rgba(59, 130, 246, 0.1);
    color: var(--primary-color-dark);
    border-color: var(--primary-color);
  }
  
  .comment-body {
    font-size: 0.9rem;
    line-height: 1.5;
    margin-bottom: 0.5rem;
  }
  
  .comment-actions {
    display: flex;
    justify-content: flex-end;
  }
  
  .edit-comment-form {
    width: 100%;
    margin-top: 0.5rem;
  }
  
  .edit-comment-form textarea {
    width: 100%;
    margin-bottom: 0.5rem;
  }
  
  .edit-buttons {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
  }
  
  .save-button, .cancel-button {
    background: none;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    font-size: 0.8rem;
    cursor: pointer;
    padding: 0.25rem 0.5rem;
  }
  
  .save-button {
    background-color: var(--primary-color);
    color: white;
  }
  
  .cancel-button {
    color: var(--text-color);
  }
  
  .edit-button {
    background: none;
    border: none;
    color: var(--primary-color);
    font-size: 0.8rem;
    cursor: pointer;
    padding: 0;
    margin-right: 0.5rem;
  }
  
  .delete-button {
    background: none;
    border: none;
    color: var(--error-color);
    font-size: 0.8rem;
    cursor: pointer;
    padding: 0;
  }
  
  .loading-state, .empty-state {
    padding: 1rem;
    text-align: center;
    color: var(--text-light);
    font-size: 0.9rem;
  }
  
  .error-message {
    background-color: rgba(239, 68, 68, 0.1);
    color: var(--error-color);
    padding: 0.75rem;
    border-radius: 4px;
    font-size: 0.9rem;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.5rem;
  }
  
  .error-message p {
    margin: 0;
  }
  
  .error-message button {
    background-color: var(--primary-color);
    color: white;
    border: none;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-size: 0.8rem;
    cursor: pointer;
  }
</style>
