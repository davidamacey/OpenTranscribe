<script>
  // @ts-nocheck
  import { createEventDispatcher, onMount } from 'svelte';
  import axiosInstance from '../lib/axios';
// Use the shared axios instance so auth token is always sent
  
  /** @type {string} */
  export let fileId = "";
  /** @type {Array<{id: number, name: string}>} */
  export let tags = [];
  
  // Ensure tags are always in the correct format
  $: {
    if (Array.isArray(tags)) {
      // Handle case where backend returns tag names as strings instead of objects
      tags = tags.map(tag => {
        if (typeof tag === 'string') {
          // Convert string tag to object format with a temporary ID
          return { id: `temp-${tag}`, name: tag };
        } else if (tag && typeof tag === 'object') {
          // Ensure tag object has required properties
          return { 
            id: tag.id !== undefined ? tag.id : `temp-${tag.name}`,
            name: tag.name || ''
          };
        }
        return tag;
      });
    }
  }
  
  /** @type {Array<{id: number, name: string}>} */
  let allTags = [];
  /** @type {string} */
  let newTagInput = '';
  /** @type {boolean} */
  let loading = false;
  /** @type {string|null} */
  let error = null;
  
  // Event dispatcher
  const dispatch = createEventDispatcher();
  
  // Fetch all available tags
  async function fetchAllTags() {
    error = null; // Reset error state before making request
    try {
      const token = localStorage.getItem('token');
      console.log('[TagsEditor] Fetching all tags with token:', token ? token.substring(0, 8) + '...' : '[none]');
      console.log('[TagsEditor] Request URL:', '/tags/');
      
      // Use consistent URL format
      const response = await axiosInstance.get('/tags/');
      console.log('[TagsEditor] Tags response:', response.status, response.headers);
      
      // Ensure all tags have valid IDs before adding them to the allTags array
      const validTags = (response.data || []).filter(tag => 
        tag && typeof tag === 'object' && 
        tag.id !== undefined && tag.id !== null && 
        tag.name !== undefined && tag.name !== null
      );
      
      allTags = validTags;
      
      if (!Array.isArray(allTags) || allTags.length === 0) {
        console.log('[TagsEditor] No tags found.');
      } else {
        console.log(`[TagsEditor] Found ${allTags.length} tags`);
      }
    } catch (err) { 
      console.error('[TagsEditor] Error fetching tags:', err);
      console.error('[TagsEditor] Error details:', {
        message: err.message,
        status: err.response?.status,
        data: err.response?.data,
        config: err.config
      });
      
      if (err.response && err.response.status === 401) {
        error = 'Unauthorized: Please log in.';
      } else if (err.code === 'ERR_NETWORK') {
        error = 'Network error: Cannot connect to server';
      } else {
        error = 'Failed to load tags';
      }
    }
  }
  
  // Add a tag to the file
  async function addTag(tagId) {
    loading = true;
    error = null;
    try {
      const token = localStorage.getItem('token');
      console.log(`[TagsEditor] Adding tag ${tagId} to file ${fileId} with token:`, token ? token.substring(0, 8) + '...' : '[none]');
      
      // Get the tag name by ID and send tag_data with name field as required by backend
      const tagToAdd = allTags.find(t => t.id === tagId);
      if (!tagToAdd) {
        console.error(`[TagsEditor] Tag with ID ${tagId} not found in allTags`);
        throw new Error('Tag not found');
      }
      
      // Prepare request payload
      const payload = { name: tagToAdd.name };
      console.log(`[TagsEditor] Adding tag with name: "${tagToAdd.name}" to file: ${fileId}`);
      console.log('[TagsEditor] Payload:', JSON.stringify(payload));
      
      // Send the payload as required by the backend API - must match the router configuration
      const addTagUrl = `/tags/files/${fileId}/tags`;
      console.log('[TagsEditor] POST URL:', addTagUrl);
      const response = await axiosInstance.post(addTagUrl, payload);
      console.log('[TagsEditor] Add tag response status:', response.status);
      console.log('[TagsEditor] Add tag response data:', response.data);
      
      // Use the response data from add_tag_to_file as the final tag object
      const finalTag = response.data;
      
      // Ensure the tag has a valid ID and name
      if (!finalTag || 
          typeof finalTag.id === 'undefined' || 
          finalTag.id === null || 
          typeof finalTag.name === 'undefined' || 
          finalTag.name === null) {
        console.error('[TagsEditor] Invalid tag received from server:', finalTag);
        throw new Error('Server returned an invalid tag');
      }
      
      // Only add the tag if it's not already present
      if (!tags.some(t => t.id === finalTag.id)) {
        tags = [...tags, finalTag];
        dispatch('tagsUpdated', { tags });
      }
    } catch (err) {
      if (err.response && err.response.status === 401) {
        error = 'Unauthorized: Please log in.';
      } else {
        error = 'Failed to add tag';
      }
      console.error('[TagsEditor] Error adding tag:', err);
    } finally {
      loading = false;
    }
  }
  
  // Create a new tag and add it to the file
  async function createAndAddTag() {
    if (!newTagInput.trim()) return;
    loading = true;
    error = null;
    try {
      const token = localStorage.getItem('token');
      console.log(`[TagsEditor] Creating tag '${newTagInput.trim()}' and adding to file ${fileId} with token:`, token ? token.substring(0, 8) + '...' : '[none]');
      
      // Step 1: Create the tag with proper payload format
      const createPayload = { name: newTagInput.trim() };
      console.log('[TagsEditor] Creating tag with payload:', JSON.stringify(createPayload));
      
      // Debug the URL and payload
      console.log('[TagsEditor] POST URL:', '/tags/');
      console.log('[TagsEditor] Headers:', axiosInstance.defaults.headers);
      
      const createResponse = await axiosInstance.post('/tags/', createPayload);
      console.log('[TagsEditor] Create tag response status:', createResponse.status);
      const newTag = createResponse.data;
      console.log('[TagsEditor] Created tag:', newTag);
      
      // Ensure the tag has a valid ID and name to prevent 'undefined' key errors
      if (!newTag || typeof newTag.id === 'undefined') {
        console.error('[TagsEditor] Invalid tag received from server:', newTag);
        throw new Error('Server returned an invalid tag');
      }
      
      // Then add the tag to the file, similar to addTag but using the new tag data
      const addTagUrl = `/tags/files/${fileId}/tags`;
      const addPayload = { name: newTag.name };
      console.log('[TagsEditor] Adding tag to file URL:', addTagUrl);
      console.log('[TagsEditor] Adding tag to file payload:', JSON.stringify(addPayload));
      
      const addResponse = await axiosInstance.post(addTagUrl, addPayload);
      console.log('[TagsEditor] Add tag response status:', addResponse.status);
      console.log('[TagsEditor] Add tag response data:', addResponse.data);
      
      // Use the response data from add_tag_to_file as the final tag object
      const finalTag = addResponse.data;
      if (!finalTag || typeof finalTag.id === 'undefined') {
        console.error('[TagsEditor] Invalid tag received after adding to file:', finalTag);
        throw new Error('Server returned an invalid tag after adding to file');
      }
      
      // Add to allTags if it's not already present
      if (!allTags.some(t => t.id === finalTag.id)) {
        allTags = [...allTags, finalTag];
      }
      
      // Add to tags if it's not already present
      if (!tags.some(t => t.id === finalTag.id)) {
        tags = [...tags, finalTag];
        newTagInput = '';
        dispatch('tagsUpdated', { tags });
      } else {
        newTagInput = '';
      }
    } catch (err) {
      // Safely check for error properties
      if (err && typeof err === 'object') {
        const errorObj = err;
        
        if (errorObj.response && errorObj.response.status === 401) {
          error = 'Unauthorized: Please log in.';
        } else if (
          errorObj.response && 
          typeof errorObj.response === 'object' && 
          'data' in errorObj.response && 
          errorObj.response.data && 
          typeof errorObj.response.data === 'object' && 
          'detail' in errorObj.response.data
        ) {
          error = `Failed to create tag: ${errorObj.response.data.detail}`;
        } else {
          error = 'Failed to create tag';
        }
      } else {
        error = 'Failed to create tag';
      }
      console.error('[TagsEditor] Error creating tag:', err);
    } finally {
      loading = false;
    }
  }
  
  // Remove a tag from the file
  async function removeTag(tagId) {
    loading = true;
    error = null;
    try {
      const token = localStorage.getItem('token');
      console.log(`[TagsEditor] Removing tag ${tagId} from file ${fileId} with token:`, token ? token.substring(0, 8) + '...' : '[none]');
      
      // Find the tag by ID to get its name - the backend needs tag name, not ID
      const tagToRemove = tags.find(t => t.id === tagId);
      if (!tagToRemove) {
        console.error(`[TagsEditor] Tag with ID ${tagId} not found in tags list`);
        throw new Error('Tag not found');
      }
      
      // IMPORTANT: The backend expects /tags/files/{file_id}/tags/{tag_name} due to router prefix configuration
      const deleteUrl = `/tags/files/${fileId}/tags/${encodeURIComponent(tagToRemove.name)}`;
      console.log('[TagsEditor] DELETE URL:', deleteUrl);
      
      // Send the delete request
      const response = await axiosInstance.delete(deleteUrl);
      console.log('[TagsEditor] Delete tag response status:', response.status);
      
      // Update the local tags array
      // Filter out the removed tag using a safe comparison
      const updatedTags = tags.filter(t => 
        t.id !== undefined && t.id !== null && t.id !== tagId
      );
      
      // Only update if something actually changed
      if (updatedTags.length !== tags.length) {
        tags = updatedTags;
        dispatch('tagsUpdated', { tags });
        console.log('[TagsEditor] Tag removed successfully');
      } else {
        console.log('[TagsEditor] Tag not found in current tags list');
      }
    } catch (err) {
      console.error('[TagsEditor] Error removing tag:', err);
      console.error('[TagsEditor] Error details:', {
        message: err.message,
        status: err.response?.status,
        data: err.response?.data,
        config: err.config
      });
      
      if (err.response && err.response.status === 401) {
        error = 'Unauthorized: Please log in.';
      } else if (err.code === 'ERR_NETWORK') {
        error = 'Network error: Cannot connect to server';
      } else {
        error = 'Failed to remove tag';
      }
    } finally {
      loading = false;
    }
  }
  
  // Handle keydown event in the input field
  function handleInputKeydown(event) {
    if (event.key === 'Enter' && newTagInput.trim()) {
      event.preventDefault();
      createAndAddTag();
    }
  }
  
  let suggestedTags = [];
  
  // Get suggested tags (those that aren't already assigned to the file)
  // Show only the 5 most recently created tags as suggestions to prevent UI clutter
  $: suggestedTags = allTags
    .filter(tag => !tags.some(t => 
      // Compare by ID if available, otherwise by name
      (t.id === tag.id) || (t.name === tag.name)
    ))
    .sort((a, b) => b.id - a.id) // Sort by ID descending (assuming higher IDs are newer)
    .slice(0, 5); // Limit to only 5 most recent tags
  
  onMount(() => {
    fetchAllTags();
  });
