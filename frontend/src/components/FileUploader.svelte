<script>
  import { createEventDispatcher, onMount } from 'svelte';
  import axiosInstance from '../lib/axios';
  
  // State
  let file = null;
  let uploading = false;
  let progress = 0;
  let error = '';
  let drag = false;
  let fileInput = null;
  
  // Event dispatcher
  const dispatch = createEventDispatcher();
  
  // Track allowed file types
  const allowedTypes = [
    'audio/mpeg', 'audio/wav', 'audio/ogg', 'audio/flac', 'audio/aac', 'audio/m4a',
    'video/mp4', 'video/webm', 'video/ogg', 'video/quicktime'
  ];
  
  // Initialize drag and drop
  function initDragAndDrop() {
    const dropZone = document.getElementById('drop-zone');
    
    if (dropZone) {
      dropZone.addEventListener('dragover', handleDragOver);
      dropZone.addEventListener('dragleave', handleDragLeave);
      dropZone.addEventListener('drop', handleDrop);
      
      return () => {
        dropZone.removeEventListener('dragover', handleDragOver);
        dropZone.removeEventListener('dragleave', handleDragLeave);
        dropZone.removeEventListener('drop', handleDrop);
      };
    }
  }
  
  // Handle drag events
  function handleDragOver(e) {
    e.preventDefault();
    e.stopPropagation();
    drag = true;
  }
  
  function handleDragLeave(e) {
    e.preventDefault();
    e.stopPropagation();
    drag = false;
  }
  
  function handleDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    drag = false;
    
    const dt = e.dataTransfer;
    const files = dt.files;
    
    if (files && files.length > 0) {
      handleFileSelect(files[0]);
    }
  }
  
  // Handle file selection
  function handleFileSelect(selectedFile) {
    error = '';
    
    // Check file type
    if (!allowedTypes.includes(selectedFile.type)) {
      error = 'File type not supported. Please upload an audio or video file.';
      return;
    }
    
    // Check file size (limit to 500MB for example)
    if (selectedFile.size > 500 * 1024 * 1024) {
      error = 'File too large. Please upload a file smaller than 500MB.';
      return;
    }
    
    file = selectedFile;
  }
  
  // Handle file input change
  function handleFileInputChange(e) {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      handleFileSelect(selectedFile);
    }
  }
  
  // Trigger file input click
  function openFileDialog() {
    if (fileInput) {
      fileInput.click();
    }
  }
  
  // Upload file
  async function uploadFile() {
    if (!file) {
      error = 'Please select a file first';
      return;
    }
    
    uploading = true;
    progress = 0;
    error = '';
    
    try {
      // Log the file being uploaded for debugging
      console.log('Uploading file:', file.name, file.type, file.size);
      
      // Create a properly configured FormData object with required file field name
      const formData = new FormData();
      formData.append('file', file); // 'file' name must match the FastAPI parameter name
      
      // Add debug logs to see exactly what's being sent
      console.log('FormData content keys:', [...formData.keys()]);
      console.log('File being uploaded:', file.name, file.type, file.size);
      
      // Log token for debugging
      const token = localStorage.getItem('token');
      console.log('Token available for upload:', !!token);
      
      // Use axiosInstance with correct path - ensure proper formatting
      const response = await axiosInstance.post('/files', formData, {
        headers: {
          // Remove the default Content-Type to let axios set it correctly for multipart/form-data
          'Content-Type': undefined,
          // Explicitly set Authorization header for file uploads
          'Authorization': `Bearer ${token}`
        },
        onUploadProgress: (progressEvent) => {
          const total = progressEvent.total || 0;
          if (total > 0) {
            progress = Math.round((progressEvent.loaded * 100) / total);
          }
        }
      });
      
      const responseData = response.data;
      console.log('Upload successful:', responseData);
      
      // Clear form and dispatch event
      file = null;
      if (fileInput) {
        fileInput.value = '';
      }
      
      // Notify parent component
      dispatch('uploadComplete', responseData);
    } catch (err) {
      console.error('Upload error:', err);
      error = err.response?.data?.detail || err.message || 'Failed to upload file. Please try again.';
    } finally {
      uploading = false;
    }
  }
  
  // Cancel upload
  function cancelUpload() {
    file = null;
    if (fileInput) {
      fileInput.value = '';
    }
  }
  
  onMount(() => {
    const cleanup = initDragAndDrop();
    return cleanup;
  });
</script>

