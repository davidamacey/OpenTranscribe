<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import axiosInstance from '../lib/axios';
  import type { AxiosProgressEvent, CancelTokenSource } from 'axios';
  import axios from 'axios';
  
  // Constants for file handling
  const LARGE_FILE_THRESHOLD = 100 * 1024 * 1024; // 100MB
  const MB = 1024 * 1024; // 1 MB in bytes
  const FILE_SIZE_LIMIT = 2 * 1024 * 1024 * 1024; // 2GB
  
  // Constants for Imohash implementation
  const IMOHASH_SAMPLE_SIZE = 64 * 1024; // 64KB samples for Imohash
  
  // Types
  interface FileWithSize extends File {
    size: number;
  }

  
  // State
  let activeTab: 'file' | 'url' = 'file';
  let file: FileWithSize | null = null;
  let fileInput: HTMLInputElement;
  let drag = false;
  let uploading = false;
  let progress = 0;
  let error = '';
  let statusMessage = '';
  let isDuplicateFile = false; // Track if the current file is a duplicate
  let duplicateFileId: number | null = null; // Track the ID of the duplicate file
  let cancelTokenSource: CancelTokenSource | null = null;
  let isCancelling = false;
  let currentFileId: number | null = null; // Track the current file ID for cancellation
  let token = ''; // Store the auth token

  // URL processing state
  let youtubeUrl = '';
  let processingUrl = false;
  let urlProgress = 0;
  let urlError = '';
  let urlStatusMessage = '';
  
  // Upload speed calculation variables
  let lastLoaded = 0;
  let lastTime = Date.now();
  let estimatedTimeRemaining = '';
  let uploadStartTime = 0;
  
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
    uploadComplete: { fileId: number; isDuplicate?: boolean };
    uploadError: { error: string };
  }>();

  // URL validation regex for YouTube
  const YOUTUBE_URL_REGEX = /^(https?:\/\/)?(www\.)?(youtube\.com|youtu\.be)\/.*$/;
  
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
  
  // Max file size (15GB in bytes) - matches nginx client_max_body_size
  const MAX_FILE_SIZE = 15 * 1024 * 1024 * 1024; // 15GB
  
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
      const fileSizeFormatted = formatFileSize(selectedFile.size);
      const maxSizeFormatted = formatFileSize(MAX_FILE_SIZE);
      error = `File too large (${fileSizeFormatted}). Maximum file size is ${maxSizeFormatted}. Please try:\n• Compressing the video/audio file\n• Using a different format with better compression\n• Splitting large files into smaller parts`;
      return;
    }
    
    // Additional checks for very large files
    if (selectedFile.size > 2 * 1024 * 1024 * 1024) { // > 2GB
      // Warn about potential upload time for very large files
      error = `Warning: This is a large file (${formatFileSize(selectedFile.size)}). Upload may take a while and requires stable internet connection. Click upload again to proceed.`;
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
    estimatedTimeRemaining = '';
    uploadStartTime = Date.now();
    
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
      
      // Calculate file hash before upload
      let fileHash = null;
      try {
        statusMessage = 'Calculating file hash with Imohash...';
        fileHash = await calculateFileHash(file);
        // Strip the 0x prefix for display and database consistency
        const displayHash = fileHash.startsWith('0x') ? fileHash.substring(2) : fileHash;
        statusMessage = `Hash calculated: ${displayHash.substring(0, 8)}...`;
        // Remove 0x prefix for backend compatibility
        if (fileHash.startsWith('0x')) {
          fileHash = fileHash.substring(2);
        }
      } catch (err) {
        // If hash calculation fails, show a warning but continue with upload
        statusMessage = "Warning: Could not calculate file hash for duplicate detection. Upload will continue.";
      }

      // First, prepare the upload to get a file ID
      try {
        // Step 1: Prepare the upload and get a file ID
        const prepareResponse = await axiosInstance.post('/api/files/prepare', {
          filename: file.name,
          file_size: file.size,
          content_type: file.type,
          file_hash: fileHash
        }, {
          headers: {
            Authorization: `Bearer ${token}`
          }
        });
        // Store the file ID as soon as we get it
        currentFileId = prepareResponse.data.file_id;
        
        // Check if this is a duplicate file
        if (prepareResponse.data.is_duplicate === 1) {
          duplicateFileId = prepareResponse.data.file_id;
          statusMessage = `Duplicate file detected. Using existing file (ID: ${duplicateFileId})`;
          uploading = false;
          isDuplicateFile = true;
          
          // Show notification message that this is a duplicate file
          error = `Duplicate file detected! This file has already been uploaded and is available in your library. You can use the existing file instead of uploading it again.`;
          
          // Note: We don't dispatch uploadComplete event here anymore
          // We'll wait for user to acknowledge the message
          
          return;
        }
        
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
      
      // Include the file hash in the headers if available
      const uploadHeaders: Record<string, string> = {
        'Authorization': `Bearer ${token}`,
        'X-File-ID': currentFileId ? currentFileId.toString() : '',
        'X-File-Size': file.size.toString(),
        'X-File-Name': encodeURIComponent(file.name)
      };
      
      if (fileHash) {
        uploadHeaders['X-File-Hash'] = fileHash;
      }
      
      // Configure axios with timeout and upload progress
      const config = {
        headers: {
          'Content-Type': 'multipart/form-data',
          ...uploadHeaders
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
              const { speed, timeRemaining } = calculateUploadStats(progressEvent);
              estimatedTimeRemaining = timeRemaining;
              statusMessage = `Uploaded ${loadedMB}MB of ${totalMB}MB (${speed} MB/s) • ${timeRemaining} remaining`;
            } else {
              // For smaller files, still calculate time remaining but don't show detailed MB info
              const { timeRemaining } = calculateUploadStats(progressEvent);
              estimatedTimeRemaining = timeRemaining;
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
      // Dispatch upload complete event with the appropriate structure
      if (currentFileId) {
        dispatch('uploadComplete', { fileId: currentFileId });
      }
      
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
          const fileSizeGB = file ? (file.size / (1024 * 1024 * 1024)).toFixed(1) : 'unknown';
          error = `File too large (${fileSizeGB}GB). This file exceeds the current server upload limit of 15GB. Please try:\n• Compressing the video/audio file\n• Using a different format with better compression\n• Splitting large files into smaller parts\n• Contacting your administrator to increase limits`;
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
  
  // Function to handle acknowledging a duplicate file
  function acknowledgeDuplicate() {
    // Dispatch event to inform parent that upload is complete with duplicate file
    if (duplicateFileId) {
      dispatch('uploadComplete', { fileId: duplicateFileId, isDuplicate: true });
    }
    
    // Reset state
    isDuplicateFile = false;
    error = '';
    duplicateFileId = null;
    resetUploadState();
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
    estimatedTimeRemaining = '';
    uploadStartTime = 0;
  }

  // Reset URL processing state
  function resetUrlState() {
    youtubeUrl = '';
    processingUrl = false;
    urlProgress = 0;
    urlError = '';
    urlStatusMessage = '';
    currentFileId = null;
  }

  // Switch tabs and reset states
  function switchTab(tab: 'file' | 'url') {
    if (tab === activeTab) return;
    
    activeTab = tab;
    
    if (tab === 'file') {
      resetUrlState();
    } else {
      resetUploadState();
    }
  }

  // Validate YouTube URL
  function isValidYouTubeUrl(url: string): boolean {
    return YOUTUBE_URL_REGEX.test(url.trim());
  }

  // Process YouTube URL
  async function processYouTubeUrl() {
    if (!youtubeUrl.trim()) {
      urlError = 'Please enter a YouTube URL';
      return;
    }

    if (!isValidYouTubeUrl(youtubeUrl)) {
      urlError = 'Please enter a valid YouTube URL (e.g., https://www.youtube.com/watch?v=...)';  
      return;
    }

    urlError = '';
    processingUrl = true;
    urlProgress = 0;
    urlStatusMessage = 'Processing YouTube URL...';
    currentFileId = null;

    // Create cancel token
    cancelTokenSource = axios.CancelToken.source();

    try {
      const response = await axiosInstance.post('/api/files/process-url', {
        url: youtubeUrl.trim()
      }, {
        headers: {
          'Authorization': `Bearer ${token}`
        },
        timeout: 300000, // 5 minutes for URL processing
        cancelToken: cancelTokenSource.token,
        onUploadProgress: (progressEvent: AxiosProgressEvent) => {
          if (progressEvent.total) {
            urlProgress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          }
        }
      });

      const result = response.data;
      currentFileId = result.id;
      urlProgress = 100;
      urlStatusMessage = 'YouTube video processed successfully!';
      
      // Dispatch success event
      dispatch('uploadComplete', { fileId: result.id });
      
    } catch (err: unknown) {
      if (axios.isCancel(err)) {
        return; // Expected cancellation
      }
      
      // Handle different types of errors
      if (err && typeof err === 'object' && 'response' in err && err.response &&
          typeof err.response === 'object' && err.response !== null) {
        const response = err.response as {
          status?: number;
          data?: { detail?: string; message?: string };
        };
        
        if (response.status === 400) {
          urlError = response.data?.detail || 'Invalid YouTube URL';
        } else if (response.status === 401) {
          urlError = 'Session expired. Please log in again.';
        } else if (response.status === 429) {
          urlError = 'Too many requests. Please wait a moment and try again.';
        } else {
          urlError = response.data?.detail || response.data?.message || 'Failed to process YouTube URL';
        }
      } else {
        urlError = 'Network error. Please check your connection and try again.';
      }
      
      dispatch('uploadError', { error: urlError });
      
    } finally {
      processingUrl = false;
      cancelTokenSource = null;
    }
  }

  // Cancel URL processing
  async function cancelUrlProcessing() {
    if (processingUrl && !isCancelling) {
      isCancelling = true;
      urlStatusMessage = 'Cancelling URL processing...';
      
      try {
        if (cancelTokenSource) {
          cancelTokenSource.cancel('URL processing cancelled by user');
        }

        if (currentFileId) {
          try {
            await axiosInstance.delete(`/api/files/${currentFileId}`, {
              headers: {
                'Authorization': `Bearer ${token}`
              }
            });
            urlStatusMessage = 'URL processing cancelled successfully';
          } catch (err) {
            urlStatusMessage = 'URL processing cancelled but cleanup may be incomplete';
          }
        } else {
          urlStatusMessage = 'URL processing cancelled';
        }

        setTimeout(() => {
          resetUrlState();
        }, 2000);
      } catch (err) {
        urlStatusMessage = 'Error during cancellation';
        setTimeout(() => {
          resetUrlState();
        }, 2000);
      }
    } else {
      resetUrlState();
    }
  }
  
  // Format time remaining into readable units
  function formatTimeRemaining(seconds: number): string {
    if (seconds < 60) {
      return `${Math.ceil(seconds)}s`;
    } else if (seconds < 3600) {
      const minutes = Math.floor(seconds / 60);
      const remainingSeconds = Math.ceil(seconds % 60);
      return remainingSeconds > 0 ? `${minutes}m ${remainingSeconds}s` : `${minutes}m`;
    } else {
      const hours = Math.floor(seconds / 3600);
      const remainingMinutes = Math.floor((seconds % 3600) / 60);
      return `${hours}h ${remainingMinutes}m`;
    }
  }

  // Calculate upload speed and estimated time remaining
  function calculateUploadStats(progressEvent: AxiosProgressEvent): { speed: string; timeRemaining: string } {
    const now = Date.now();
    const timeElapsed = (now - lastTime) / 1000; // in seconds
    
    if (timeElapsed > 0 && progressEvent.total) {
      const loadedSinceLastUpdate = progressEvent.loaded - lastLoaded;
      const speedBps = loadedSinceLastUpdate / timeElapsed;
      const speedMBps = (speedBps / MB).toFixed(1);
      
      // Calculate estimated time remaining
      const remainingBytes = progressEvent.total - progressEvent.loaded;
      const estimatedSeconds = speedBps > 0 ? remainingBytes / speedBps : 0;
      const timeRemaining = formatTimeRemaining(estimatedSeconds);
      
      // Update values for next calculation
      lastLoaded = progressEvent.loaded;
      lastTime = now;
      
      return { speed: speedMBps, timeRemaining };
    }
    
    return { speed: '0.0', timeRemaining: 'Calculating...' };
  }
  
  // Calculate file hash using imohash package
  /**
   * Calculate file hash using the Imohash algorithm
   * 
   * This is a simplified implementation of the Imohash algorithm:
   * - Takes small samples from beginning, middle, and end of the file
   * - Combines with file size
   * - Creates SHA-256 hash of this data (truncated to 128 bits for compatibility)
   * 
   * This makes it extremely fast even for large files while providing reliable duplicate detection.
   * 
   * @param file - The file to hash
   * @returns A hash as a hex string with 0x prefix
   */
  async function calculateFileHash(file: File): Promise<string> {
    // Handle empty files according to Imohash spec
    if (file.size === 0) {
      return "0xc1c93cf2d1ecdc0b42e91262f343d8d9";
    }
    
    try {
      // For small files, just hash the entire content
      if (file.size <= IMOHASH_SAMPLE_SIZE) {
        const fileBuffer = await file.arrayBuffer();
        const fileBytes = new Uint8Array(fileBuffer);
        
        // Combine file content with size (8 bytes, little-endian)
        const hashData = new Uint8Array(fileBytes.length + 8);
        hashData.set(fileBytes, 0);
        
        // Add file size as 8 bytes
        const view = new DataView(hashData.buffer);
        view.setBigUint64(fileBytes.length, BigInt(file.size), true); // true = little-endian
        
        // Calculate SHA-256 hash (browsers don't support MD5 in SubtleCrypto)
        const hashBuffer = await crypto.subtle.digest('SHA-256', hashData);
        // Use only first 16 bytes (128 bits) to match MD5 length for compatibility
        const hashHex = Array.from(new Uint8Array(hashBuffer).slice(0, 16))
          .map(b => b.toString(16).padStart(2, '0'))
          .join('');
        
        return "0x" + hashHex;
      }
      
      // For larger files, sample beginning, middle, and end
      const beginBuffer = await file.slice(0, IMOHASH_SAMPLE_SIZE).arrayBuffer();
      
      const middleStart = Math.floor(file.size / 2) - Math.floor(IMOHASH_SAMPLE_SIZE / 2);
      const middleBuffer = await file.slice(middleStart, middleStart + IMOHASH_SAMPLE_SIZE).arrayBuffer();
      
      const endStart = Math.max(0, file.size - IMOHASH_SAMPLE_SIZE);
      const endBuffer = await file.slice(endStart).arrayBuffer();
      
      // Combine samples with file size (8 bytes)
      const totalSize = beginBuffer.byteLength + middleBuffer.byteLength + endBuffer.byteLength + 8;
      const hashData = new Uint8Array(totalSize);
      
      // Copy samples into combined buffer
      hashData.set(new Uint8Array(beginBuffer), 0);
      hashData.set(new Uint8Array(middleBuffer), beginBuffer.byteLength);
      hashData.set(new Uint8Array(endBuffer), beginBuffer.byteLength + middleBuffer.byteLength);
      
      // Add file size as 8 bytes (little-endian)
      const view = new DataView(hashData.buffer);
      view.setBigUint64(totalSize - 8, BigInt(file.size), true); // true = little-endian
      
      // Calculate SHA-256 hash (browsers don't support MD5 in SubtleCrypto)
      const hashBuffer = await crypto.subtle.digest('SHA-256', hashData);
      // Use only first 16 bytes (128 bits) to match MD5 length for compatibility
      const hashHex = Array.from(new Uint8Array(hashBuffer).slice(0, 16))
        .map(b => b.toString(16).padStart(2, '0'))
        .join('');
      
      return "0x" + hashHex;
    } catch (error) {
      console.error('Error calculating file hash:', error);
      throw error;
    }
  }
  
  onMount(() => {
    const cleanup = initDragAndDrop();
    return () => {
      if (cleanup) cleanup();
    };
  });
</script>

<div class="uploader-container">
  <!-- Tab Navigation -->
  <div class="tab-navigation">
    <button 
      class="tab-button {activeTab === 'file' ? 'active' : ''}"
      on:click={() => switchTab('file')}
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
        <polyline points="17 8 12 3 7 8"></polyline>
        <line x1="12" y1="3" x2="12" y2="15"></line>
      </svg>
      Upload File
    </button>
    <button 
      class="tab-button {activeTab === 'url' ? 'active' : ''}"
      on:click={() => switchTab('url')}
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path>
        <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path>
      </svg>
      YouTube URL
    </button>
  </div>
  <!-- Display duplicate notification - made more prominent with !important -->
  {#if isDuplicateFile}
    <div class="message duplicate-message" id="duplicate-notification">
      <div class="message-icon">
        <!-- Duplicate File Icon -->
        <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M16 17L21 12L16 7"></path>
          <path d="M21 12H9"></path>
          <path d="M3 3V21"></path>
        </svg>
      </div>
      <div class="message-content">
        <strong>Duplicate File Detected!</strong>
        <p>This file has already been uploaded and is available in your library. You can use the existing file instead of uploading it again.</p>
        <div class="message-actions">
          <button class="btn-acknowledge" on:click|stopPropagation={acknowledgeDuplicate}>
            Use Existing File
          </button>
        </div>
      </div>
    </div>
  {/if}
  
  <!-- Regular error messages (non-duplicates) -->
  {#if error && !isDuplicateFile}
    <div class="message {error.includes('Warning:') ? 'warning-message' : 'error-message'}">
      <div class="message-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"></circle>
          <line x1="12" y1="8" x2="12" y2="12"></line>
          <line x1="12" y1="16" x2="12.01" y2="16"></line>
        </svg>
      </div>
      <div class="message-content">
        {error}
        <div class="message-actions">
          {#if error.includes('Warning:')}
            <button class="btn-continue" on:click|stopPropagation={uploadFile}>
              Continue Anyway
            </button>
          {/if}
        </div>
      </div>
    </div>
  {/if}
  
  <!-- File Upload Tab -->
  {#if activeTab === 'file'}
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
          <div class="progress-header">
            <span class="progress-text">{progress}%</span>
            {#if estimatedTimeRemaining && estimatedTimeRemaining !== 'Calculating...'}
              <span class="time-remaining">{estimatedTimeRemaining} remaining</span>
            {/if}
          </div>
          <div class="progress-bar">
            <div class="progress-fill" style="width: {progress}%"></div>
          </div>
          {#if statusMessage}
            <p class="status-message">{statusMessage}</p>
          {/if}
        </div>
      {/if}
    {/if}
  {:else}
    <!-- YouTube URL Tab -->
    <div class="url-input-container">
      <div class="url-input-section">
        <label for="youtube-url" class="url-label">
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M22.54 6.42a2.78 2.78 0 0 0-1.94-2C18.88 4 12 4 12 4s-6.88 0-8.6.46a2.78 2.78 0 0 0-1.94 2A29 29 0 0 0 1 11.75a29 29 0 0 0 .46 5.33A2.78 2.78 0 0 0 3.4 19c1.72.46 8.6.46 8.6.46s6.88 0 8.6-.46a2.78 2.78 0 0 0 1.94-2 29 29 0 0 0 .46-5.25 29 29 0 0 0-.46-5.33z"></path>
            <polygon points="9.75 15.02 15.5 11.75 9.75 8.48 9.75 15.02"></polygon>
          </svg>
          YouTube URL
        </label>
        <input
          id="youtube-url"
          type="url"
          placeholder="https://www.youtube.com/watch?v=..."
          class="url-input"
          bind:value={youtubeUrl}
          disabled={processingUrl}
        />
        <div class="url-actions">
          <button
            type="button"
            class="cancel-url-button"
            on:click={cancelUrlProcessing}
            disabled={isCancelling}
            title={isCancelling ? 'Cancelling...' : (processingUrl ? 'Cancel processing' : 'Clear URL')}
          >
            {isCancelling ? 'Cancelling...' : (processingUrl ? 'Cancel' : 'Clear')}
          </button>
          <button 
            class="process-url-button" 
            on:click={processYouTubeUrl}
            disabled={processingUrl || !youtubeUrl.trim()}
            title="Process YouTube video for transcription"
          >
            {processingUrl ? 'Processing...' : 'Process Video'}
          </button>
        </div>
      </div>

      {#if urlError}
        <div class="message error-message">
          <div class="message-icon">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="8" x2="12" y2="12"></line>
              <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
          </div>
          <div class="message-content">{urlError}</div>
        </div>
      {/if}
      
      {#if processingUrl}
        <div class="progress-container">
          <div class="progress-header">
            <span class="progress-text">{urlProgress}%</span>
          </div>
          <div class="progress-bar">
            <div class="progress-fill" style="width: {urlProgress}%"></div>
          </div>
          {#if urlStatusMessage}
            <p class="status-message">{urlStatusMessage}</p>
          {/if}
        </div>
      {/if}
      
      <div class="url-info">
        <p class="url-description">
          Enter a YouTube video URL to download and transcribe the video automatically.
          The video will be processed and available in your media library just like uploaded files.
        </p>
        <div class="supported-formats">
          <p>Supported: YouTube videos and playlists</p>
        </div>
      </div>
    </div>
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
  
  .tab-navigation {
    display: flex;
    gap: 0.5rem;
    border-bottom: 1px solid var(--border-color);
    margin-bottom: 1rem;
  }
  
  .tab-button {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1rem;
    background: none;
    border: none;
    cursor: pointer;
    color: var(--text-secondary);
    font-size: 0.95rem;
    font-weight: 500;
    border-radius: 6px 6px 0 0;
    transition: all 0.2s ease;
    position: relative;
  }
  
  .tab-button:hover {
    color: var(--primary-color);
    background-color: var(--hover-color, rgba(59, 130, 246, 0.05));
  }
  
  .tab-button.active {
    color: var(--primary-color);
    background-color: transparent;
    border-bottom: 2px solid var(--primary-color);
  }
  
  .tab-button.active::after {
    content: '';
    position: absolute;
    bottom: -1px;
    left: 0;
    right: 0;
    height: 2px;
    background-color: var(--primary-color);
    border-radius: 2px 2px 0 0;
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

  .progress-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
  }

  .time-remaining {
    font-size: 0.8rem;
    color: var(--primary-color);
    font-weight: 500;
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
    font-size: 0.8rem;
    color: var(--text-color);
    font-weight: 500;
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
  
  .duplicate-message {
    background-color: rgba(59, 130, 246, 0.15);
    color: var(--primary-color);
    padding: 1.25rem;
    border-radius: 8px;
    font-size: 1rem;
    display: flex;
    align-items: flex-start;
    gap: 1rem;
    margin-bottom: 1.5rem;
    border: 1px solid var(--primary-color);
    border-left: 6px solid var(--primary-color);
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.05);
    position: relative;
    z-index: 10;
  }
  
  #duplicate-notification {
    display: flex !important;
    opacity: 1 !important;
    visibility: visible !important;
  }
  
  .duplicate-message strong {
    display: block;
    font-size: 1.1rem;
    margin-bottom: 0.5rem;
    color: var(--primary-color);
  }
  
  .duplicate-message p {
    margin: 0 0 0.75rem 0;
    line-height: 1.5;
  }
  
  .message-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--primary-color);
    flex-shrink: 0;
  }
  
  .message-content {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  
  .message-actions {
    display: flex;
    gap: 0.75rem;
  }
  
  .btn-acknowledge {
    padding: 0.5rem 1rem;
    background-color: var(--primary-color);
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-weight: 500;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
    transition: all 0.2s ease;
  }
  
  .btn-acknowledge:hover {
    opacity: 0.9;
    transform: translateY(-1px);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }
  
  /* URL Input Styles */
  .url-input-container {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
  }
  
  .url-input-section {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }
  
  .url-label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 1rem;
    font-weight: 600;
    color: var(--text-primary);
  }
  
  .url-label svg {
    color: #ff0000; /* YouTube red */
  }
  
  .url-input {
    width: 100%;
    padding: 0.75rem;
    border: 2px solid var(--border-color);
    border-radius: 8px;
    font-size: 1rem;
    background-color: var(--surface-color);
    color: var(--text-primary);
    transition: border-color 0.2s ease;
  }
  
  .url-input:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }
  
  .url-input:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  
  .url-actions {
    display: flex;
    gap: 0.5rem;
    justify-content: flex-end;
  }
  
  .cancel-url-button {
    background-color: transparent;
    border: 1px solid var(--border-color);
    color: var(--text-color);
    border-radius: 6px;
    padding: 0.5rem 1rem;
    cursor: pointer;
    font-size: 0.9rem;
    transition: all 0.2s ease;
  }
  
  .cancel-url-button:hover:not(:disabled) {
    border-color: var(--primary-color);
    color: var(--primary-color);
  }
  
  .cancel-url-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  
  .process-url-button {
    background-color: var(--primary-color);
    color: white;
    border: none;
    border-radius: 6px;
    padding: 0.5rem 1rem;
    cursor: pointer;
    font-size: 0.9rem;
    font-weight: 500;
    transition: all 0.2s ease;
  }
  
  .process-url-button:hover:not(:disabled) {
    background-color: var(--primary-hover, #2563eb);
    transform: translateY(-1px);
  }
  
  .process-url-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  
  .url-info {
    background-color: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 1rem;
  }
  
  .url-description {
    margin: 0 0 0.75rem 0;
    font-size: 0.9rem;
    color: var(--text-secondary);
    line-height: 1.5;
  }
  
  /* Dark mode adjustments for URL components */
  :global(.dark) .url-input {
    background-color: var(--surface-color);
    border-color: var(--border-color);
    color: var(--text-primary);
  }
  
  :global(.dark) .url-input:focus {
    border-color: var(--primary-color);
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.2);
  }
  
  :global(.dark) .url-info {
    background-color: var(--surface-color);
    border-color: var(--border-color);
  }
</style>
