<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import axiosInstance from '../lib/axios';
  import type { AxiosProgressEvent, CancelTokenSource } from 'axios';
  import axios from 'axios';
  
  // Constants for file handling
  const LARGE_FILE_THRESHOLD = 100 * 1024 * 1024; // 100MB
  const MB = 1024 * 1024; // 1 MB in bytes
  
  // Types
  interface FileWithSize extends File {
    size: number;
  }
  
  // State
  let file: File | null = null;
  let uploading = false;
  let progress = 0;
  let error = '';
  let statusMessage = ''; // Status message for user feedback
  let drag = false;
  let fileInput: HTMLInputElement | null = null;
  let cancelTokenSource: CancelTokenSource | null = null;
  let isCancelling = false;
  let currentFileId: number | null = null; // Track the current file ID for cancellation
  let token = ''; // Store the auth token
  
  // Upload speed calculation variables
  let lastLoaded = 0;
  let lastTime = Date.now();
  
  // Get token from localStorage on component mount
  onMount(() => {
    token = localStorage.getItem('token') || '';
    const cleanup = initDragAndDrop();
    return () => {
      if (cleanup) cleanup();
    };
  });
  
  // Event dispatcher with proper types
  const dispatch = createEventDispatcher<{
    uploadComplete: { id: string; filename: string };
    uploadError: { error: string };
  }>();
  
  // Track allowed file types with more comprehensive list
  const allowedTypes = [
    // Audio types
    'audio/mpeg', 'audio/wav', 'audio/ogg', 'audio/flac', 'audio/aac', 'audio/m4a',
    'audio/x-wav', 'audio/x-aiff', 'audio/x-m4a', 'audio/x-m4b', 'audio/x-m4p',
    'audio/mp3', 'audio/x-mpeg', 'audio/x-ms-wma', 'audio/x-ms-wax', 'audio/x-ms-wmv',
    'audio/vnd.rn-realaudio', 'audio/x-realaudio', 'audio/webm', 'audio/3gpp', 'audio/3gpp2',
    
    // Video types
    'video/mp4', 'video/webm', 'video/ogg', 'video/quicktime', 'video/x-msvideo',
    'video/x-ms-wmv', 'video/x-matroska', 'video/3gpp', 'video/3gpp2', 'video/x-flv',
    'video/x-m4v', 'video/mpeg', 'video/x-ms-asf', 'video/x-ms-wvx', 'video/avi'
  ];
  
  // Max file size (50GB in bytes)
  const MAX_FILE_SIZE = 50 * 1024 * 1024 * 1024; // 50GB
  
  // Initialize drag and drop
  function initDragAndDrop() {
    const dropZone = document.getElementById('drop-zone');
    
    if (dropZone) {
      const dragOverHandler = (e: DragEvent) => handleDragOver(e);
      const dragLeaveHandler = (e: DragEvent) => handleDragLeave(e);
      const dropHandler = (e: DragEvent) => handleDrop(e);
      
      dropZone.addEventListener('dragover', dragOverHandler);
      dropZone.addEventListener('dragleave', dragLeaveHandler);
      dropZone.addEventListener('drop', dropHandler);
      
      return () => {
        dropZone.removeEventListener('dragover', dragOverHandler);
        dropZone.removeEventListener('dragleave', dragLeaveHandler);
        dropZone.removeEventListener('drop', dropHandler);
      };
    }
    return () => {}; // Return empty cleanup function if no drop zone
  }
  
  // Handle drag events
  function handleDragOver(e: DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    drag = true;
  }
  
  function handleDragLeave(e: DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    drag = false;
  }
  
  function handleDrop(e: DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    drag = false;
    
    const dt = e.dataTransfer;
    if (!dt) return;
    
    const files = dt.files;
    if (files && files.length > 0) {
      handleFileSelect(files[0]);
    }
  }
  
  // Handle file selection
  function handleFileSelect(selectedFile: File) {
    error = '';
    file = selectedFile;
    
    // Check if file has a valid type
    if (!selectedFile.type) {
      // Try to determine type from extension if browser doesn't provide it
      const extension = selectedFile.name.split('.').pop()?.toLowerCase() || '';
      const extensionMap: Record<string, string> = {
        // Audio extensions
        'mp3': 'audio/mpeg',
        'wav': 'audio/wav',
        'ogg': 'audio/ogg',
        'flac': 'audio/flac',
        'aac': 'audio/aac',
        'm4a': 'audio/m4a',
        'aif': 'audio/x-aiff',
        'aiff': 'audio/x-aiff',
        'wma': 'audio/x-ms-wma',
        'ra': 'audio/vnd.rn-realaudio',
        'ram': 'audio/vnd.rn-realaudio',
        'weba': 'audio/webm',
        '3ga': 'audio/3gpp',
        '3gp': 'audio/3gpp',
        '3g2': 'audio/3gpp2',
        // Video extensions
        'mp4': 'video/mp4',
        'webm': 'video/webm',
        'ogv': 'video/ogg',
        'mov': 'video/quicktime',
        'avi': 'video/x-msvideo',
        'wmv': 'video/x-ms-wmv',
        'mkv': 'video/x-matroska',
        'm4v': 'video/x-m4v',
        'mpeg': 'video/mpeg',
        'mpg': 'video/mpeg',
        'flv': 'video/x-flv',
        'asf': 'video/x-ms-asf'
      };
      
      const mimeType = extensionMap[extension];
      if (extension && mimeType) {
        // Create a new File object with the correct type
        file = new File([selectedFile], selectedFile.name, {
          type: mimeType,
          lastModified: selectedFile.lastModified
        }) as FileWithSize;
      } else {
        error = 'File type could not be determined. Please upload a supported audio or video file.';
        file = null;
        return;
      }
    }
    
    // Check file type
    if (!allowedTypes.some(type => selectedFile.type.startsWith(type.split('/')[0]))) {
      error = `File type "${selectedFile.type}" is not supported. Please upload an audio or video file.`;
      return;
    }
    
    // Check file size
    if (selectedFile.size > MAX_FILE_SIZE) {
      error = `File too large. Maximum file size is ${formatFileSize(MAX_FILE_SIZE)}.`;
      return;
    }
    
    // Additional checks for very large files
    if (selectedFile.size > 2 * 1024 * 1024 * 1024) { // > 2GB
      // Warn about potential upload time for very large files
      error = `Warning: This is a large file (${formatFileSize(selectedFile.size)}). Upload may take a while. Click upload again to proceed.`;
      file = selectedFile;
      return;
    }
    
    file = selectedFile;
  }
  
  // Format file size for display
  function formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    const size = parseFloat((bytes / Math.pow(k, i)).toFixed(2));
    return `${size} ${sizes[i]}`;
  }
  
  // Handle file input change
  function handleFileInputChange(e: Event) {
    const target = e.target as HTMLInputElement;
    const selectedFile = target.files?.[0];
    if (selectedFile) {
      handleFileSelect(selectedFile);
    }
    // Reset the input value to allow re-uploading the same file
    target.value = '';
  }
  
  // Trigger file input click
  function openFileDialog() {
    if (fileInput) {
      fileInput.click();
    }
  }
  
  // Upload file with enhanced error handling and retry logic
  async function uploadFile() {
    if (!file) return;
    
    error = '';
    uploading = true;
    progress = 0;
    isCancelling = false;
    currentFileId = null; // Reset file ID at the start of upload
    statusMessage = ''; // Clear any status messages
    
    // Create a cancel token
    cancelTokenSource = axios.CancelToken.source();
    
    try {
      // If we have a warning but no error, and the user clicked upload again, proceed
      if (error && error.includes('Warning:')) {
        error = '';
      } else if (error) {
        // If there's a real error, don't proceed
        return;
      }
      
      statusMessage = 'Preparing upload...';
      
      // First, prepare the upload to get a file ID
      try {
        const prepareResponse = await axiosInstance.post('/api/files/prepare', {
          filename: file.name,
          file_size: file.size,
          content_type: file.type
        }, {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        });
        
        // Store the file ID as soon as we get it
        currentFileId = prepareResponse.data.file_id;
        statusMessage = `Upload prepared (File ID: ${currentFileId})`;
      } catch (err) {
        error = 'Failed to prepare upload';
        uploading = false;
        return;
      }
      
      // Create FormData with the file
      const formData = new FormData();
      formData.append('file', file);
      
      // Get auth token from the component state
      if (!token) {
        throw new Error('Authentication required. Please log in again.');
      }
      
      // Configure axios with timeout and upload progress
      const config = {
        headers: {
          'Content-Type': 'multipart/form-data',
          'Authorization': `Bearer ${token}`,
          'X-File-Size': file.size.toString(),
          'X-File-Name': encodeURIComponent(file.name)
        },
        timeout: 0, // No timeout for large uploads - server handles timeouts
        maxContentLength: Infinity,
        maxBodyLength: Infinity,
        cancelToken: cancelTokenSource.token,
        onUploadProgress: (progressEvent: AxiosProgressEvent) => {
          if (progressEvent.total) {
            // Calculate progress percentage
            const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            progress = Math.min(percentCompleted, 99); // Cap at 99% until fully processed
            
            // We can't reliably get the X-File-ID during upload progress in Axios
            // We'll get it from the final response instead
            
            // Update status message for large files
            if (file && file.size > LARGE_FILE_THRESHOLD) { 
              const loadedMB = (progressEvent.loaded / MB).toFixed(2);
              const totalMB = (progressEvent.total / MB).toFixed(2);
              const speedMBps = calculateUploadSpeed(progressEvent);
              statusMessage = `Uploaded ${loadedMB}MB of ${totalMB}MB (${speedMBps} MB/s)`;
            }
          }
        }
      };
      
      // Start the upload
      const response = await axiosInstance.post('/api/files', formData, config);
      const responseData = response.data;
      
      // Store the file ID for potential cancellation
      if (responseData && responseData.id) {
        currentFileId = responseData.id;
      }
      
      // Update progress to 100% when complete
      progress = 100;
      
      // Notify parent component
      dispatch('uploadComplete', responseData);
      
    } catch (err: unknown) {
      if (axios.isCancel(err)) {
        // This is an expected cancellation - don't treat as an error
        // Just update the status message (already set by cancelUpload)
        return;
      }
      
      // Handle different types of errors
      if (err && typeof err === 'object' && 'code' in err && err.code === 'ECONNABORTED') {
        error = 'Upload timed out. The server took too long to respond. Please try again.';
      } else if (err && typeof err === 'object' && 'response' in err && err.response && 
                typeof err.response === 'object' && err.response !== null) {
        const response = err.response as {
          status?: number;
          data?: { detail?: string; message?: string };
          statusText?: string;
        };
        
        // Server responded with an error status code
        if (response.status === 413) {
          error = 'File too large. The server rejected the upload due to size limits.';
        } else if (response.status === 401) {
          error = 'Session expired. Please log in again.';
        } else {
          error = response.data?.detail || 
                 response.data?.message || 
                 `Server error: ${response.status} ${response.statusText || 'Unknown error'}`;
        }
      } else if (err && typeof err === 'object' && 'request' in err) {
        // Request was made but no response received
        error = 'No response from server. Please check your connection and try again.';
      } else {
        // Something else went wrong
        error = (err as Error)?.message || 'An unknown error occurred during upload.';
      }
      
      // If we have a file and it's large, suggest using a different upload method
      if (file && file.size > 2 * 1024 * 1024 * 1024) { // > 2GB
        error += '\n\nFor large files, consider using a more reliable upload method or splitting the file into smaller parts.';
      }
      
      // Dispatch error event
      dispatch('uploadError', { error });
      
    } finally {
      // Clean up the cancel token
      cancelTokenSource = null;
      
      // Only reset state if not in the middle of cancellation
      // The cancellation handler will handle the state reset
      if (!isCancelling) {
        resetUploadState();
      } else {
        // Just reset the uploading state but keep the file
        uploading = false;
        progress = 0;
        
        // Set a timeout to clear the cancellation message after 3 seconds
        setTimeout(() => {
          isCancelling = false;
          error = '';
        }, 3000);
      }
    }
  }
  
  // Cancel upload or selection
  async function cancelUpload() {
    if (uploading && !isCancelling) {
      isCancelling = true;
      
      // Update UI immediately to show cancellation is in progress
      progress = 0;
      statusMessage = 'Cancelling upload...';
      
      try {
        // Cancel the ongoing request if we have a cancel token
        if (cancelTokenSource) {
          cancelTokenSource.cancel('Upload cancelled by user');
        }

        // If we have a file ID, call the backend to clean up
        if (currentFileId) {
          try {
            // Log the attempt to help with debugging
            statusMessage = `Cleaning up file ID ${currentFileId}...`;
            
            await axiosInstance.delete(`/api/files/${currentFileId}`, {
              headers: {
                'Authorization': `Bearer ${token}`
              }
            });
            statusMessage = 'Upload cancelled successfully';
          } catch (err) {
            // Log error but don't show console.error in production
            statusMessage = 'Upload cancelled but cleanup may be incomplete';
            // Continue with reset even if cleanup fails
          }
        } else {
          statusMessage = 'Upload cancelled (no file ID to clean up)';
        }

        // Reset the button state after a short delay to show feedback
        setTimeout(() => {
          resetUploadState();
        }, 2000);
      } catch (err) {
        statusMessage = 'Error during cancellation';
        setTimeout(() => {
          resetUploadState();
        }, 2000);
      }
    } else {
      // Not uploading or already cancelling: just clear the selection and reset state
      resetUploadState();
    }
  }
  
  // Reset the upload state
  function resetUploadState() {
    // Don't reset the file if we're in the middle of cancellation
    if (!isCancelling) {
      file = null;
      if (fileInput) {
        fileInput.value = '';
      }
    }
    uploading = false;
    progress = 0;
    isCancelling = false;
    currentFileId = null;
    error = '';
    statusMessage = '';
    
    // Reset upload speed calculation variables
    lastLoaded = 0;
    lastTime = Date.now();
  }
  
  // Calculate upload speed in MB/s
  function calculateUploadSpeed(progressEvent: AxiosProgressEvent): string {
    const now = Date.now();
    const timeElapsed = (now - lastTime) / 1000; // in seconds
    
    if (timeElapsed > 0) {
      const loadedSinceLastUpdate = progressEvent.loaded - lastLoaded;
      const speedBps = loadedSinceLastUpdate / timeElapsed;
      const speedMBps = (speedBps / MB).toFixed(1);
      
      // Update values for next calculation
      lastLoaded = progressEvent.loaded;
      lastTime = now;
      
      return speedMBps;
    }
    
    return '0.0';

  }
  
  onMount(() => {
    const cleanup = initDragAndDrop();
    return () => {
      if (cleanup) cleanup();
    };
  });