<div class="uploader-container">
  {#if error}
    <div class="error-message">
      {error}
    </div>
  {/if}
  
  {#if !file}
    <div 
      id="drop-zone" 
      class="drop-zone {drag ? 'active' : ''}" 
      on:click={openFileDialog} 
      on:keydown={(e) => e.key === 'Enter' && openFileDialog()} 
      role="button" 
      tabindex="0"
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
        <polyline points="17 8 12 3 7 8"></polyline>
        <line x1="12" y1="3" x2="12" y2="15"></line>
      </svg>
      <div class="upload-text">
        <span>Drag & drop your audio/video file here</span>
        <span class="or-text">or click to browse</span>
      </div>
      <input
        type="file"
        accept="audio/*,video/*"
        bind:this={fileInput}
        on:change={handleFileInputChange}
        style="display: none;"
      >
    </div>
    
    <div class="supported-formats">
      <p>Supported formats: MP3, WAV, OGG, FLAC, AAC, M4A, MP4, WEBM</p>
    </div>
  {:else}
    <div class="selected-file">
      <div class="file-info">
        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polygon points="12 2 2 7 12 12 22 7 12 2"></polygon>
          <polyline points="2 17 12 22 22 17"></polyline>
          <polyline points="2 12 12 17 22 12"></polyline>
        </svg>
        <div>
          <p class="file-name">{file.name}</p>
          <p class="file-size">{(file.size / (1024 * 1024)).toFixed(2)} MB</p>
        </div>
      </div>
      
      <div class="file-actions">
        <button class="cancel-button" on:click={cancelUpload} disabled={uploading}>
          Cancel
        </button>
        <button class="upload-button" on:click={uploadFile} disabled={uploading}>
          {uploading ? 'Uploading...' : 'Upload'}
        </button>
      </div>
    </div>
    
    {#if uploading}
      <div class="progress-container">
        <div class="progress-bar">
          <div class="progress-fill" style="width: {progress}%"></div>
        </div>
        <p class="progress-text">{progress}%</p>
      </div>
    {/if}
  {/if}
</div>

<style>
  .uploader-container {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
    width: 100%;
    max-width: 500px;
    margin: 0 auto;
    padding: 0;
  }
  
  .drop-zone {
    padding: 3rem 2rem;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 1rem;
    border: 2px dashed var(--border-color);
    border-radius: 12px;
    background-color: var(--background-alt);
    cursor: pointer;
    transition: all 0.2s ease;
    text-align: center;
  }
  
  .drop-zone:hover,
  .drop-zone.active {
    border-color: var(--primary-color);
    background-color: rgba(59, 130, 246, 0.05);
  }
  
  .drop-zone svg {
    width: 2.5rem;
    height: 2.5rem;
    color: var(--primary-color);
    margin-bottom: 0.5rem;
  }
  
  .upload-text {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.25rem;
    text-align: center;
    color: var(--text-color);
    font-size: 1rem;
    line-height: 1.5;
  }
  
  .or-text {
    color: var(--text-light);
    font-size: 0.9em;
  }
  
  .supported-formats p {
    margin: 0;
  }
  
  .selected-file {
    padding: 1rem;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 1rem;
  }
  
  .file-info {
    display: flex;
    align-items: center;
    gap: 1rem;
  }
  
  .file-name {
    font-weight: 500;
    margin: 0;
    word-break: break-all;
  }
  
  .file-size {
    color: var(--text-light);
    font-size: 0.8rem;
    margin: 0.25rem 0 0;
  }
  
  .file-actions {
    display: flex;
    gap: 0.5rem;
  }
  
  .cancel-button {
    background-color: transparent;
    border: 1px solid var(--border-color);
    color: var(--text-color);
    border-radius: 4px;
    padding: 0.5rem 1rem;
    cursor: pointer;
    font-size: 0.9rem;
  }
  
  .upload-button {
    background-color: var(--primary-color);
    color: white;
    border: none;
    border-radius: 4px;
    padding: 0.5rem 1rem;
    cursor: pointer;
    font-size: 0.9rem;
  }
  
  .upload-button:disabled,
  .cancel-button:disabled {
    opacity: 0.7;
    cursor: not-allowed;
  }
  
  .progress-container {
    margin-top: 0.5rem;
  }
  
  .progress-bar {
    width: 100%;
    height: 8px;
    background-color: var(--background-color);
    border-radius: 4px;
    overflow: hidden;
  }
  
  .progress-fill {
    height: 100%;
    background-color: var(--primary-color);
    transition: width 0.2s;
  }
  
  .progress-text {
    text-align: right;
    font-size: 0.8rem;
    color: var(--text-light);
    margin: 0.25rem 0 0;
  }
  
  .error-message {
    background-color: rgba(239, 68, 68, 0.1);
    color: var(--error-color);
    padding: 0.75rem;
    border-radius: 4px;
    font-size: 0.9rem;
  }
</style>
