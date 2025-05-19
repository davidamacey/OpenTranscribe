<script>
  import { slide } from 'svelte/transition';
  import Plyr from 'plyr';
  import 'plyr/dist/plyr.css';
  import { onMount, onDestroy, afterUpdate } from 'svelte';
  import { writable } from 'svelte/store';
  import axiosInstance from '$lib/axios';
  import TagsEditor from '$components/TagsEditor.svelte';
  import CommentSection from '$components/CommentSection.svelte';
  import SpeakerStats from '$components/SpeakerStats.svelte';
  import { formatDuration, formatTimestampWithMillis } from '$lib/utils/formatting';
  import { authStore } from '$stores/auth'; // Corrected import path

  // JSDoc type definitions
  /**
   * @typedef {object} Tag
   * @property {number} id
   * @property {string} name
   */

  /**
   * @typedef {Object} SpeakerTime
   * @property {Object.<string, number>} [by_speaker] // Speaker time mapped by speaker name
   * @property {number} [total] // Total talk time
   */

  /**
   * @typedef {Object} Interruptions
   * @property {Object.<string, number>} [by_speaker] // Interruptions count mapped by speaker name
   * @property {number} [total] // Total interruptions
   */

  /**
   * @typedef {Object} TurnTaking
   * @property {Object.<string, number>} [by_speaker] // Turn count mapped by speaker name
   * @property {number} [total_turns] // Total turns
   */

  /**
   * @typedef {Object} Questions
   * @property {Object.<string, number>} [by_speaker] // Questions count mapped by speaker name
   * @property {number} [total] // Total questions
   */

  /**
   * @typedef {object} SpeakerSpecificMetrics
   * // Define known speaker-specific metrics here. Examples:
   * @property {number} [word_count] 
   * @property {number} [speaking_time]
   */
  
  /**
   * @typedef {object} OverallFileMetrics
   * @property {number} [word_count] // Total words in the transcript
   * @property {number} [duration_seconds] // Duration of the audio/video file in seconds
   * @property {string} [clarity_score] // e.g., "Good", "Fair", "Poor"
   * @property {number} [sentiment_score] // e.g., from -1 (negative) to 1 (positive)
   * @property {number} [sentiment_magnitude] // Strength of sentiment
   * @property {number} [silence_ratio] // Ratio of silence in the audio
   * @property {number} [speaking_pace] // Average words per minute
   * @property {string} [language] // Detected language
   * @property {SpeakerTime} [talk_time] // Optional: total talk time in seconds, broken down by speaker
   * @property {Interruptions} [interruptions] // Optional: count of interruptions, broken down by speaker
   * @property {TurnTaking} [turn_taking] // Optional: metric for turn-taking balance, broken down by speaker
   * @property {Questions} [questions] // Optional: count of questions asked, broken down by speaker
   */
   
  /**
   * @typedef {object} Analytics
   * @property {number} [word_count] // Total words in the transcript
   * @property {number} [duration_seconds] // Duration of the audio/video file in seconds
   * @property {string} [clarity_score] // e.g., "Good", "Fair", "Poor"
   * @property {number} [sentiment_score] // e.g., from -1 (negative) to 1 (positive)
   * @property {number} [sentiment_magnitude] // Strength of sentiment
   * @property {number} [silence_ratio] // Ratio of silence in the audio
   * @property {number} [speaking_pace] // Average words per minute
   * @property {string} [language] // Detected language
   * @property {SpeakerTime} talk_time // Required: total talk time in seconds, broken down by speaker
   * @property {Interruptions} [interruptions] // Optional: count of interruptions, broken down by speaker
   * @property {TurnTaking} [turn_taking] // Optional: metric for turn-taking balance, broken down by speaker
   * @property {Questions} [questions] // Optional: count of questions asked, broken down by speaker
   */

  /**
   * @typedef {object} FileAnalytics
   * @property {OverallFileMetrics} [overall] // Overall metrics for the file
   * @property {Object.<string, SpeakerSpecificMetrics>} [speakers] // Metrics per speaker
   */

  /**
   * @typedef {object} TranscriptSegment
   * @property {number} start_time
   * @property {number} end_time
   * @property {string} text
   * @property {string} [speaker_label] // Optional speaker label
   */

  /**
   * @typedef {object} FileObject
   * @property {number} id
   * @property {string} filename
   * @property {string} file_type
   * @property {string} uploaded_at
   * @property {string} download_url
   * @property {string} [preview_url] // For video preview
   * @property {string} [storage_path] // Path in storage (S3/MinIO)
   * @property {Array<TranscriptSegment>} [transcript]
   * @property {Array<Tag>} [tags]
   * @property {FileAnalytics} [analytics]
   * @property {string} [created_at]
   * @property {string} [updated_at]
   * @property {number} [version]
   * @property {string} [error_message] // If status is 'error'
   * @property {number} [progress] // Processing progress (0-100)
   * @property {string} [status] // Status of the file: 'pending', 'processing', 'completed', 'error'
   * @property {number} [size] // File size in bytes
   * @property {number} [duration] // Duration of the audio/video in seconds
   * @property {string} [description] // Description of the file
   * @property {Array<string>} [speakers] // List of speakers in the file
   */

  // Use more generic typing for component references
  /** @typedef {any} PlayerComponent */

  // Props
  /** @type {string} */
  export let id = '';

  /** @type {FileObject | null} */
  let file = null;
  let fileId = '';
  let videoUrl = '';
  let errorMessage = '';
  let apiBaseUrl = ''; // Will store the base API URL
  /** @type {any | null} */ // Using any for Plyr type as it doesn't have a default export
  let player = null;
  let currentTime = 0;
  let duration = 0;
  let isLoading = true;
  let transcriptComponent = null; // Reference to the transcript component
  let transcriptText = '';
  let isEditingTranscript = false;
  let editedTranscript = '';
  let savingTranscript = false;
  let transcriptError = '';
  let isTagsExpanded = false; // Control for tags dropdown
  let isAnalyticsExpanded = false; // Control for analytics dropdown
  let activeSpeaker = '';

  // These variables are already declared above

  /** @type {import('svelte/store').Writable<FileObject|null>} */
  const reactiveFile = writable(null);

  $: if (file) {
    reactiveFile.set(file);
  }

  // Video player initialization flag to track status
  let playerInitialized = false;
  let videoElementChecked = false;
  
  // Use afterUpdate to check for video element after DOM updates
  afterUpdate(() => {
    if (videoUrl && !videoElementChecked && !playerInitialized) {
      console.log('FileDetail: Checking for video element after update');
      // Use requestAnimationFrame to ensure we're checking after the browser has painted
      window.requestAnimationFrame(() => {
        const videoElement = document.querySelector('#player');
        if (videoElement) {
          console.log('FileDetail: Video element found in DOM after update');
          // Delay slightly to ensure the element is fully rendered
          setTimeout(() => {
            initializePlayer();
            videoElementChecked = true;
          }, 100);
        } else {
          console.log('FileDetail: Video element not found yet, will try again next update');
          // Reset the flag so we keep trying on subsequent updates
          videoElementChecked = false;
        }
      });
    }
  });
  
  // Fetch file details on component mount
  onMount(() => {
    // Determine the API base URL based on the current environment
    const origin = window.location.origin;
    apiBaseUrl = origin;
    
    // Try to extract file ID from multiple possible sources
    // 1. First check if ID was passed as a prop
    if (id) {
      console.log(`FileDetail: Using provided ID prop: ${id}`);
      fileId = id;
      fetchFileDetails();
      return;
    }
    
    // 2. Try to get ID from URL parameters
    const urlSearchParams = new URLSearchParams(window.location.search);
    const params = Object.fromEntries(urlSearchParams.entries());
    
    if (params.id) {
      console.log(`FileDetail: Using ID from URL query: ${params.id}`);
      fileId = params.id;
      fetchFileDetails();
      return;
    }
    
    // 3. Try to extract from path segments (/:id format)
    const pathParts = window.location.pathname.split('/');
    const lastPathPart = pathParts[pathParts.length - 1];
    
    if (lastPathPart && !isNaN(Number(lastPathPart))) {
      console.log(`FileDetail: Using ID from URL path: ${lastPathPart}`);
      fileId = lastPathPart;
      fetchFileDetails();
      return;
    }
    
    // If we get here, we couldn't find an ID
    console.error('FileDetail: Could not determine file ID from props or URL');
    errorMessage = 'No file ID provided';
    isLoading = false;
  });
  
  // Cleanup on component destroy
  onDestroy(() => {
    // Clean up Plyr instance
    if (player) {
      console.log('FileDetail: Destroying player on component destroy');
      try {
        player.destroy();
      } catch (err) {
        console.error('Error destroying player:', err);
      }
    }
  });

  async function fetchFileDetails() {
    isLoading = true;
    errorMessage = '';
    try {
      console.log(`FileDetail: Fetching details for file ID: ${fileId}`);
      const response = await axiosInstance.get(`/files/${fileId}`);
      
      console.log('FileDetail: File data received:', response.status);
      console.log('FileDetail: Complete file data:', response.data);
      file = response.data;
      
      if (!file) {
        console.error('FileDetail: File data is null or undefined');
        errorMessage = 'Error loading file data';
        isLoading = false;
        return;
      }
      
      // Enhanced debugging for video URL handling
      console.log('FileDetail: Raw preview_url:', file.preview_url || 'null/undefined');
      console.log('FileDetail: Raw download_url:', file.download_url || 'null/undefined');
      
      // Check if we have any URL at all
      if (!file.preview_url && !file.download_url) {
        console.error('FileDetail: Neither preview_url nor download_url is available');
        console.log('FileDetail: Full file data for debugging:', JSON.stringify(file, null, 2));
      }
      
      // Handle URL choices based on path type - with enhanced error handling
      // Use the simple-video endpoint which returns the complete video file
      // This is not efficient for large files but works reliably for development
      videoUrl = `${apiBaseUrl}/api/files/${fileId}/simple-video`;
      console.log('FileDetail: Using simple-video endpoint for direct download:', videoUrl);
      
      // Reset video element check flag to prompt afterUpdate to try initialization
      videoElementChecked = false;
      
      if (videoUrl && !videoUrl.startsWith('/') && !videoUrl.startsWith('http')) {
        videoUrl = '/' + videoUrl;
        console.log('FileDetail: Added leading slash to URL:', videoUrl);
      }
      
      console.log('FileDetail: Final videoUrl chosen:', videoUrl || 'none');
      
      transcriptText = file.transcript ? file.transcript.map(seg => `${seg.speaker_label || 'Unknown'}: ${seg.text}`).join('\n') : 'No transcript available.';
      editedTranscript = transcriptText;
      
      console.log('FileDetail: File status:', file.status);
      console.log('FileDetail: Storage path:', file.storage_path || 'none');
      
      if (videoUrl) {
        console.log('FileDetail: S3 direct URL is available for playback:', videoUrl);
        // Reset flag to prompt afterUpdate to try initialization
        videoElementChecked = false;
      } else {
        console.warn('FileDetail: No video URL available - investigating why');
        // Add more debugging information if URL is missing
        if (file.status !== 'completed') {
          console.log('FileDetail: File not completed yet, status =', file.status);
          errorMessage = `Video not available yet. File status: ${file.status}`;
        } else if (!file.storage_path) {
          console.log('FileDetail: No storage path available');
          errorMessage = 'Video URL not available. No storage path found.';
        } else {
          console.log('FileDetail: Unknown reason for missing URL');
          errorMessage = 'Video URL not available. The file might still be processing.';
        }
      }
      if (file.status === 'processing') {
        // If still processing, poll for updates
        // This is a simple polling mechanism; consider WebSockets for real-time updates
        setTimeout(fetchFileDetails, 5000); 
      }

    } catch (err) {
      console.error('Error fetching file details:', err);
      // Log more detailed error information
      console.error('Error fetching file details:', err);
      
      // Define an ErrorLike type with JSDoc for better error handling
      /**
       * @typedef {object} ErrorResponse
       * @property {number} status - HTTP status code
       * @property {string} statusText - Status text
       * @property {any} data - Response data
       */
       
      /**
       * @typedef {object} ErrorWithResponse
       * @property {ErrorResponse} response - Error response object
       * @property {object} [request] - Error request object
       */
       
      /** @type {ErrorWithResponse|Error|any} */
      const error = err;
      
      // Using a structured approach with proper type checking for all properties
      if (error && typeof error === 'object') {
        if (error.response && typeof error.response === 'object') {
          const response = error.response;
          
          console.error('Error response:', {
            status: response.status,
            statusText: response.statusText,
            data: response.data
          });
          
          if (response.status === 404) {
            errorMessage = `File not found. Please check the file ID.`;
          } else if (response.status === 401 || response.status === 403) {
            errorMessage = `You don't have permission to access this file.`;
          } else {
            errorMessage = `Server error: ${response.status || 'unknown'}. Please try again later.`;
          }
        } else if (error.request && typeof error.request === 'object') {
          console.error('Error request:', error.request);
          errorMessage = 'Network error. Please check your connection.';
        } else if (error.message && typeof error.message === 'string') {
          errorMessage = `Error: ${error.message}`;
        } else {
          errorMessage = 'Failed to load file details. Please try again later.';
        }
      } else {
        errorMessage = 'An unknown error occurred. Please try again later.';
      }
      file = null;
    } finally {
      isLoading = false;
    }
  }

  /**
   * Initialize the Plyr video player
   */
  function initializePlayer() {
    if (playerInitialized) {
      console.log('FileDetail: Player already initialized, skipping');
      return;
    }
    
    console.log('FileDetail: Initializing Plyr player with URL:', videoUrl);
    // Make sure we're checking for the video element with a more robust approach
    const videoElement = /** @type {HTMLVideoElement|null} */ (document.querySelector('#player'));
    
    if (!videoElement) {
      console.error('FileDetail: Video element not found in DOM');
      // Log debug information about the DOM structure
      console.log('FileDetail: DOM Structure:', 
        Array.from(document.querySelectorAll('body > *')).map(el => el.tagName).join(', '));
      console.log('FileDetail: Video container exists:', 
        document.querySelector('.video-player-container') !== null);
      return;
    }
    
    // Make sure the video has a valid source before initializing
    if (!videoUrl) {
      console.error('FileDetail: No video URL provided');
      return;
    }
    
    // Set source to make sure it's available
    if (videoElement.querySelector('source')) {
      const sourceElement = videoElement.querySelector('source');
      if (sourceElement) {
        sourceElement.src = videoUrl;
        videoElement.load(); // Force reload with new source
      }
    }
    
    // Clear previous Plyr instance if any
    if (player) {
      console.log('FileDetail: Destroying previous player instance');
      try {
        player.destroy();
      } catch (err) {
        console.error('FileDetail: Error destroying previous player:', err);
      }
      player = null;
    }
    
    try {
      // Simplest possible Plyr initialization
      player = new Plyr('#player', {
        controls: ['play-large', 'play', 'progress', 'current-time', 'mute', 'volume', 'fullscreen']
      });
      
      // Only track timeupdate and error events
      player.on('timeupdate', () => {
        currentTime = player.currentTime;
      });

      player.on('loadedmetadata', () => {
        console.log('FileDetail: Video metadata loaded');
        if (player && player.duration) {
          duration = player.duration;
        }
      });

      player.on('error', () => {
        console.error('FileDetail: Video player error');
        errorMessage = 'Error loading video. The file may not be available or supported.';
      });
      
      // Listen for video error events directly on the video element
      videoElement.addEventListener('error', (e) => {
        console.error('FileDetail: Native video error:', e);
        errorMessage = 'Error loading video. Please try again or download the file directly.';
      });
      
      // Log detailed stream information to the console
      console.log('FileDetail: Player initialized with source:', videoUrl);
      
      // Add a canplay event listener to confirm when video is actually ready
      videoElement.addEventListener('canplay', () => {
        console.log('FileDetail: Video CAN PLAY event fired - video is ready to play');
      });
      
      // Add loadstart event to track when video starts loading
      videoElement.addEventListener('loadstart', () => {
        console.log('FileDetail: Video LOADSTART event fired - loading has begun');
      });
      
      // Track progress events
      videoElement.addEventListener('progress', () => {
        console.log('FileDetail: Video PROGRESS event fired - download in progress');
        // Log what's been buffered
        if (videoElement.buffered.length) {
          console.log(`FileDetail: Buffered ${videoElement.buffered.end(0)} of ${videoElement.duration} seconds`);
        }
      });
      
      // Log detailed stream info for debugging
      console.log('FileDetail: Video element details:', {
        readyState: videoElement.readyState,
        networkState: videoElement.networkState, 
        error: videoElement.error,
        src: videoElement.currentSrc || videoUrl
      });
    } catch (err) {
      console.error('FileDetail: Error initializing player:', err);
      // Safely get error message from error object
      const errorMsg = (err && typeof err === 'object' && 'message' in err) 
        ? String(err.message) 
        : 'Unknown error';
      errorMessage = 'Could not initialize video player. ' + errorMsg;
    }
  }

  async function saveTranscript() {
    if (!file || !file.id) return;
    savingTranscript = true;
    transcriptError = '';
    try {
      // Basic parsing: assumes "Speaker: Text" format per line
      const updatedTranscriptSegments = editedTranscript.split('\n').map((line, index) => {
        const parts = line.match(/^([^:]+):\s*(.*)$/);
        let speaker_label = `SPK${index % 2}`; // Default if no match
        let text = line;
        if (parts && parts.length === 3) {
          speaker_label = parts[1].trim();
          text = parts[2].trim();
        }
        // Find original timing if possible, or assign new ones (this part is complex without UI for timing)
        // For simplicity, this example doesn't re-time segments, it just updates text and speaker.
        // A real implementation would need a more sophisticated editor or rely on backend re-processing.
        // Add proper null/undefined checks to avoid runtime errors
        const existingSegment = file && file.transcript && Array.isArray(file.transcript) ? file.transcript[index] : null;
        return {
          start_time: existingSegment ? existingSegment.start_time : index * 5, // Placeholder timing
          end_time: existingSegment ? existingSegment.end_time : (index + 1) * 5, // Placeholder timing
          text: text,
          speaker_label: speaker_label,
        };
      });

      await axiosInstance.put(`/files/${file.id}/transcript`, {
        transcript: updatedTranscriptSegments,
      });
      isEditingTranscript = false;
      transcriptText = editedTranscript; // Update the displayed transcript
      if (file) file.transcript = updatedTranscriptSegments; // Update local file object
    } catch (err) {
      console.error('Error saving transcript:', err);
      // Safely get error detail from error response
      let errorDetail = 'An unknown error occurred';
      
      if (err && typeof err === 'object') {
        // Handle Axios error response
        const axiosError = /** @type {import('axios').AxiosError} */ (err);
        
        if (axiosError.response) {
          // The request was made and the server responded with a status code
          // that falls out of the range of 2xx
          const responseData = axiosError.response.data;
          if (responseData && typeof responseData === 'object' && 'detail' in responseData) {
            errorDetail = String(responseData.detail);
          } else if (axiosError.response.statusText) {
            errorDetail = `${axiosError.response.status}: ${axiosError.response.statusText}`;
          } else {
            errorDetail = `Server responded with status ${axiosError.response.status}`;
          }
        } else if (axiosError.request) {
          // The request was made but no response was received
          errorDetail = 'No response from server';
        } else {
          // Something happened in setting up the request that triggered an Error
          errorDetail = axiosError.message || 'Error setting up request';
        }
      } else if (err) {
        errorDetail = String(err);
      }
      
      transcriptError = `Failed to save transcript. ${errorDetail}`;
    } finally {
      savingTranscript = false;
    }
  }

  function toggleEditTranscript() {
    if (isEditingTranscript) {
      isEditingTranscript = false;
    } else {
      if (file && file.transcript && file.transcript.length > 0) {
        editedTranscript = file.transcript.map(segment => `${formatTimestampWithMillis(segment.start_time)} [${segment.speaker_label || 'Unknown'}]: ${segment.text}`).join('\n');
        isEditingTranscript = true;
      } else {
        errorMessage = 'No transcript available to edit';
      }
    }
  }
  
  /**
   * Export transcript to a downloadable text file
   */
  function exportTranscript() {
    if (!file || !file.transcript || file.transcript.length === 0) {
      errorMessage = 'No transcript available to export';
      return;
    }
    
    try {
      // Format transcript for export
      const transcriptText = file.transcript.map(segment => 
        `${formatTimestampWithMillis(segment.start_time)} - ${formatTimestampWithMillis(segment.end_time)}\n` +
        `[${segment.speaker_label || 'Unknown'}]: ${segment.text}\n`
      ).join('\n');
      
      // Create file and trigger download
      const blob = new Blob([transcriptText], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${file.filename.replace(/\.[^\.]+$/, '')}_transcript.txt`;
      document.body.appendChild(a);
      a.click();
      
      // Clean up
      setTimeout(() => {
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }, 100);
    } catch (err) {
      console.error('Error exporting transcript:', err);
      errorMessage = 'Failed to export transcript';
    }
  }

  /** 
   * @param {Event} event 
   */
  function handleTranscriptInput(event) {
    // Cast target to HTMLTextAreaElement to access value property
    const target = /** @type {HTMLTextAreaElement} */ (event.target);
    editedTranscript = target?.value;
  }

  /**
   * Handles tags updated event from TagsEditor.
   * @param {CustomEvent} event - The event containing updated tags.
   */
  function handleTagsUpdated(event) {
    if (file) {
      file.tags = event.detail.tags;
    }
  }
  // Placeholder for handling comment updates from CommentSection
  /** @param {CustomEvent} event */
  function handleCommentAddedOrUpdated(event) {
    // console.log('Comment added or updated:', event.detail);
    // Potentially refresh comments or update local state if needed
    // For now, we assume CommentSection handles its own state mostly
    fetchFileDetails(); // Re-fetch to get updated comment counts or data if necessary
  }

  /** @param {CustomEvent} event */
  function handleCommentDeleted(event) {
    // console.log('Comment deleted:', event.detail);
    fetchFileDetails(); // Re-fetch to get updated comment counts or data if necessary
  }

  /** @param {CustomEvent} event - Event containing the seek time */
  function handleSeekTo(event) {
    if (player && typeof player.currentTime === 'number') {
      player.currentTime = event.detail;
    }
  }

  onMount(() => {
    // This ensures player is initialized after DOM is ready if videoUrl is already available
    if (videoUrl && !player) {
      initializePlayer();
    }
  });

  onDestroy(() => {
    // Clean up player on component destruction
    if (player) {
      console.log('FileDetail: Destroying player on component unmount');
      player.destroy();
      player = null;
    }
  });

  /**
   * Format file size in bytes to a human-readable format
   * @param {number} bytes - File size in bytes
   * @returns {string} Formatted file size
   */
  function formatFileSize(bytes) {
    if (!bytes || isNaN(bytes)) return 'Unknown';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let size = bytes;
    let unitIndex = 0;
    
    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024;
      unitIndex++;
    }
    
    return `${size.toFixed(1)} ${units[unitIndex]}`;
  }
  
  // formatDuration is already imported at the top of the file
  
  // Helper to simulate processing for UI testing
  function simulateProcessing() {
    if (!file || file.status !== 'processing') return;
    let progress = file.progress || 0;
    const interval = setInterval(() => {
      progress += 10;
      if (progress >= 100) {
        clearInterval(interval);
        if (file) {
          file.status = 'completed'; // Simulate completion
          file.progress = 100;
          // Simulate some analytics data appearing
          file.analytics = {
            overall: {
              word_count: 1234,
              duration_seconds: 300,
              clarity_score: 'Good',
              sentiment_score: 0.7,
              sentiment_magnitude: 1.2,
              silence_ratio: 0.1,
              speaking_pace: 150,
              language: 'en-US',
              talk_time: {
                by_speaker: {
                  'Speaker A': 120,
                  'Speaker B': 130
                },
                total: 250
              },
              interruptions: {
                by_speaker: {
                  'Speaker A': 2,
                  'Speaker B': 1
                },
                total: 3
              },
              turn_taking: {
                by_speaker: {
                  'Speaker A': 5,
                  'Speaker B': 4
                },
                total_turns: 9
              },
              questions: {
                by_speaker: {
                  'Speaker A': 3,
                  'Speaker B': 2
                },
                total: 5
              }
            },
            speakers: {
              'Speaker A': { word_count: 600, speaking_time: 120 },
              'Speaker B': { word_count: 634, speaking_time: 130 },
            }
          };
          reactiveFile.set(file); // Trigger reactivity
          initializePlayer(); // Re-initialize player if source might have changed (e.g. preview_url becomes available)
        }
      } else if (file) {
        file.progress = progress;
        reactiveFile.set(file); // Trigger reactivity
      }
    }, 500);
  }

  // Reactive statement to re-initialize player if videoUrl changes after initial mount
  // and player wasn't initialized (e.g., fetched file details did not have URL initially)
  $: if (videoUrl && !player && !isLoading) {
    initializePlayer();
  }

  // Simulate processing if status is 'processing'
  $: if (file && file.status === 'processing') {
      simulateProcessing();
  }

</script>

<svelte:head>
  <title>{file ? `File: ${file.filename}` : 'Loading File...'}</title>
</svelte:head>

<div class="file-detail-page">
  {#if isLoading}
    <div class="loading-container">
      <div class="spinner"></div>
      <p>Loading file details...</p>
    </div>
  {:else if errorMessage}
    <div class="error-container">
      <p class="error-message">{errorMessage}</p>
      <button on:click={fetchFileDetails}>Try Again</button>
    </div>
  {:else if file}
    <div class="file-header">
      <div class="file-header-main">
        <div class="title-status">
          <h1>{file.filename}</h1>
          <div class="status-badge status-{file.status}">{file.status}</div>
        </div>
        <div class="file-metadata">
          {#if file.size}
            <span class="metadata-item">Size: {formatFileSize(file.size)}</span>
          {/if}
          {#if file.duration}
            <span class="metadata-item">Duration: {formatDuration(file.duration)}</span>
          {/if}
          {#if file.created_at}
            <span class="metadata-item">Uploaded: {new Date(file.created_at).toLocaleDateString()}</span>
          {/if}
        </div>
        
        <!-- File summary section -->
        <div class="file-summary">
          <p>
            {file.description || `This file contains ${file.duration ? formatDuration(file.duration) + ' of ' : ''}audio${file.speakers && file.speakers.length ? ' with ' + file.speakers.length + ' speakers' : ''}. ${file.transcript ? 'Transcript is available.' : ''}`}
          </p>
        </div>
      </div>
    </div>
    
    <!-- Tags now moved to a dropdown below video -->
    <!-- See the implementation below the video player -->

    {#if file.status === 'error' && file.error_message}
      <div class="status-message">
        <p><strong>Processing Status:</strong> {file.error_message}</p>
      </div>
    {/if}

    {#if file.status === 'processing'}
      <div class="processing-info">
        <p>File is processing... Progress: {file.progress || 0}%</p>
        <div class="progress-bar">
          <div class="progress-bar-inner" style="width: {file.progress || 0}%;"></div>
        </div>
      </div>
    {/if}

    <div class="main-content-grid">
      <!-- Left column: Video player, tags, analytics, and comments -->
      <section class="video-column">
        <h4>Video</h4>
        <div class="video-player-container">
          {#if videoUrl}
            <!-- Simple video player with a11y track for captions -->
            <video id="player" playsinline controls crossorigin="anonymous">
              <source src={videoUrl} type="video/mp4" />
              <!-- Add caption track for accessibility -->
              <track kind="captions" label="English" src="data:text/vtt,WEBVTT" default />
              Your browser does not support the video element.
            </video>
            
            {#if errorMessage}
              <p class="error-message">{errorMessage}</p>
              <button class="retry-button" on:click={fetchFileDetails}>Retry Loading Video</button>
            {/if}
          {:else if file.status === 'completed'}
            <div class="no-preview">Video preview not available. You can try downloading the file.</div>
          {:else if file.status !== 'processing'}
             <div class="no-preview">Video processing or not available.</div>
          {/if}
        </div>
        
        <!-- Download button area -->
        {#if file.download_url}
          <div class="download-container">
            <a href={file.download_url} class="download-button" download={file.filename}>
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="7 10 12 15 17 10"></polyline>
                <line x1="12" y1="15" x2="12" y2="3"></line>
              </svg>
              <span>Download</span>
            </a>
          </div>
        {/if}
        
        <!-- Tags dropdown section -->
        <div class="tags-dropdown-section">
          <button class="tags-header" on:click={() => isTagsExpanded = !isTagsExpanded} on:keydown={e => e.key === 'Enter' && (isTagsExpanded = !isTagsExpanded)} aria-expanded={isTagsExpanded}>
            <h4 class="section-heading">Tags</h4>
            <div class="tags-preview">
              {#if file.tags && file.tags.length > 0}
                {#each file.tags.slice(0, 3) as tag, i}
                  <span class="tag-chip">{tag && tag.name ? tag.name : tag}</span>
                {/each}
                {#if file.tags.length > 3}
                  <span class="tag-chip more">+{file.tags.length - 3} more</span>
                {/if}
              {:else}
                <span class="no-tags">No tags</span>
              {/if}
            </div>
            <span class="dropdown-toggle" aria-hidden="true">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="transform: rotate({isTagsExpanded ? '180deg' : '0deg'})">
                <polyline points="6 9 12 15 18 9"></polyline>
              </svg>
            </span>
          </button>
          
          {#if isTagsExpanded}
            <div class="tags-content" transition:slide={{ duration: 200 }}>
              {#if file && file.id}
                <TagsEditor fileId={String(file.id)} tags={file.tags || []} on:tagsUpdated={handleTagsUpdated} />
              {:else}
                <p>Loading tags...</p>
              {/if}
            </div>
          {/if}
        </div>

        <!-- Analytics dropdown section -->
        <div class="analytics-dropdown-section">
          <button class="analytics-header" on:click={() => isAnalyticsExpanded = !isAnalyticsExpanded} on:keydown={e => e.key === 'Enter' && (isAnalyticsExpanded = !isAnalyticsExpanded)} aria-expanded={isAnalyticsExpanded}>
            <h4 class="section-heading">Analytics Overview</h4>
            <div class="analytics-preview">
              {#if file && file.analytics && file.analytics.overall}
                <span class="analytics-chip">
                  {file.analytics.overall.word_count ? `${file.analytics.overall.word_count} words` : 'Analytics available'}
                </span>
              {:else if file && file.status === 'processing'}
                <span class="analytics-chip processing">Processing...</span>
              {:else}
                <span class="no-analytics">No analytics</span>
              {/if}
            </div>
            <span class="dropdown-toggle" aria-hidden="true">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="transform: rotate({isAnalyticsExpanded ? '180deg' : '0deg'})">
                <polyline points="6 9 12 15 18 9"></polyline>
              </svg>
            </span>
          </button>
          
          {#if isAnalyticsExpanded}
            <div class="analytics-content" transition:slide={{ duration: 200 }}>
              {#if file && file.analytics && file.analytics.overall}
                <SpeakerStats 
                  analytics={{
                    talk_time: file.analytics.overall.talk_time || { by_speaker: {}, total: 0 },
                    interruptions: file.analytics.overall.interruptions || { by_speaker: {}, total: 0 },
                    turn_taking: file.analytics.overall.turn_taking || { by_speaker: {}, total_turns: 0 },
                    questions: file.analytics.overall.questions || { by_speaker: {}, total: 0 },
                    ...file.analytics.overall
                  }} 
                />
              {:else if file && file.status === 'processing'}
                <p>Analytics are being processed...</p>
              {:else if file && file.status === 'completed' && !file.analytics}
                <p>Analytics data is not available for this file.</p>
              {/if}
            </div>
          {/if}
        </div>

        <!-- Comments section below analytics (always visible) -->
        <div class="comments-section">
          <h4 class="comments-heading">Comments & Discussion</h4>
          <div class="comments-section-wrapper">
            <div class="section-header">
              <h2>Comments</h2>
              <div class="spacer"></div>
            </div>
            <CommentSection 
              fileId={file?.id ? String(file.id) : ''} 
              currentTime={currentTime} 
              on:seekTo={handleSeekTo} 
            />

          </div>
        </div>
      </section>
      
      <!-- Transcript section - now right side of page -->
      <section class="transcript-column">
        <h4>Transcript</h4>
        {#if file.transcript && file.transcript.length > 0}
          {#if isEditingTranscript}
            <textarea bind:value={editedTranscript} rows="20" class="transcript-textarea"></textarea>
            <div class="edit-actions">
              <button on:click={saveTranscript} disabled={savingTranscript}>
                {savingTranscript ? 'Saving...' : 'Save Transcript'}
              </button>
              <button on:click={toggleEditTranscript} class="cancel-button">Cancel</button>
            </div>
            {#if transcriptError}
              <p class="error-message small">{transcriptError}</p>
            {/if}
          {:else}
            <div class="transcript-display">
              {#each file.transcript as segment, i (segment.start_time + '-' + i)}
                <div
                  class="transcript-segment"
                  class:active={currentTime >= segment.start_time && currentTime < segment.end_time}
                  on:click={() => handleSeekTo(new CustomEvent('seek', { detail: segment.start_time }))}
                  role="button"
                  tabindex="0"
                  on:keydown={(e) => { if (e.key === 'Enter' || e.key === ' ') handleSeekTo(new CustomEvent('seek', { detail: segment.start_time })); }}
                >
                  <span class="timestamp">{formatTimestampWithMillis(segment.start_time)}</span>
                  <span class="speaker">{segment.speaker_label || 'Unknown'}:</span>
                  <span class="text">{segment.text}</span>
                </div>
              {/each}
            </div>
            <div class="transcript-actions">
              <button on:click={toggleEditTranscript} class="edit-transcript-button">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                </svg>
                Edit Transcript
              </button>
              <button on:click={exportTranscript} class="export-transcript-button">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                  <polyline points="7 10 12 15 17 10"></polyline>
                  <line x1="12" y1="15" x2="12" y2="3"></line>
                </svg>
                Export
              </button>
            </div>
          {/if}
        {:else if file.status === 'completed'}
          <p>No transcript available for this file.</p>
        {:else if file.status === 'processing'}
          <p>Transcript is being generated...</p>
        {:else}
          <p>Transcript not available.</p>
        {/if}
      </section>
    </div>

  {:else}
    <div class="no-file-container">
      <p>File data could not be loaded or does not exist.</p>
    </div>
  {/if}
</div>

<style>
  .file-detail-page {
    padding: 2rem;
    max-width: 1200px;
    margin: 0 auto;
    font-family: var(--font-family-sans);
    color: var(--text-color);
  }

  .loading-container, .error-container, .no-file-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 50vh;
    text-align: center;
  }

  .spinner {
    border: 4px solid rgba(0, 0, 0, 0.1);
    width: 36px;
    height: 36px;
    border-radius: 50%;
    border-left-color: var(--primary-color);
    animation: spin 1s ease infinite;
    margin-bottom: 1rem;
  }

  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }

  .file-header {
    margin-bottom: 0.5rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border-color-soft);
  }
  
  .file-header-main {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  
  .title-status {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  
  .file-metadata {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    gap: 1rem;
    font-size: 0.9rem;
    color: var(--text-color-secondary);
    margin-bottom: 0.5rem;
  }
  
  .file-summary {
    margin-top: 0.5rem;
    font-size: 0.95rem;
    line-height: 1.4;
    color: var(--text-color);
  }
  
  /* Tags dropdown styling */
  .tags-dropdown-section, .analytics-dropdown-section {
    margin-top: 0.75rem;
    margin-bottom: 0.75rem;
    background-color: var(--background-alt);
    border-radius: var(--border-radius);
    border: 2px solid var(--primary-color-light);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    overflow: hidden;
  }
  
  .tags-header, .analytics-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem 1.5rem;
    background: none;
    border: none;
    width: 100%;
    text-align: left;
    cursor: pointer;
    transition: background-color 0.2s ease;
  }
  
  .tags-header:hover, .analytics-header:hover {
    background-color: rgba(59, 130, 246, 0.05);
  }
  
  .section-heading {
    margin: 0;
    margin-top: 0;
    margin-bottom: 1rem;
    font-size: 1.2rem;
    font-weight: 600;
    color: var(--primary-color);
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border-color-soft);
  }
  
  h4 {
    margin-top: 0;
    margin-bottom: 1rem;
    font-size: 1.2rem;
    font-weight: 600;
    color: var(--primary-color);
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border-color-soft);
  }
  
  .tags-preview, .analytics-preview {
    flex: 1;
    display: flex;
    gap: 0.5rem;
    margin: 0 1rem;
    flex-wrap: wrap;
  }
  
  .tag-chip, .analytics-chip {
    background-color: rgba(59, 130, 246, 0.1);
    color: var(--primary-color);
    padding: 0.25rem 0.5rem;
    border-radius: 1rem;
    font-size: 0.75rem;
    display: inline-flex;
    align-items: center;
    border: 1px solid rgba(59, 130, 246, 0.2);
    white-space: nowrap;
    max-width: 120px;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  
  .tag-chip.more, .analytics-chip.processing {
    background-color: rgba(100, 116, 139, 0.1);
    color: var(--text-color-secondary);
  }
  
  .no-tags, .no-analytics {
    color: var(--text-color-secondary);
    font-style: italic;
    font-size: 0.9rem;
  }
  
  .dropdown-toggle {
    display: flex;
    align-items: center;
    transition: transform 0.2s ease;
  }
  
  .tags-content, .analytics-content {
    padding: 1rem 1.5rem 1.5rem;
    border-top: 1px solid var(--border-color-soft);
  }
  
  .metadata-item {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
  }

  .file-header h1 {
    font-size: 1.8rem;
    font-weight: 600;
    color: var(--heading-color);
    margin: 0;
  }

  .status-badge {
    padding: 0.3rem 0.8rem;
    border-radius: 1rem;
    font-size: 0.8rem;
    font-weight: 500;
    text-transform: capitalize;
  }
  .status-completed { background-color: rgba(34, 197, 94, 0.1); color: #22c55e; }
  .status-processing { background-color: rgba(234, 179, 8, 0.1); color: #eab308; }
  .status-error { background-color: rgba(239, 68, 68, 0.1); color: #ef4444; }
  .status-pending, .status-uploaded { background-color: rgba(100, 116, 139, 0.1); color: #64748b; }

  .status-message {
    background-color: rgba(59, 130, 246, 0.1);
    color: var(--text-color);
    padding: 0.8rem 1rem;
    border-radius: var(--border-radius);
    margin-bottom: 1rem;
    border: 1px solid rgba(59, 130, 246, 0.2);
  }
  .status-message p strong {
    color: var(--primary-color);
  }

  .processing-info {
    background-color: var(--background-alt);
    padding: 1rem;
    border-radius: var(--border-radius);
    margin-bottom: 1.5rem;
    text-align: center;
  }
  .processing-info p {
    margin: 0 0 0.5rem 0;
    font-size: 0.9rem;
  }
  .progress-bar {
    width: 100%;
    max-width: 300px;
    height: 8px;
    background-color: var(--border-color-soft);
    border-radius: 4px;
    overflow: hidden;
    margin: 0 auto;
  }
  .progress-bar-inner {
    height: 100%;
    background-color: var(--primary-color);
    transition: width 0.3s ease;
  }

  .main-content-grid {
    display: grid;
    grid-template-columns: minmax(300px, 45%) minmax(250px, 55%);
    gap: 1.5rem;
    margin-top: 1.5rem;
  }

  @media (max-width: 992px) { /* Medium devices */
    .main-content-grid {
      grid-template-columns: 1fr;
    }
  }
  
  @media (max-width: 768px) { /* Small devices */
    .main-content-grid {
      grid-template-columns: 1fr;
    }
    .video-column, .transcript-column, .analytics-column {
      margin-top: 0.75rem;
      background-color: var(--background-alt);
      padding: 1.5rem;
      border-radius: var(--border-radius);
      border: 2px solid var(--primary-color-light);
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    }
    .video-column, .transcript-column, .analytics-column {
      grid-column: span 1;
    }
  }

  .video-column, .transcript-column {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
  }
  
  .video-player-container {
    width: 100%;
    aspect-ratio: 16 / 9; /* Maintain aspect ratio */
    background-color: #000;
    border-radius: var(--border-radius-lg);
    overflow: hidden; /* Ensures Plyr fits within rounded corners */
    position: relative;
  }

  #player {
    width: 100%;
    height: 100%;
    display: block; /* remove extra space below video */
  }
  
  .no-preview {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    height: 100%;
    color: var(--text-light);
    background-color: var(--background-alt);
    font-size: 0.9rem;
    border-radius: var(--border-radius-lg);
  }

  .download-container {
    margin-top: 0.75rem;
    display: flex;
    justify-content: flex-end;
  }

  .file-actions-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 1rem;
    flex-wrap: wrap;
    gap: 0.75rem;
  }

  .download-button {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    background-color: #3b82f6; /* Use explicit color instead of variable */
    color: white !important; /* Force white text */
    padding: 0.6rem 1.2rem;
    border-radius: 10px;
    text-decoration: none !important; /* Prevent browser default styles */
    font-weight: 500;
    font-size: 0.95rem;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
    border: none;
  }
  
  .download-button:hover:not(:disabled),
  .download-button:focus:not(:disabled) {
    background-color: #2563eb; /* Darker blue on hover */
    color: white !important; /* Force white text on hover */
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
    transform: translateY(-1px);
    text-decoration: none !important;
  }
  
  .download-button:active:not(:disabled) {
    transform: translateY(0);
  }
  
  .download-button:visited {
    color: white !important; /* Ensure even visited links stay white */
  }
  
  /* Extra specificity to override any inherited styles */
  .download-container .download-button * {
    color: white !important;
  }

  .download-button svg {
    flex-shrink: 0;
  }
  
  .video-column .video-player-container {
    margin-bottom: 1rem;
  }
  
  .transcript-column .transcript-display {
    max-height: 500px;
    overflow-y: auto;
    padding-right: 0.5rem;
  }
  
  .transcript-actions {
    display: flex;
    justify-content: space-between;
    margin-top: 1rem;
    gap: 0.5rem;
  }
  
  .edit-transcript-button, .export-transcript-button {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background-color: var(--background-alt);
    border: 1px solid var(--border-color);
    color: var(--text-color);
    padding: 0.5rem 0.75rem;
    border-radius: var(--border-radius);
    font-size: 0.9rem;
    cursor: pointer;
    transition: background-color 0.2s;
  }
  
  .edit-transcript-button:hover, .export-transcript-button:hover {
    background-color: var(--primary-color-light);
    color: var(--primary-color);
  }
  
  .analytics-column {
    background-color: var(--surface-color);
    padding: 1rem;
    border-radius: var(--border-radius);
    border: 1px solid var(--border-color);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  }
  
  .stats-section, .tags-section {
    margin-top: 1rem;
    background-color: var(--surface-color);
    padding: 1rem;
    border-radius: var(--border-radius);
    border: 1px solid var(--border-color);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  }
  
  .comments-section {
    margin-top: 0.75rem;
    background-color: var(--background-alt);
    padding: 1.5rem;
    border-radius: var(--border-radius);
    border: 2px solid var(--primary-color-light);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  }
  
  .comments-heading {
    font-size: 1.2rem;
    font-weight: 600;
    color: var(--primary-color);
    margin-top: 0;
    margin-bottom: 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border-color-soft);
  }
  
  .comments-container {
    max-height: 400px;
    overflow-y: auto;
  }

  h4 {
    font-size: 1.2rem;
    font-weight: 600;
    color: var(--heading-color);
    margin-top: 0;
    margin-bottom: 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border-color-soft);
  }

  .transcript-display {
    max-height: 400px;
    overflow-y: auto;
    padding: 0.5rem;
    border: 1px solid var(--border-color);
    border-radius: var(--border-radius);
    background-color: var(--background-code);
    font-family: var(--font-family-mono);
    font-size: 0.9rem;
    line-height: 1.6;
  }

  .transcript-segment {
    padding: 0.3rem 0.5rem;
    margin-bottom: 0.2rem;
    border-radius: 3px;
    cursor: pointer;
    transition: background-color 0.2s;
  }
  .transcript-segment:hover {
    background-color: rgba(var(--primary-color-rgb), 0.1);
  }
  .transcript-segment.active {
    background-color: rgba(var(--primary-color-rgb), 0.2);
    font-weight: 500;
  }
  .transcript-segment .timestamp {
    color: var(--primary-color);
    margin-right: 0.5em;
    font-weight: 500;
  }
  .transcript-segment .speaker {
    color: var(--text-light);
    font-weight: bold;
    margin-right: 0.5em;
  }

  .transcript-textarea {
    width: 100%;
    padding: 0.8rem;
    border: 1px solid var(--border-color);
    border-radius: var(--border-radius);
    font-family: var(--font-family-mono);
    font-size: 0.9rem;
    line-height: 1.6;
    background-color: var(--background-code);
    color: var(--text-color);
    min-height: 200px;
    resize: vertical;
  }

  /* Debug styles removed as they're no longer used */

  .edit-actions {
    margin-top: 1rem;
    display: flex;
    gap: 0.5rem;
  }
  .edit-actions button {
    padding: 0.5rem 1rem;
    border: none;
    border-radius: var(--border-radius);
    cursor: pointer;
    font-weight: 500;
  }
  .edit-actions button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  .edit-actions .cancel-button {
    background-color: var(--button-secondary-bg);
    color: var(--button-secondary-text);
  }
  .edit-actions .cancel-button:hover {
    background-color: var(--button-secondary-hover-bg);
  }
  
  .edit-transcript-button {
    margin-top: 1rem;
    padding: 0.5rem 1rem;
    border: 1px solid var(--primary-color);
    background-color: transparent;
    color: var(--primary-color);
    border-radius: var(--border-radius);
    cursor: pointer;
    font-weight: 500;
    transition: background-color 0.2s, color 0.2s;
  }
  .edit-transcript-button:hover {
    background-color: rgba(var(--primary-color-rgb), 0.1);
  }

  .error-message.small {
    font-size: 0.8rem;
    color: var(--error-color);
    margin-top: 0.5rem;
  }

  /* Responsive adjustments */
  @media (max-width: 768px) {
    .file-header {
      flex-direction: column;
      align-items: flex-start;
      gap: 0.5rem;
    }
    .file-header h1 {
      font-size: 1.5rem;
    }
    .main-content-grid {
      grid-template-columns: 1fr; /* Stack columns on smaller screens */
    }
    /* Video player responsiveness is handled by aspect-ratio */
  }
</style>