</script>

<div class="uploader-container">
  {#if error}
    <div class="message {error.includes('Warning:') ? 'warning-message' : 'error-message'}">
      {error}
      {#if error.includes('Warning:')}
        <button class="btn-continue" on:click|stopPropagation={uploadFile}>
          Continue Anyway
        </button>
      {/if}
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
      title="Drop your audio or video file here, or click to browse and select a file"
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
        <button
          type="button"
          class="cancel-button"
          on:click={cancelUpload}
          disabled={isCancelling}
          title={isCancelling ? 'Cancelling...' : 'Cancel selection or upload'}
        >
          {isCancelling ? 'Cancelling...' : 'Cancel'}
        </button>
        <button 
          class="upload-button" 
          on:click={uploadFile} 
          disabled={uploading}
          title="Upload the selected file for transcription"
        >
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
        {#if statusMessage}
          <p class="status-message">{statusMessage}</p>
        {/if}
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
    background-color: var(--surface-color);
    cursor: pointer;
    transition: all 0.2s ease;
    text-align: center;
  }
  
  .drop-zone:hover,
  .drop-zone.active {
    border-color: var(--primary-color);
    background-color: rgba(59, 130, 246, 0.05);
  }
  
  :global(.dark) .drop-zone:hover,
  :global(.dark) .drop-zone.active {
    background-color: rgba(59, 130, 246, 0.1);
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
    font-size: 0.875rem;
    color: var(--text-secondary);
  }
  
  .selected-file {
    padding: 1rem;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    background-color: var(--surface-color);
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
    margin-top: 4px;
    font-size: 0.8rem;
    color: var(--color-text);
  }
  
  .status-message {
    margin-top: 8px;
    font-size: 0.9rem;
    font-weight: 500;
    text-align: center;
    color: var(--color-primary);
  }
  
  .error-message {
    background-color: rgba(239, 68, 68, 0.1);
    color: var(--error-color);
    padding: 0.75rem;
    border-radius: 4px;
    font-size: 0.9rem;
  }
</style>
