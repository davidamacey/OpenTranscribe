<script>
  import { onMount, onDestroy, createEventDispatcher } from 'svelte';
  import { slide } from 'svelte/transition';
  // Use the shared axios instance so auth token is always sent
  import axiosInstance from '../lib/axios';
  import { authStore } from '../stores/auth';
  import TruncatedText from './TruncatedText.svelte';
  import ConfirmationModal from './ConfirmationModal.svelte';
  
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
  
  // Confirmation modal state
  let showConfirmModal = false;
  let confirmModalTitle = '';
  let confirmModalMessage = '';
  /** @type {(() => void) | null} */
  let confirmCallback = null;
  
  // Event dispatcher
  const dispatch = createEventDispatcher();
  
  // Event listener for getComments events from parent components
  function handleGetCommentsEvent() {
    // Send comments data back through the event
    dispatch('getComments', { comments: comments });
  }
  
  // Add event listener when component is mounted
  onMount(() => {
    fetchComments();
    
    // Listen for getComments events
    const commentsWrapper = document.querySelector('.comments-section-wrapper');
    if (commentsWrapper) {
      commentsWrapper.addEventListener('getComments', /** @type {EventListener} */ (handleGetCommentsEvent));
    }
  });
  
  // Remove event listener when component is destroyed
  onDestroy(() => {
    const commentsWrapper = document.querySelector('.comments-section-wrapper');
    if (commentsWrapper) {
      commentsWrapper.removeEventListener('getComments', /** @type {EventListener} */ (handleGetCommentsEvent));
    }
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
        console.error('Invalid file ID:', fileId);
        error = 'Invalid file ID provided';
        loading = false;
        return;
      }
      
      if (!token) {
        console.error('No auth token found in localStorage');
        error = 'You need to be logged in to view comments';
        loading = false;
        return;
      }
      
      // Create custom headers with authentication token
      const headers = {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      };
      
      let response;
      try {
        const endpoint = `/comments/files/${numericFileId}/comments`;
        response = await axiosInstance.get(endpoint, { headers });
      } catch (/** @type {any} */ error) {
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
            response = await axiosInstance.get(`files/${numericFileId}/comments`, { headers });
          } catch (/** @type {any} */ legacyError) {
            try {
              // If that fails, try the query parameter approach as last resort
              response = await axiosInstance.get('/comments', { 
                params: { media_file_id: numericFileId },
                headers 
              });
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
      
      // Comments response received
      
      // Process comments to ensure they have user information
      // Processing comments
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
        // No comments found for this file
      } else {
        // Successfully processed comments
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
    
    if (!newComment.trim()) return;
    
    // Use the timestamp input if it was explicitly set, otherwise use null
    const timestamp = timestampInput !== null ? timestampInput : null;
    
    // Store locally for optimistic UI updates
    try {
      // Get user data from localStorage
      const userData = JSON.parse(localStorage.getItem('user') || '{}');
      
      // Get auth token from localStorage
      const token = localStorage.getItem('token');
      const numericFileId = Number(fileId);
      
      if (!token) {
        console.error('No auth token found in localStorage');
        error = 'You need to be logged in to add comments';
        return;
      }

      // Create custom headers with authentication token
      const headers = {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      };

      // Use the endpoint confirmed to be working in the API debugger
      let response;
      try {
        // The correct endpoint without leading slash (baseURL is '/api')
        // This will become /api/comments/files/{fileId}/comments
        const endpoint = `comments/files/${numericFileId}/comments`;
        
        // The backend expects media_file_id in the payload even though it's in the URL path
        const commentPayload = {
          text: newComment,
          timestamp: timestamp,
          media_file_id: numericFileId // Required by the CommentCreate schema
        };
        
        // Ensure token is included in the headers
        response = await axiosInstance.post(endpoint, commentPayload, { headers });
        
        // Successfully added comment
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
            // Trying legacy endpoint for adding comment
            const legacyPayload = {
              text: newComment,
              timestamp: timestamp,
              media_file_id: numericFileId // Required by the CommentCreate schema
            };
            response = await axiosInstance.post(`files/${numericFileId}/comments`, legacyPayload, { headers });
            // Successfully added comment using main endpoint
          } catch (/** @type {any} */ legacyError) {
            try {
              // Try the query parameter endpoint as last resort
              // Trying query parameter endpoint as last resort
              response = await axiosInstance.post('comments', {
                text: newComment,
                timestamp,
                media_file_id: numericFileId // Required by the CommentCreate schema
              }, { headers });
              // Successfully added comment using root endpoint
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
      
      // Comment added successfully
      
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
      // Editing comment
      
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
      // Editing comment with new text
      
      // Log detailed request info
      const isDevMode = typeof window !== 'undefined' && window.location.hostname === 'localhost';
      if (isDevMode) {
        // Request details for editing comment
      }
      
      await axiosInstance.put(`comments/${commentId}`, {
        text: newText
      }, { headers });
      
      // Comment edited successfully
      
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
  
  /**
   * Show confirmation modal
   * @param {string} title - The modal title
   * @param {string} message - The confirmation message
   * @param {() => void} callback - The callback to execute on confirmation
   */
  function showConfirmation(title, message, callback) {
    confirmModalTitle = title;
    confirmModalMessage = message;
    confirmCallback = callback;
    showConfirmModal = true;
  }

  /**
   * Handle confirmation modal confirm
   */
  function handleConfirmModalConfirm() {
    if (confirmCallback) {
      confirmCallback();
      confirmCallback = null;
    }
    showConfirmModal = false;
  }

  /**
   * Handle confirmation modal cancel
   */
  function handleConfirmModalCancel() {
    confirmCallback = null;
    showConfirmModal = false;
  }

  /**
   * Delete a comment
   * @param {number} commentId - The ID of the comment to delete
   */
  async function deleteComment(commentId) {
    showConfirmation(
      'Delete Comment',
      'Are you sure you want to delete this comment?',
      () => executeDeleteComment(commentId)
    );
  }

  /**
   * Execute comment deletion after confirmation
   * @param {number} commentId - The ID of the comment to delete
   */
  async function executeDeleteComment(commentId) {
    try {
      // Get auth token from localStorage
      const token = localStorage.getItem('token');
      // Deleting comment
      
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
      // Deleting comment with ID
      
      // Log detailed request info
      const isDevMode = typeof window !== 'undefined' && window.location.hostname === 'localhost';
      if (isDevMode) {
        // Delete request details
      }
      
      await axiosInstance.delete(`comments/${commentId}`, { headers });
      // Comment deleted successfully
      
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
    // Set timestamp to current time
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
  <div class="comments-header-internal">
    <h4 class="section-heading">Comments & Notes</h4>
    <div class="comments-preview">
      {#if comments && comments.length > 0}
        <span class="tag-chip">{comments.length} comment{comments.length !== 1 ? 's' : ''}</span>
      {:else}
        <span class="no-comments">No comments</span>
      {/if}
    </div>
  </div>
  <!-- Error message if needed -->
  {#if error}
    <div class="error-message">
      <p>{error}</p>
      <button 
        on:click={fetchComments}
        title="Retry loading comments"
      >Try Again</button>
    </div>
  {/if}
  
  <!-- Fixed comment form at the top -->
  <div class="comment-form-container">
    <form class="comment-form" on:submit={addComment}>
      <textarea
        bind:value={newComment}
        placeholder="Type your comment or note here..."
        rows="2"
        title="Enter your comment or note. You must mark a timestamp and add text before you can submit."
      ></textarea>
      <div class="form-actions">
        <div class="timestamp-actions">
          {#if timestampInput === null}
            <button
              type="button"
              class="timestamp-button"
              on:click={useCurrentTime}
              title="Click to mark the current video time - required before you can add your comment"
            >
              <span class="button-icon">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <circle cx="12" cy="12" r="10"/>
                  <polyline points="12,6 12,12 16,14"/>
                </svg>
              </span>
              <span>Mark Current Time</span>
            </button>
          {:else}
            <div class="current-timestamp">
              <span class="timestamp-value">Marked {formatTimestamp(timestampInput)}</span>
              <button
                type="button"
                class="clear-button"
                on:click|stopPropagation={() => timestampInput = null}
                title="Clear the marked timestamp (you'll need to mark time again to submit)"
              >
                ✖
              </button>
            </div>
          {/if}
        </div>
        <button
          type="submit"
          class="submit-button"
          disabled={!newComment.trim() || timestampInput === null}
          title={!newComment.trim() || timestampInput === null 
            ? 'You must add text and mark a timestamp before submitting' 
            : `Add your comment at ${formatTimestamp(timestampInput)}`}
        >
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
                  on:click={() => dispatch('seekTo', { time: comment.timestamp })}
                  on:keydown={(e) => e.key === 'Enter' && dispatch('seekTo', { time: comment.timestamp })}
                  aria-label="Jump to timestamp {formatTimestamp(comment.timestamp)}"
                  title="Jump to {formatTimestamp(comment.timestamp)} in the video"
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
                <button 
                  type="button" 
                  class="cancel-button" 
                  on:click={() => editingCommentId = null}
                  title="Cancel editing this comment and discard changes"
                >
                  Cancel
                </button>
                <button 
                  type="submit" 
                  class="save-button"
                  title="Save the changes to this comment"
                >
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
                  title="Edit this comment"
                >
                  Edit
                </button>
                <button 
                  type="button"
                  class="delete-button"
                  on:click={() => deleteComment(comment.id)}
                  title="Delete this comment permanently"
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

<!-- Confirmation Modal -->
<ConfirmationModal
  bind:isOpen={showConfirmModal}
  title={confirmModalTitle}
  message={confirmModalMessage}
  confirmText="Delete"
  cancelText="Cancel"
  confirmButtonClass="modal-delete-button"
  cancelButtonClass="modal-cancel-button"
  on:confirm={handleConfirmModalConfirm}
  on:cancel={handleConfirmModalCancel}
  on:close={handleConfirmModalCancel}
/>

<style>
  .comments-header-internal {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    border-bottom: 1px solid var(--border-color);
    background: var(--bg-secondary, var(--surface-color));
    position: sticky;
    top: 0;
    z-index: 10;
  }

  .section-heading {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .comments-preview {
    display: flex;
    gap: 8px;
    align-items: center;
  }

  .tag-chip {
    background: var(--primary-light);
    color: var(--primary-color);
    padding: 3px 8px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 500;
    white-space: nowrap;
  }

  .no-comments {
    color: var(--text-secondary);
    font-size: 12px;
    font-style: italic;
  }

  /* Main wrapper for the entire comments component */
  .comments-wrapper {
    display: flex;
    flex-direction: column;
    gap: 0;
    max-height: 1200px;
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    overflow: hidden;
  }
  
  /* Fixed comment form container at the top */
  .comment-form-container {
    position: sticky;
    top: 0;
    z-index: 5;
    padding: 1rem 0.5rem;
    border-bottom: 1px solid var(--border-color, rgba(120, 120, 120, 0.2));
  }
  
  /* Scrollable comments list container */
  .comment-form {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    width: 100%;
  }
  
  .comments-list-container {
    flex: 1;
    overflow-y: auto;
    padding: 0.5rem;
    max-height: 800px;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  
  .comment-form {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    width: 100%;
    max-width: none;
  }

  textarea {
    width: 100%;
    box-sizing: border-box;
    padding: 0.75rem;
    border: 1px solid var(--border-color, rgba(120, 120, 120, 0.2));
    border-radius: 8px;
    resize: vertical;
    min-height: 70px;
    font-family: inherit;
    font-size: 0.9rem;
    line-height: 1.5;
    background-color: var(--input-background, rgba(255, 255, 255, 0.05));
    color: var(--text-color);
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
    align-items: center;
    flex-wrap: wrap;
    gap: 0.75rem;
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
    background-color: var(--button-secondary-bg, rgba(59, 130, 246, 0.1));
    border: 1px solid var(--button-secondary-border, rgba(59, 130, 246, 0.3));
    border-radius: 6px;
    color: var(--primary-color);
    padding: 0.5rem 0.75rem;
    font-size: 0.85rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    white-space: nowrap;
  }
  
  .timestamp-button:hover {
    background-color: var(--button-secondary-bg-hover, rgba(59, 130, 246, 0.2));
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
    gap: 0.5rem;
    background-color: var(--button-secondary-bg, rgba(59, 130, 246, 0.1));
    border: 1px solid var(--button-secondary-border, rgba(59, 130, 246, 0.3));
    border-radius: 6px;
    color: var(--primary-color);
    padding: 0.5rem 0.75rem;
    font-size: 0.85rem;
    font-weight: 500;
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
    background-color: #3b82f6;
    color: white;
    border: none;
    padding: 0.6rem 1.2rem;
    border-radius: 10px;
    font-size: 0.95rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }
  
  .submit-button:hover:not(:disabled) {
    background-color: #2563eb;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }
  
  .submit-button:active:not(:disabled) {
    transform: translateY(0);
  }
  
  .submit-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  
  
  .comment-item {
    padding: 0.75rem;
    border: 1px solid var(--border-color, rgba(120, 120, 120, 0.2));
    border-radius: 8px;
    background-color: var(--surface-color, rgba(255, 255, 255, 0.03));
    transition: border-color 0.2s ease;
    width: 100%;
    box-sizing: border-box;
  }
  
  .comment-item:hover {
    border-color: var(--border-color-hover, rgba(120, 120, 120, 0.3));
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
    padding: 0.4rem 0.8rem;
    border-radius: 10px;
    font-size: 0.85rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    border: none;
    min-width: 60px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
  
  .save-button {
    background: #3b82f6;
    color: white;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }
  
  .save-button:hover {
    background: #2563eb;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }
  
  .save-button:active {
    transform: translateY(0);
  }
  
  .cancel-button {
    background-color: var(--card-background);
    color: var(--text-color);
    border: 1px solid var(--border-color);
    box-shadow: var(--card-shadow);
  }
  
  .cancel-button:hover {
    background: #2563eb;
    color: white;
    border: 1px solid #2563eb;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }
  
  .cancel-button:active {
    transform: translateY(0);
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

  /* Modal button styling to match app design */
  :global(.modal-delete-button) {
    background-color: #ef4444 !important;
    color: white !important;
    border: none !important;
    padding: 0.6rem 1.2rem !important;
    border-radius: 10px !important;
    font-size: 0.95rem !important;
    font-weight: 500 !important;
    cursor: pointer !important;
    transition: all 0.2s ease !important;
    box-shadow: 0 2px 4px rgba(239, 68, 68, 0.2) !important;
  }

  :global(.modal-delete-button:hover) {
    background-color: #dc2626 !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 8px rgba(239, 68, 68, 0.25) !important;
  }

  :global(.modal-cancel-button) {
    background-color: var(--card-background) !important;
    color: var(--text-color) !important;
    border: 1px solid var(--border-color) !important;
    padding: 0.6rem 1.2rem !important;
    border-radius: 10px !important;
    font-size: 0.95rem !important;
    font-weight: 500 !important;
    cursor: pointer !important;
    transition: all 0.2s ease !important;
    box-shadow: var(--card-shadow) !important;
    /* Ensure text is always visible */
    opacity: 1 !important;
  }

  :global(.modal-cancel-button:hover) {
    background-color: #2563eb !important;
    color: white !important;
    border-color: #2563eb !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25) !important;
  }
</style>