</script>

<div class="tags-editor">
  {#if error && !(error === 'Failed to load tags' && tags.length === 0)}
    <div class="error-message">
      {error}
    </div>
  {/if}
  
  <div class="tags-list">
    {#if tags.length === 0}
      <span class="no-tags">No tags yet.</span>
    {/if}
    {#each tags.filter(t => t && t.id !== undefined) as tag (tag.id)}
      <span class="tag">
        {tag.name}
        <button class="tag-remove" on:click={() => removeTag(tag.id)} title="Remove tag">×</button>
      </span>
    {/each}
    
    <div class="tag-input-container">
      <input
        type="text"
        placeholder="Add tag..."
        bind:value={newTagInput}
        on:keydown={handleInputKeydown}
        class="tag-input"
        disabled={loading}
      >
      {#if newTagInput.trim()}
        <button 
          class="tag-add-button"
          on:click={createAndAddTag}
          disabled={loading}
        >
          Add
        </button>
      {/if}
    </div>
  </div>
  
  {#if suggestedTags.length > 0}
    <div class="suggested-tags">
      <span class="suggested-label">Suggested:</span>
      {#each suggestedTags.filter(t => t && t.id !== undefined) as tag (tag.id)}
        <button 
          class="suggested-tag"
          on:click={() => addTag(tag.id)}
          disabled={loading}
        >
          {tag.name}
        </button>
      {/each}
    </div>
  {/if}
</div>

<style>
  .tags-editor {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  
  .tags-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    align-items: center;
  }
  
  .tag {
    background-color: rgba(59, 130, 246, 0.1);
    color: var(--primary-color);
    padding: 0.35rem 0.5rem;
    border-radius: 4px;
    font-size: 0.8rem;
    display: flex;
    align-items: center;
    gap: 0.25rem;
  }
  
  .tag-remove {
    background: none;
    border: none;
    color: var(--text-light);
    font-size: 1rem;
    cursor: pointer;
    padding: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 16px;
    height: 16px;
  }
  
  .tag-remove:hover {
    color: var(--error-color);
  }
  
  .tag-input-container {
    display: flex;
    align-items: center;
  }
  
  .tag-input {
    background: transparent;
    border: none;
    border-bottom: 1px dashed var(--border-color);
    padding: 0.35rem 0;
    font-size: 0.8rem;
    width: 100px;
    color: var(--text-color);
  }
  
  .tag-input:focus {
    border-bottom-color: var(--primary-color);
    outline: none;
  }
  
  .tag-add-button {
    background-color: var(--primary-color);
    color: white;
    border: none;
    border-radius: 4px;
    padding: 0.25rem 0.5rem;
    font-size: 0.8rem;
    cursor: pointer;
    margin-left: 0.5rem;
  }
  
  .tag-add-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  
  .suggested-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    align-items: center;
    font-size: 0.8rem;
  }
  
  .suggested-label {
    color: var(--text-light);
  }
  
  .suggested-tag {
    background: none;
    border: 1px dashed var(--border-color);
    border-radius: 4px;
    padding: 0.25rem 0.5rem;
    font-size: 0.8rem;
    cursor: pointer;
    color: var(--text-light);
  }
  
  .suggested-tag:hover {
    border-color: var(--primary-color);
    color: var(--primary-color);
    background-color: rgba(59, 130, 246, 0.05);
  }
  
  .suggested-tag:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  
  .error-message {
    background-color: rgba(239, 68, 68, 0.1);
    color: var(--error-color);
    padding: 0.5rem;
    border-radius: 4px;
    font-size: 0.8rem;
  }
</style>
