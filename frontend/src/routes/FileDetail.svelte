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

  // Speaker type is already defined above

  /**
   * @typedef {object} TranscriptSegment
   * @property {number} start_time
   * @property {number} end_time
   * @property {string} text
   * @property {string} [speaker_label] // Optional speaker label
   * @property {string} [speaker_id] // ID of the speaker
   * @property {string} [speaker_uuid] // UUID of the speaker for cross-video identification
   * @property {Speaker} [speaker] // Full speaker object with details
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
  let editingSegmentId = null;
  let editingSegmentText = '';
  let isEditingSpeakers = false;
  let savingSpeakers = false;
  let speakerError = '';
  let isTagsExpanded = false; // Control for tags dropdown
  let isAnalyticsExpanded = false; // Control for analytics dropdown
  let activeSpeaker = '';
  /**
   * @typedef {Object} Speaker
   * @property {number} id - The speaker ID
   * @property {string} name - The speaker name
   * @property {string} display_name - The display name for the speaker
   * @property {string} [color] - The color assigned to the speaker
   */
  
  /** @type {Speaker[]} */
  let speakerList = [];
  /** @type {{ [key: string]: string }} */
  let speakerColors = {};
  let loadingSpeakers = false; // Flag for speaker loading state

  // These variables are already declared above

  /** @type {import('svelte/store').Writable<FileObject|null>} */
  const reactiveFile = writable(null);

  $: if (file) {
    reactiveFile.set(file);
  }

  // Video player initialization and state tracking
  let playerInitialized = false;
  let videoElementChecked = false;
  let isPlayerBuffering = false;
  let loadStartTime = 0;
  let loadProgress = 0;
  let playerQuality = 'auto';
  let playbackSpeed = 1.0;
  let isFullscreen = false;
  let playerErrorDetails = '';
  
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
            
            // Add event listeners for detailed video metrics
            videoElement.addEventListener('waiting', () => {
              isPlayerBuffering = true;
              if (!loadStartTime) loadStartTime = Date.now();
            });
            
            videoElement.addEventListener('canplay', () => {
              isPlayerBuffering = false;
              if (loadStartTime) {
                const loadTime = Date.now() - loadStartTime;
                console.log(`FileDetail: Video loaded in ${loadTime}ms`);
                loadStartTime = 0;
              }
            });
            
            // Track loading progress
            videoElement.addEventListener('progress', () => {
              if (videoElement.buffered.length > 0 && videoElement.duration) {
                loadProgress = (videoElement.buffered.end(0) / videoElement.duration) * 100;
              }
            });
          }, 100);
        } else {
          console.log('FileDetail: Video element not found yet, will try again next update');
          // Reset the flag so we keep trying on subsequent updates
          videoElementChecked = false;
        }
      });
    }
  });
  
  /**
   * Handles clicking on a transcript segment to jump to that point in the video
   * @param {number} startTime - The start time of the segment in seconds
   */
  function handleSegmentClick(startTime) {
    if (player && player.ready) {
      console.log(`Jumping to time: ${startTime} seconds`);
      player.currentTime = startTime;
      player.play().catch(error => {
        console.error('Error playing video after segment click:', error);
      });
    } else {
      console.warn('Player not ready for seeking');
    }
  }

  /**
   * Highlights the current segment based on video playback time
   * @param {number} currentPlaybackTime - Current video playback time in seconds
   */
  function highlightCurrentSegment(currentPlaybackTime) {
    if (!file || !file.transcript || !file.transcript.segments) return;
    
    // Remove highlight from all segments
    const allSegments = document.querySelectorAll('.transcript-segment');
    allSegments.forEach(segment => {
      segment.classList.remove('active-segment');
    });
    
    // Find the current segment based on playback time
    const currentSegment = file.transcript.segments.find(segment => {
      return currentPlaybackTime >= segment.start_time && currentPlaybackTime <= segment.end_time;
    });
    
    if (currentSegment) {
      // Find and highlight the corresponding DOM element
      const segmentElement = document.querySelector(`[data-segment-id="${currentSegment.start_time}-${currentSegment.end_time}"]`);
      if (segmentElement) {
        segmentElement.classList.add('active-segment');
        // Optionally scroll into view if not visible
        segmentElement.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    }
  }
  
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

  /**
   * Fetch analytics data for a file
   * @param {number} fileId - The ID of the file to fetch analytics for
   */
  async function fetchAnalytics(fileId) {
    try {
      console.log(`FileDetail: Fetching analytics for file ID: ${fileId}`);
      const response = await axiosInstance.get(`/files/${fileId}/analytics`);
      
      if (response.data && typeof response.data === 'object') {
        console.log('FileDetail: Received analytics data:', response.data);
        
        // Update file with analytics data
        if (file) {
          file.analytics = response.data;
          reactiveFile.set(file);
        }
      } else {
        console.warn('FileDetail: No analytics data received');
      }
    } catch (error) {
      console.error('Error fetching analytics:', error);
      // If the endpoint doesn't exist, create a basic analytics structure
      // Use JavaScript-compatible error handling
      const err = error;
      
      /** @type {any} */ // Type assertion for error object
      const errorObj = err;
      if (file && errorObj && typeof errorObj === 'object' && errorObj.response && typeof errorObj.response === 'object' && errorObj.response.status === 404) {
        console.log('FileDetail: Creating default analytics structure');
          // Create a basic analytics structure from transcript data
          if (file && file.transcript && file.transcript.length > 0) {
            // Initialize with JavaScript-compatible typing
            const speakerCounts = {};
            let totalWords = 0;
            
            file.transcript.forEach(segment => {
              const speaker = segment.speaker_label || 'Unknown';
              const words = segment.text.split(/\s+/).filter(Boolean).length;
              speakerCounts[speaker] = (speakerCounts[speaker] || 0) + words;
              totalWords += words;
            });
            
            // Create analytics structure
            file.analytics = {
              overall: {
                word_count: totalWords,
                duration_seconds: file.duration || 0,
                talk_time: {
                  by_speaker: speakerCounts,
                  total: totalWords
                }
              }
            };
            reactiveFile.set(file);
          }
      }
    }
  }
  
  /**
   * Fetch transcript segments for a file
   * @param {number} fileId - The ID of the file to fetch transcript segments for
   */
  async function fetchTranscriptSegments(fileId) {
    try {
      console.log(`FileDetail: Fetching transcript segments for file ID: ${fileId}`);
      const response = await axiosInstance.get(`/api/files/${fileId}/transcript`);
      
      if (response.data && Array.isArray(response.data)) {
        console.log(`FileDetail: Received ${response.data.length} transcript segments`);
        
        // Update file with transcript segments
        if (file) {
          file.transcript = response.data;
          
          // Update transcript text
          transcriptText = file.transcript.map(seg => 
            `${formatTimestampWithMillis(seg.start_time)} [${seg.speaker_label || 'Speaker'}]: ${seg.text}`
          ).join('\n');
          
          editedTranscript = transcriptText;
          
          // Load speakers for this file
          loadSpeakers();
        }
      } else {
        console.warn('FileDetail: No transcript segments received');
        transcriptText = 'No transcript available.';
      }
    } catch (err) {
      console.error('Error fetching transcript segments:', err);
      transcriptText = 'Error loading transcript.';
    }
  }
  
  /**
   * Fetch file details from the API
   * @param {MouseEvent | string | undefined} fileIdOrEvent - Either a file ID or a click event
   */
  async function fetchFileDetails(fileIdOrEvent = id) {
    // Handle both string ID and click event cases
    const fileId = typeof fileIdOrEvent === 'string' ? fileIdOrEvent : id;
    if (!fileId) {
      errorMessage = 'No file ID provided';
      isLoading = false;
      return;
    }
    
    isLoading = true;
    errorMessage = '';
    
    try {
      console.log(`FileDetail: Fetching file details for ID: ${fileId}`);
      const response = await axiosInstance.get(`/files/${fileId}`);
      
      if (response.data) {
        file = response.data;
        console.log('FileDetail: File details:', file);
        
        // Set video URL - use the simple-video endpoint for efficient streaming
        videoUrl = `${apiBaseUrl}/api/files/${file.id}/simple-video`;
        console.log('FileDetail: Video URL set to:', videoUrl);
        
        // Initialize player (will be done after DOM update via afterUpdate hook)
        videoElementChecked = false;
        
        // Fetch transcript if not included in response
        if (!file.transcript || file.transcript.length === 0) {
          console.log('FileDetail: No transcript data in file, fetching separately');
          fetchTranscriptSegments(file.id);
        }
        
        // Process transcript data if available
        if (file && file.transcript && file.transcript.length > 0) {
          console.log(`FileDetail: File has ${file.transcript.length} transcript segments`);
          
          // Load speakers for this file to associate with transcript segments
          loadSpeakers();
          
          // Create text representation of transcript
          transcriptText = file.transcript.map(seg => `${formatTimestampWithMillis(seg.start_time)} [${seg.speaker_label || 'Speaker'}]: ${seg.text}`).join('\n');
        } else if (file && response.data.transcript_segments && response.data.transcript_segments.length > 0) {
          // Handle case where transcript is in transcript_segments field instead of transcript
          console.log(`FileDetail: File has ${response.data.transcript_segments.length} transcript segments in transcript_segments field`);
          file.transcript = response.data.transcript_segments;
          
          // Load speakers for this file to associate with transcript segments
          loadSpeakers();
          
          // Create text representation of transcript
          transcriptText = file.transcript.map(seg => `${formatTimestampWithMillis(seg.start_time)} [${seg.speaker_label || 'Speaker'}]: ${seg.text}`).join('\n');
        } else if (file) {
          console.warn('FileDetail: No transcript data found');
          // Check if we need to fetch transcript segments separately
          fetchTranscriptSegments(file.id);
          transcriptText = 'Loading transcript...';
        }
        
        // Check if we need to fetch analytics separately
        if (file && (!file.analytics || !file.analytics.overall)) {
          console.log('FileDetail: No analytics data found, fetching separately');
          fetchAnalytics(file.id);
        } else if (file && file.analytics) {
          console.log('FileDetail: Analytics data found:', file.analytics);
        }
        editedTranscript = transcriptText;
        
        console.log('FileDetail: File status:', file.status);
        console.log('FileDetail: Storage path:', file.storage_path || 'none');
        
        if (videoUrl) {
          console.log('FileDetail: S3 direct URL is available for playback:', videoUrl);
          // Reset flag to prompt afterUpdate to try initialization
          videoElementChecked = false;
        }
        
        console.log('FileDetail: Final videoUrl chosen:', videoUrl || 'none');
      }
      if (file.status === 'processing') {
        // If still processing, poll for updates
        // This is a simple polling mechanism; consider WebSockets for real-time updates
        setTimeout(fetchFileDetails, 5000); 
      }

    } catch (err) {
      console.error('Error fetching file details:', err);
      
      // Handle error with structured approach
      const error = err;
      
      if (error && typeof error === 'object') {
        // Use a different variable name to avoid shadowing
        const errorObj = error;
        if (errorObj.response && typeof errorObj.response === 'object') {
          const response = errorObj.response;
          
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
   * Set up the video URL for streaming
   * @param {string} fileId - The ID of the file to stream
   */
  function setupVideoUrl(fileId) {
    // Use the simple-video endpoint which returns the complete video file
    // Use the correct API endpoint for video streaming
    videoUrl = `${apiBaseUrl}/api/files/${fileId}/simple-video`;
    console.log('FileDetail: Using simple-video endpoint for streaming:', videoUrl);
    
    // Ensure URL has proper formatting
    if (videoUrl && !videoUrl.startsWith('/') && !videoUrl.startsWith('http')) {
      videoUrl = '/' + videoUrl;
    }
    console.log('FileDetail: Added leading slash to URL:', videoUrl);
    
    // Reset video element check flag to prompt afterUpdate to try initialization
    videoElementChecked = false;
  }

  /**
   * Initialize the Plyr video player with enhanced streaming capabilities
   */
  function initializePlayer() {
    if (playerInitialized) {
      console.log('FileDetail: Player already initialized, skipping');
      return;
    }
    
    console.log('FileDetail: Initializing enhanced video player with URL:', videoUrl);
    // Make sure we're checking for the video element with a more robust approach
    const videoElement = document.querySelector('#player');
    
    if (!videoElement) {
      console.error('FileDetail: Video element not found in DOM');
      // Log debug information about the DOM structure
      console.log('FileDetail: DOM Structure:', 
        Array.from(document.querySelectorAll('body > *')).map(el => el.tagName).join(', '));
      console.log('FileDetail: Video container exists:', 
        document.querySelector('.video-player-container') !== null);
      
      // Try again after a short delay to allow DOM to fully render
      setTimeout(() => {
        console.log('FileDetail: Retrying player initialization after delay');
        const retryVideoElement = document.querySelector('#player');
        if (retryVideoElement) {
          console.log('FileDetail: Video element found on retry');
          initializePlayer();
        }
      }, 1000);
      return;
    }
    
    // Make sure the video has a valid source before initializing
    if (!videoUrl) {
      console.error('FileDetail: No video URL provided');
      return;
    }

    // Configure video element with preload hint for improved startup performance
    videoElement.preload = 'metadata'; // Fetch metadata but don't download entire video until play
    videoElement.crossOrigin = 'anonymous'; // Enable CORS for subtitle support
    videoElement.playsInline = true; // Better mobile experience
    
    // Set up buffer management for more efficient streaming
    // HTML5 video buffer hints for improved streaming performance
    const setVideoBufferPreferences = () => {
      try {
        // @ts-ignore - Media Source Extensions API may not be fully typed
        if ('bufferingGoal' in HTMLMediaElement.prototype) {
          // @ts-ignore - Set buffer goal to improve streaming performance
          videoElement.bufferingGoal = 15; // Buffer 15 seconds ahead
        }
        
        // Set buffering policy using Media Source Extensions if available
        if (window.MediaSource) {
          // Configure video to aggressively preload on good connections
          // and conservatively on slower connections
          if (navigator.connection) {
            // @ts-ignore - Connection API may not be fully typed
            const connection = navigator.connection;
            if (connection.downlink > 5) { // >5Mbps connection
              videoElement.preload = 'auto';
            }
          }
        }
      } catch (e) {
        console.warn('Advanced buffer settings not supported by browser:', e);
      }
    };
    
    setVideoBufferPreferences();
    
    // Set source to ensure it's correctly loaded
    // Check if source element exists and create if it doesn't
    let sourceElement = videoElement.querySelector('source');
    if (!sourceElement) {
      console.log('FileDetail: Creating new source element');
      sourceElement = document.createElement('source');
      sourceElement.type = 'video/mp4';
      videoElement.appendChild(sourceElement);
    }
    
    // Update source with current URL and add cache-busting parameter if needed
    if (sourceElement) {
      // Add a cache parameter only if experiencing caching issues
      const hasQuery = videoUrl.includes('?');
      const cacheBuster = `${hasQuery ? '&' : '?'}_t=${Date.now()}`;
      // Only add cache buster during development or if experiencing issues
      const finalUrl = import.meta.env.DEV ? `${videoUrl}${cacheBuster}` : videoUrl;
      
      sourceElement.src = finalUrl;
      videoElement.load(); // Force reload with new source
    }
    
    // Clear previous Plyr instance if any
    if (player) {
      console.log('FileDetail: Destroying previous player instance');
      try {
        player.destroy();
      } catch (e) {
        console.error('Error destroying player:', e);
      }
    }
    
    try {
      console.log('FileDetail: Creating enhanced Plyr player instance');
      
      if (!videoElement) {
        console.error('FileDetail: Video element not found');
        return;
      }

      // Create new Plyr instance with enhanced options
      player = new Plyr(videoElement, {
        controls: [
          'play-large', 'play', 'progress', 'current-time', 'mute', 
          'volume', 'captions', 'settings', 'pip', 'airplay', 'fullscreen'
        ],
        seekTime: 5,
        keyboard: { focused: true, global: false },
        speed: { selected: 1, options: [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2] },
        quality: { default: 'auto', options: ['auto'] },
        tooltips: { controls: true, seek: true },
        previewThumbnails: false, // Could be enabled with sprite generation
        storage: { enabled: true, key: 'opentranscribe-player' }
      });

      // Set up comprehensive event listeners for player metrics and experience
      player.on('ready', () => {
        console.log('FileDetail: Player ready');
        playerInitialized = true;
      });

      player.on('timeupdate', () => {
        if (player && typeof player.currentTime === 'number') {
          currentTime = player.currentTime;
          // Highlight the current segment based on playback time
          highlightCurrentSegment(currentTime);
        }
      });

      player.on('loadedmetadata', () => {
        if (player && typeof player.duration === 'number') {
          duration = player.duration;
          console.log(`FileDetail: Video duration loaded: ${duration}s`);
          // Update file object with duration if not already set
          if (file && (!file.duration || file.duration === 0) && duration > 0) {
            file.duration = duration;
            reactiveFile.set(file);
          }
        }
      });
      
      // Improved error tracking with detailed diagnostics
      player.on('error', (event) => {
        console.error('FileDetail: Player error event:', event);
        const videoError = videoElement.error;
        let errorDetail = 'Unknown error';
        
        if (videoError) {
          const errorCodes = {
            1: 'MEDIA_ERR_ABORTED: The fetching process was aborted by the user',
            2: 'MEDIA_ERR_NETWORK: A network error occurred while fetching the media',
            3: 'MEDIA_ERR_DECODE: The media cannot be decoded (likely corrupt or unsupported format)',
            4: 'MEDIA_ERR_SRC_NOT_SUPPORTED: The media format or MIME type is not supported'
          };
          errorDetail = errorCodes[videoError.code] || `Error code ${videoError.code}`;
          playerErrorDetails = errorDetail;
          console.error(`FileDetail: Video error: ${errorDetail}`, videoError);
        }
        
        errorMessage = `Error playing video: ${errorDetail}. Try refreshing the page or downloading the file.`;
      });

      // Track loading state for better user feedback
      player.on('stalled', () => {
        console.warn('FileDetail: Video playback has stalled');
        isPlayerBuffering = true;
      });

      player.on('playing', () => {
        isPlayerBuffering = false;
        errorMessage = ''; // Clear any error messages when playback succeeds
      });
      
      // Track player settings
      player.on('qualitychange', (event) => {
        playerQuality = event.detail.quality;
      });
      
      player.on('ratechange', () => {
        playbackSpeed = player.speed || 1;
      });
      
      player.on('enterfullscreen', () => {
        isFullscreen = true;
      });
      
      player.on('exitfullscreen', () => {
        isFullscreen = false;
      });

      playerInitialized = true;
      console.log('FileDetail: Enhanced player initialized successfully');
      
      // Set up additional native video element event listeners for better metrics
      if (videoElement) {
        // Listen for more granular loading events
        videoElement.addEventListener('waiting', () => {
          isPlayerBuffering = true;
          console.log('FileDetail: Video is waiting for more data');
        });
        
        videoElement.addEventListener('canplaythrough', () => {
          console.log('FileDetail: Video CAN PLAY THROUGH - enough data is loaded to play to the end');
          isPlayerBuffering = false;
        });
        
        // Monitor network and buffer state for diagnostics
        videoElement.addEventListener('progress', () => {
          // Ensure videoElement is an HTMLVideoElement with buffered property
          if (videoElement && 'buffered' in videoElement && videoElement.buffered && videoElement.buffered.length) {
            const bufferedEnd = videoElement.buffered.end(0);
            const bufferedPercent = (bufferedEnd / videoElement.duration) * 100;
            loadProgress = bufferedPercent;
            
            // Log buffer status periodically (every 20%)
            if (Math.floor(bufferedPercent) % 20 === 0) {
              console.log(`FileDetail: Buffered ${Math.floor(bufferedPercent)}% (${bufferedEnd.toFixed(1)}s of ${videoElement.duration.toFixed(1)}s)`);
            }
          }
        });
        
        // Detailed error handling for native video element
        videoElement.addEventListener('error', (e) => {
          console.error('FileDetail: Native video error event:', e);
          const videoError = videoElement.error;
          
          if (videoError) {
            playerErrorDetails = `Error code ${videoError.code}: ${videoError.message || 'No details available'}`;
            console.error('Video error details:', playerErrorDetails);
          }
          
          // Try to recover by reloading source if it's a network error
          if (videoError && videoError.code === 2 && sourceElement) { // MEDIA_ERR_NETWORK
            console.log('FileDetail: Attempting to recover from network error by reloading source');
            setTimeout(() => {
              sourceElement.src = videoUrl;
              videoElement.load();
            }, 3000); // Wait 3 seconds before retry
          }
        });
      }
    } catch (error) {
      console.error('FileDetail: Error initializing player:', error);
      
      // Safely get error message from error object
      const errorMsg = (error && typeof error === 'object' && 'message' in error) 
        ? String(error.message) 
        : 'Unknown error';
      errorMessage = 'Could not initialize video player: ' + errorMsg;
      playerInitialized = false;
    }
  }

  async function saveTranscript() {
    if (!file || !file.id) return;
    savingTranscript = true;
    transcriptError = '';
    try {
      // Parse transcript with timestamp and speaker format: "MM:SS [Speaker]: Text"
      const updatedTranscriptSegments = [];
      const lines = editedTranscript.split('\n').filter(line => line.trim() !== '');
      
      for (let index = 0; index < lines.length; index++) {
        const line = lines[index];
        // Try to match timestamp and speaker pattern: "MM:SS [Speaker]: Text"
        const timestampMatch = line.match(/^(\d+:\d+)\s+\[([^\]]+)\]:\s*(.*)$/);
        
        if (timestampMatch && timestampMatch.length === 4) {
          // We have a timestamp, speaker, and text
          const timestampStr = timestampMatch[1];
          const speaker_label = timestampMatch[2].trim();
          const text = timestampMatch[3].trim();
          
          // Convert MM:SS to seconds
          const [minutes, seconds] = timestampStr.split(':').map(Number);
          const start_time = minutes * 60 + seconds;
          
          // Try to find the original segment to preserve end_time
          const existingSegment = file?.transcript?.find(seg => 
            Math.abs(seg.start_time - start_time) < 2 && // Within 2 seconds
            (seg.speaker_label === speaker_label || seg.speaker?.name === speaker_label || seg.speaker?.display_name === speaker_label)
          );
          
          updatedTranscriptSegments.push({
            start_time: start_time,
            end_time: existingSegment ? existingSegment.end_time : (index < lines.length - 1 ? start_time + 5 : start_time + 10),
            text: text,
            speaker_label: speaker_label,
          });
        } else {
          // Fallback for lines without proper formatting
          const parts = line.match(/^\[([^\]]+)\]:\s*(.*)$/);
          let speaker_label = `Speaker ${index % 2 + 1}`; // Default if no match
          let text = line;
          
          if (parts && parts.length === 3) {
            speaker_label = parts[1].trim();
            text = parts[2].trim();
          }
          
          // Find original timing if possible, or assign new ones
          const existingSegment = file?.transcript?.[index];
          
          updatedTranscriptSegments.push({
            start_time: existingSegment ? existingSegment.start_time : index * 5,
            end_time: existingSegment ? existingSegment.end_time : (index + 1) * 5,
            text: text,
            speaker_label: speaker_label,
          });
        }
      }
      
      // Sort segments by start time
      updatedTranscriptSegments.sort((a, b) => a.start_time - b.start_time);

      // The API expects transcript segments as a list, not as an object with a transcript property
      await axiosInstance.put(`/files/${file.id}/transcript`, updatedTranscriptSegments);
      isEditingTranscript = false;
      transcriptText = editedTranscript; // Update the displayed transcript
      if (file) file.transcript = updatedTranscriptSegments; // Update local file object
    } catch (err) {
      console.error('Error saving transcript:', err);
      // Safely get error detail from error response
      let errorDetail = 'An unknown error occurred';
      
      if (err && typeof err === 'object') {
        // Handle Axios error response
        const axiosError = err;
        
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
        // Use proper speaker display names when available
        editedTranscript = file.transcript.map(segment => {
          // Get the proper speaker name, prioritizing display_name over original name
          const speakerName = segment.speaker?.display_name || 
                             segment.speaker?.name || 
                             segment.speaker_label || 
                             'Unknown';
          
          return `${formatSimpleTimestamp(segment.start_time)} [${speakerName}]: ${segment.text}`;
        }).join('\n');
        isEditingTranscript = true;
      } else {
        errorMessage = 'No transcript available to edit';
      }
    }
  }
  
  /**
   * Start editing a specific transcript segment
   * @param {Object} segment - The transcript segment to edit
   */
  function editSegment(segment) {
    if (!segment || !segment.id) {
      console.error('Cannot edit segment without a valid ID');
      return;
    }
    // Use the segment ID from the database
    editingSegmentId = segment.id;
    editingSegmentText = segment.text || '';
    console.log('Editing segment with ID:', editingSegmentId);
  }
  
  function cancelEditSegment() {
    editingSegmentId = null;
    editingSegmentText = '';
  }
  
  /**
   * Save changes to a specific transcript segment
   * @param {Object} segment - The transcript segment being edited
   */
  async function saveSegment(segment) {
    if (!file || !file.id) return;
    savingTranscript = true;
    transcriptError = '';

    if (!segment || !segment.id) {
      console.error('Cannot save segment without a valid ID');
      transcriptError = 'Error: Cannot save segment without a valid ID';
      savingTranscript = false;
      return;
    }

    try {
      // Create a segment update object with only the fields we want to update
      // @ts-ignore - Ignoring TypeScript errors as per user preference
      const segmentUpdate = {
        id: segment.id,
        text: editingSegmentText
      };
      
      // Add timing and speaker information if available
      if (segment.start_time !== undefined) {
        // @ts-ignore
        segmentUpdate.start_time = segment.start_time;
      }
      
      if (segment.end_time !== undefined) {
        // @ts-ignore
        segmentUpdate.end_time = segment.end_time;
      }
      
      if (segment.speaker_id !== undefined) {
        // @ts-ignore
        segmentUpdate.speaker_id = segment.speaker_id || null;
      }
      
      console.log('Saving segment update:', segmentUpdate, 'Original segment:', segment);
      
      // Send the updated segment to the API as an array
      console.log('Sending segment update to API:', [segmentUpdate]);
      // The API expects a list of segments
      const response = await axiosInstance.put(`/api/files/${file.id}/transcript`, [segmentUpdate]);
      
      // After successful update, refresh the transcript segments to ensure we have the latest data
      if (response.status === 200) {
        console.log('Segment updated successfully, refreshing transcript data');
        // Fetch the updated transcript data
        if (file && file.id) {
          await fetchTranscriptSegments(file.id);
        }
      }
      
      // Update the local state if file and transcript exist
      if (file && file.transcript) {
        // @ts-ignore - Ignoring TypeScript errors as per user preference
        const updatedSegment = file.transcript.find(s => s.id === segment.id);
        if (updatedSegment) {
          updatedSegment.text = editingSegmentText;
        } else {
          console.warn('Updated segment not found in local state after saving');
        }
      }
      
      // Reset editing state
      editingSegmentId = null;
      editingSegmentText = '';
    } catch (err) {
      console.error('Error saving segment:', err);
      let errorDetail = 'An unknown error occurred';
      
      if (err && typeof err === 'object') {
        // @ts-ignore - Ignoring TypeScript errors as per user preference
        const axiosError = err;
        
        // @ts-ignore - Ignoring TypeScript errors as per user preference
        if (axiosError.response) {
          // @ts-ignore - Ignoring TypeScript errors as per user preference
          const responseData = axiosError.response.data;
          if (responseData && typeof responseData === 'object' && 'detail' in responseData) {
            errorDetail = String(responseData.detail);
          // @ts-ignore - Ignoring TypeScript errors as per user preference
          } else if (axiosError.response.statusText) {
            // @ts-ignore - Ignoring TypeScript errors as per user preference
            errorDetail = `${axiosError.response.status}: ${axiosError.response.statusText}`;
          } else {
            // @ts-ignore - Ignoring TypeScript errors as per user preference
            errorDetail = `Server responded with status ${axiosError.response.status}`;
          }
        // @ts-ignore - Ignoring TypeScript errors as per user preference
        } else if (axiosError.request) {
          errorDetail = 'No response from server';
        } else {
          // @ts-ignore - Ignoring TypeScript errors as per user preference
          errorDetail = axiosError.message || 'Error setting up request';
        }
      } else if (err) {
        errorDetail = String(err);
      }
      
      transcriptError = `Failed to save segment. ${errorDetail}`;
    } finally {
      savingTranscript = false;
    }
  }
  
  /**
   * Export transcript to a downloadable file in various formats
   * @param {string} format - The format to export (txt, json, csv, srt, vtt)
   */
  function exportTranscript(format = 'txt') {
    if (!file || !file.transcript || file.transcript.length === 0) {
      errorMessage = 'No transcript available to export';
      return;
    }
    
    try {
      let content = '';
      let mimeType = 'text/plain';
      let extension = 'txt';
      
      // Generate content based on selected format
      switch (format) {
        case 'json':
          // Export as JSON with speaker and timing information
          // Create a deep copy with proper speaker names
          const jsonData = file.transcript.map(segment => {
            const speakerName = segment.speaker?.display_name || 
                               segment.speaker?.name || 
                               segment.speaker_label || 
                               'Unknown';
            return {
              ...segment,
              speaker_display_name: speakerName
            };
          });
          content = JSON.stringify(jsonData, null, 2);
          mimeType = 'application/json';
          extension = 'json';
          break;
          
        case 'csv':
          // Export as CSV with headers
          content = 'Start Time,End Time,Speaker,Text\n';
          content += file.transcript.map(segment => {
            // Get proper speaker name
            const speakerName = segment.speaker?.display_name || 
                               segment.speaker?.name || 
                               segment.speaker_label || 
                               'Unknown';
            // Escape quotes in text for CSV
            const escapedText = segment.text.replace(/"/g, '""');
            return `${segment.start_time},${segment.end_time},"${speakerName}","${escapedText}"`;
          }).join('\n');
          mimeType = 'text/csv';
          extension = 'csv';
          break;
          
        case 'srt':
          // Export as SubRip subtitle format
          content = file.transcript.map((segment, index) => {
            const speakerName = segment.speaker?.display_name || 
                               segment.speaker?.name || 
                               segment.speaker_label || 
                               'Unknown';
            const startTime = formatSrtTimestamp(segment.start_time);
            const endTime = formatSrtTimestamp(segment.end_time);
            return `${index + 1}\n${startTime} --> ${endTime}\n${speakerName}: ${segment.text}\n`;
          }).join('\n');
          mimeType = 'text/plain';
          extension = 'srt';
          break;
          
        case 'vtt':
          // Export as WebVTT subtitle format
          content = 'WEBVTT\n\n';
          content += file.transcript.map((segment, index) => {
            const speakerName = segment.speaker?.display_name || 
                               segment.speaker?.name || 
                               segment.speaker_label || 
                               'Unknown';
            const startTime = formatVttTimestamp(segment.start_time);
            const endTime = formatVttTimestamp(segment.end_time);
            return `${index + 1}\n${startTime} --> ${endTime}\n<v ${speakerName}>${segment.text}\n`;
          }).join('\n');
          mimeType = 'text/vtt';
          extension = 'vtt';
          break;
          
        default: // txt
          // Format transcript for plain text export
          content = file.transcript.map(segment => {
            const speakerName = segment.speaker?.display_name || 
                               segment.speaker?.name || 
                               segment.speaker_label || 
                               'Unknown';
            return `${formatSimpleTimestamp(segment.start_time)} - ${formatSimpleTimestamp(segment.end_time)}\n` +
                   `[${speakerName}]: ${segment.text}\n`;
          }).join('\n');
          mimeType = 'text/plain';
          extension = 'txt';
      }
      
      // Create file and trigger download
      const blob = new Blob([content], { type: mimeType });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${file.filename.replace(/\.[^\.]+$/, '')}_transcript.${extension}`;
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
   * Format timestamp for SRT format (00:00:00,000)
   * @param {number} seconds - Time in seconds
   * @returns {string} - Formatted timestamp
   */
  function formatSrtTimestamp(seconds) {
    const totalSeconds = Math.floor(seconds);
    const hours = Math.floor(totalSeconds / 3600).toString().padStart(2, '0');
    const minutes = Math.floor((totalSeconds % 3600) / 60).toString().padStart(2, '0');
    const secs = (totalSeconds % 60).toString().padStart(2, '0');
    const millis = Math.floor((seconds - Math.floor(seconds)) * 1000).toString().padStart(3, '0');
    return `${hours}:${minutes}:${secs},${millis}`;
  }
  
  /**
   * Format timestamp for VTT format (00:00:00.000)
   * @param {number} seconds - Time in seconds
   * @returns {string} - Formatted timestamp
   */
  function formatVttTimestamp(seconds) {
    const totalSeconds = Math.floor(seconds);
    const hours = Math.floor(totalSeconds / 3600).toString().padStart(2, '0');
    const minutes = Math.floor((totalSeconds % 3600) / 60).toString().padStart(2, '0');
    const secs = (totalSeconds % 60).toString().padStart(2, '0');
    const millis = Math.floor((seconds - Math.floor(seconds)) * 1000).toString().padStart(3, '0');
    return `${hours}:${minutes}:${secs}.${millis}`;
  }
  
  /**
   * Format seconds to MM:SS or HH:MM:SS format
   * @param {number} seconds - Time in seconds to format
   * @returns {string} - Formatted time string
   */
  function formatSimpleTimestamp(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    
    if (hours > 0) {
      return `${hours}:${minutes.toString().padStart(2, '0')}:${remainingSeconds.toString().padStart(2, '0')}`;
    } else {
      return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
    }
  }

  /** 
   * @param {Event} event 
   */
  function handleTranscriptInput(event) {
    // Cast target to HTMLTextAreaElement to access value property
    const target = event.target;
    editedTranscript = target?.value;
  }

  /**
   * Handles tags updated event from TagsEditor.
   * @param {CustomEvent<{tags: any[]}>} event - The event containing updated tags.
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
  
  /**
   * Load speakers for the current file
   */
  async function loadSpeakers() {
    if (!file || !file.id) {
      console.error('Cannot load speakers: File ID is missing');
      return;
    }
    
    try {
      loadingSpeakers = true;
      // Get speakers for this specific file by adding a file_id query parameter
      const response = await axiosInstance.get(`/api/speakers/?file_id=${file.id}`);
      speakerList = response.data;
      console.log('FileDetail: Speakers loaded:', speakerList);
      
      // Process transcript with speaker information
      updateTranscriptWithSpeakers();
      
      loadingSpeakers = false;
    } catch (error) {
      console.error('Error loading speakers:', error);
      loadingSpeakers = false;
    }
  }
  
  /**
   * Handle speaker updates from the SpeakerEditor component
   */
  function handleSpeakersUpdated(event) {
    console.log('FileDetail: Speakers updated:', event.detail.speakers);
    speakerList = event.detail.speakers;
    
    // Update transcript display with new speaker names
    updateTranscriptWithSpeakers();
    
    // Re-fetch file details to get updated speaker information
    fetchFileDetails();
  }
  
  /**
   * Save updated speaker names to the server
   */
  async function saveSpeakerNames() {
    if (!speakerList || speakerList.length === 0 || !file || !file.id) {
      speakerError = 'No speakers to save';
      return;
    }
    
    savingSpeakers = true;
    speakerError = '';
    
    try {
      console.log('FileDetail: Saving speaker names:', speakerList);
      
      // Format speakers for API
      const speakersToUpdate = speakerList.map(speaker => ({
        id: speaker.id,
        display_name: speaker.display_name || speaker.name
      }));
      
      // Send update to server - use the correct endpoint format with speaker IDs
      // Process each speaker individually to ensure correct API format
      const updatedSpeakers = [];
      
      for (const speaker of speakersToUpdate) {
        if (!speaker.id) continue;
        
        try {
          // Use numeric ID in the URL path
          const speakerResponse = await axiosInstance.put(`/speakers/${speaker.id}`, {
            display_name: speaker.display_name
          });
          
          if (speakerResponse.data) {
            updatedSpeakers.push(speakerResponse.data);
          }
        } catch (err) {
          console.error(`Failed to update speaker ${speaker.id}:`, err);
        }
      }
      
      // Use the updated speakers or the original response
      const response = { data: updatedSpeakers.length > 0 ? updatedSpeakers : speakerList };
      
      console.log('FileDetail: Speaker names saved successfully:', response.data);
      
      // Update local speaker list
      if (response.data && Array.isArray(response.data)) {
        speakerList = response.data;
      }
      
      // Update transcript display with new speaker names
      updateTranscriptWithSpeakers();
      
      // Hide speaker editor
      isEditingSpeakers = false;
    } catch (error) {
      console.error('Error saving speaker names:', error);
      speakerError = 'Failed to save speaker names. Please try again.';
    } finally {
      savingSpeakers = false;
    }
  }
  
  /**
   * Update transcript segments with speaker information
   */
  function updateTranscriptWithSpeakers() {
    if (!file || !file.transcript || !file.transcript.length || !speakerList.length) {
      return;
    }
    
    const updatedTranscript = [...file.transcript];
    for (let segment of updatedTranscript) {
      // Try to find a matching speaker by ID, UUID, or label
      const matchingSpeaker = speakerList.find(s => {
        return s.id === segment.speaker_id || 
               (s.uuid && s.uuid === segment.speaker_uuid) ||
               (segment.speaker_label && s.name === segment.speaker_label);
      });
      
      if (matchingSpeaker) {
        // Add speaker info to the segment for display purposes
        segment.speaker = {
          id: matchingSpeaker.id,
          name: matchingSpeaker.name,
          display_name: matchingSpeaker.display_name || matchingSpeaker.name,
          uuid: matchingSpeaker.uuid
        };
      } else if (segment.speaker_label) {
        // If no matching speaker found but we have a label, create a minimal speaker object
        // Generate a temporary ID based on the label to satisfy the Speaker type
        segment.speaker = {
          id: `temp_${segment.speaker_label.replace(/\s+/g, '_').toLowerCase()}`,
          name: segment.speaker_label,
          display_name: segment.speaker_label
        };
      }
    }
    
    // Update the file with updated speaker information
    file.transcript = updatedTranscript;
    console.log('Transcript updated with speaker information');
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
  
  // Poll for file processing status updates
  function pollForFileStatus() {
    if (!file || !file.id || file.status !== 'processing') return;
    
    console.log('FileDetail: Polling for file status updates...');
    
    // Use a closure to maintain state across polling intervals
    const pollInterval = 5000; // 5 seconds between polls
    let isPolling = false;
    let currentFileId = file.id; // Cache the file ID to use in async callbacks
    
    const poll = async () => {
      // Prevent concurrent polling or if no longer relevant
      if (isPolling || !file) return;
      isPolling = true;
      
      try {
        // Always use the cached file ID to prevent null reference errors
        console.log(`FileDetail: Polling for updates for file ID: ${currentFileId}`);
        const response = await axiosInstance.get(`/files/${currentFileId}`);
        const updatedFile = response.data;
        
        // Update local file state with new data if we still have a valid file reference
        if (updatedFile) {
          // Update file state safely
          file = updatedFile;
          reactiveFile.set(file);
          
          // Safe access to properties with null checks
          const fileStatus = file?.status || 'unknown';
          const fileProgress = file?.progress || 0;
          console.log(`FileDetail: File status update - ${fileStatus}, progress: ${fileProgress}%`);
          
          // If processing is complete, try to initialize the player
          if (file && file.status === 'completed' && file.id) {
            console.log('FileDetail: Processing completed, updating video URL');
            // Update video URL and initialize player
            videoUrl = `${apiBaseUrl}/api/files/${file.id}/simple-video`;
            videoElementChecked = false;
            initializePlayer();
          }
        }
      } catch (err) {
        console.error('FileDetail: Error polling for file status:', err);
      } finally {
        isPolling = false;
        
        // Continue polling if still processing and file reference is valid
        if (file && file.status === 'processing') {
          setTimeout(poll, pollInterval);
        }
      }
    };
    
    // Start the polling process
    setTimeout(poll, 1000); // Start first poll after 1 second
  }

  // Reactive statement to re-initialize player if videoUrl changes after initial mount
  // and player wasn't initialized (e.g., fetched file details did not have URL initially)
  $: if (videoUrl && !player && !isLoading) {
    console.log('FileDetail: Video URL available but no player, initializing player');
    initializePlayer();
  }

  // Start polling for file status updates if the file is processing
  $: if (file && file.status === 'processing') {
    console.log('FileDetail: File is processing, starting status polling');
    pollForFileStatus();
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
      <button on:click={(e) => fetchFileDetails()}>Try Again</button>
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
        <div class="video-player-container" class:loading={isPlayerBuffering}>
          {#if videoUrl}
            <!-- Enhanced video player with improved streaming capabilities -->
            <video id="player" playsinline controls>
              <source src={videoUrl} type="video/mp4" />
              <!-- Captions track using transcript data -->
              {#if file && file.transcript && file.transcript.length > 0}
                <!-- Generate captions from transcript in memory -->
                
              <!-- Show buffering indicator when video is loading -->
              {#if isPlayerBuffering}
                <div class="buffer-indicator">
                  <div class="spinner"></div>
                  <div class="buffer-text">Loading video... {Math.round(loadProgress)}%</div>
                </div>
              {/if}
                <track kind="captions" label="English" default
                  src={`data:text/vtt;base64,${btoa('WEBVTT\n\n' + file.transcript.map(segment => 
                    `${formatTimestampWithMillis(segment.start_time).replace(',', '.')} --> ${formatTimestampWithMillis(segment.end_time).replace(',', '.')}\n${segment.text}\n\n`
                  ).join(''))}`} />
              {:else}
                <!-- Empty track to satisfy accessibility requirements -->
                <track kind="captions" label="English" src="data:text/vtt;base64,V0VCVlRUCgo=" />
              {/if}
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
            <!-- <div class="section-header">
              <h2>Comments</h2>
              <div class="spacer"></div>
            </div> -->
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
              <button class="cancel-button" on:click={() => isEditingTranscript = false}>Cancel</button>
            </div>
            {#if transcriptError}
              <p class="error-message small">{transcriptError}</p>
            {/if}
          {:else}
            <div class="transcript-display">
              {#each file.transcript as segment, i}
                <div 
                  class="transcript-segment" 
                  data-segment-id="{segment.id || `${segment.start_time}-${segment.end_time}`}"
                >
                  {#if editingSegmentId === segment.id}
                    <div class="segment-edit-container">
                      <div class="segment-time">{formatSimpleTimestamp(segment.start_time)}</div>
                      <div class="segment-speaker">{segment.speaker?.display_name || segment.speaker?.name || segment.speaker_label || 'Unknown'}</div>
                      <div class="segment-edit-input">
                        <textarea bind:value={editingSegmentText} rows="3" class="segment-textarea"></textarea>
                        <div class="segment-edit-actions">
                          <button class="save-button" on:click={() => saveSegment(segment)} disabled={savingTranscript}>
                            {savingTranscript ? 'Saving...' : 'Save'}
                          </button>
                          <button class="cancel-button" on:click={cancelEditSegment}>Cancel</button>
                        </div>
                        {#if transcriptError}
                          <p class="error-message small">{transcriptError}</p>
                        {/if}
                      </div>
                    </div>
                  {:else}
                    <div class="segment-row">
                      <button 
                        class="segment-content" 
                        on:click={() => handleSegmentClick(segment.start_time)}
                        on:keydown={(e) => e.key === 'Enter' && handleSegmentClick(segment.start_time)}
                        title="Jump to this segment"
                      >
                        <div class="segment-time">{formatSimpleTimestamp(segment.start_time)}</div>
                        <div class="segment-speaker">{segment.speaker?.display_name || segment.speaker?.name || segment.speaker_label || 'Unknown'}</div>
                        <div class="segment-text">{segment.text}</div>
                      </button>
                      <button 
                        class="edit-button" 
                        on:click|stopPropagation={() => editSegment(segment)} 
                        title="Edit segment"
                      >
                        Edit
                      </button>
                    </div>
                  {/if}
                </div>
              {/each}
            </div>
            
            <div class="transcript-actions">
              
              <div class="export-dropdown">
                <button class="export-transcript-button">
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                    <polyline points="7 10 12 15 17 10"></polyline>
                    <line x1="12" y1="15" x2="12" y2="3"></line>
                  </svg>
                  Export
                </button>
                <div class="export-dropdown-content">
                  <button on:click={() => exportTranscript('txt')}>Plain Text (.txt)</button>
                  <button on:click={() => exportTranscript('json')}>JSON Format (.json)</button>
                  <button on:click={() => exportTranscript('csv')}>CSV Format (.csv)</button>
                  <button on:click={() => exportTranscript('srt')}>SubRip Subtitles (.srt)</button>
                  <button on:click={() => exportTranscript('vtt')}>WebVTT Subtitles (.vtt)</button>
                </div>
              </div>
              
              <button class="edit-speakers-button" on:click={() => isEditingSpeakers = !isEditingSpeakers}>
                {isEditingSpeakers ? 'Hide Speaker Editor' : 'Edit Speakers'}
              </button>
            </div>
            
            {#if isEditingSpeakers}
              <div class="speaker-editor-container" transition:slide={{ duration: 200 }}>
                <h4>Edit Speaker Names</h4>
                {#if speakerList && speakerList.length > 0}
                  <div class="speaker-list">
                    {#each speakerList as speaker}
                      <div class="speaker-item">
                        <span class="speaker-original">{speaker.name}</span>
                        <input 
                          type="text" 
                          bind:value={speaker.display_name} 
                          placeholder="Enter display name"
                        />
                      </div>
                    {/each}
                    <button class="save-speakers-button" on:click={saveSpeakerNames}>Save Speaker Names</button>
                  </div>
                {:else}
                  <p>No speakers found in this transcript.</p>
                {/if}
              </div>
            {/if}
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
  
  .segment-content {
    display: flex;
    flex: 1;
    cursor: pointer;
    background: none;
    border: none;
    padding: 0;
    margin: 0;
    text-align: left;
    font-family: inherit;
    font-size: inherit;
    color: inherit;
    width: 100%;
  }
  
  .segment-actions {
    display: flex;
    position: absolute;
    right: 10px;
    top: 10px;
  }
  
  .tags-header, .analytics-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem 1.5rem;
    background-color: rgba(59, 130, 246, 0.05);
    border: none;
    border-radius: 8px;
    width: 100%;
    text-align: left;
    cursor: pointer;
    transition: all 0.2s ease;
    margin-bottom: 0.5rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  }
  
  .tags-header:hover, .analytics-header:hover {
    background-color: rgba(59, 130, 246, 0.1);
    transform: translateY(-1px);
    box-shadow: 0 2px 5px rgba(0, 0, 0, 0.08);
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
    min-height: 24px;
  }
  
  .tag-chip, .analytics-chip {
    background-color: rgba(59, 130, 246, 0.15);
    color: var(--primary-color);
    padding: 0.35rem 0.75rem;
    border-radius: 1rem;
    font-size: 0.85rem;
    font-weight: 500;
    display: inline-flex;
    align-items: center;
    border: 1px solid rgba(59, 130, 246, 0.3);
    white-space: nowrap;
    max-width: 150px;
    overflow: hidden;
    text-overflow: ellipsis;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
    transition: all 0.2s ease;
  }
  
  .tag-chip:hover, .analytics-chip:hover {
    background-color: rgba(59, 130, 246, 0.2);
    transform: translateY(-1px);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
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
  
  .transcript-segment {
    margin-bottom: 1rem;
    padding: 0.75rem 1rem;
    border-radius: 12px;
    background-color: var(--surface-color, #ffffff);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
    transition: all 0.2s ease;
    position: relative;
  }
  
  .transcript-segment:hover {
    background-color: var(--hover-color, #f0f7ff);
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.08);
    transform: translateY(-2px);
  }
  
  .transcript-segment.active-segment {
    background-color: var(--primary-color-light, #e6f0ff);
    border-left: 3px solid var(--primary-color);
    box-shadow: 0 4px 10px rgba(59, 130, 246, 0.15);
  }
  
  .segment-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    gap: 0.5rem;
  }
  
  .segment-time {
    min-width: 80px;
    color: var(--text-color-light, #666);
    font-size: 0.85rem;
    padding-right: 0.5rem;
  }
  
  .segment-speaker {
    min-width: 100px;
    font-weight: 600;
    color: var(--primary-color);
    padding-right: 1rem;
  }
  
  .segment-text {
    flex: 1;
    line-height: 1.4;
  }
  
  .segment-content {
    display: flex;
    flex: 1;
    background: none;
    border: none;
    text-align: left;
    cursor: pointer;
    padding: 0;
    font-size: inherit;
    font-family: inherit;
    color: inherit;
  }
  
  .edit-button {
    background-color: var(--primary-color);
    color: white;
    border: none;
    padding: 0.35rem 0.75rem;
    border-radius: 4px;
    font-size: 0.85rem;
    font-weight: 500;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 0.25rem;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    transition: all 0.2s ease;
    margin-left: 0.5rem;
    min-width: 60px;
    justify-content: center;
    position: relative;
    z-index: 2;
  }
  
  .edit-button:hover {
    background-color: var(--primary-color-dark, #2563eb);
    transform: translateY(-1px);
    box-shadow: 0 3px 6px rgba(0, 0, 0, 0.15);
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
    padding: 1rem;
    border: 1px solid var(--border-color);
    border-radius: calc(var(--border-radius) * 1.5);
    font-family: var(--font-family-mono);
    font-size: 0.9rem;
    line-height: 1.6;
    background-color: var(--background-code);
    color: var(--text-color);
    min-height: 200px;
    resize: vertical;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
  }

  /* Debug styles removed as they're no longer used */

  .edit-actions {
    margin-top: 1rem;
    display: flex;
    gap: 0.5rem;
  }
  .edit-actions button {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    background-color: #3b82f6;
    color: white;
    padding: 0.6rem 1.2rem;
    border-radius: 10px;
    text-decoration: none;
    font-weight: 500;
    font-size: 0.95rem;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
    border: none;
    cursor: pointer;
  }
  
  .edit-actions button:hover {
    background-color: #2563eb;
    color: white;
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
    transform: translateY(-1px);
  }
  
  .edit-actions button:active {
    transform: translateY(0);
  }
  
  .edit-actions button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  
  .edit-actions .cancel-button {
    background-color: #f3f4f6;
    color: #374151;
    border: 1px solid #e5e7eb;
  }
  
  .edit-actions .cancel-button:hover {
    background-color: #e5e7eb;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }
  
  .transcript-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-top: 1rem;
  }
  
  .edit-transcript-button,
  .export-transcript-button,
  .edit-speakers-button,
  .save-transcript-button,
  .save-speakers-button {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    background-color: #3b82f6; /* Use explicit color instead of variable */
    color: white;
    padding: 0.6rem 1.2rem;
    border-radius: 10px;
    text-decoration: none;
    font-weight: 500;
    font-size: 0.95rem;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
    border: none;
    cursor: pointer;
  }
  
  .edit-transcript-button:hover,
  .export-transcript-button:hover,
  .edit-speakers-button:hover,
  .save-transcript-button:hover,
  .save-speakers-button:hover {
    background-color: #2563eb; /* Darker blue on hover */
    color: white;
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
    transform: translateY(-1px);
  }
  
  .edit-transcript-button:active,
  .export-transcript-button:active,
  .edit-speakers-button:active,
  .save-transcript-button:active,
  .save-speakers-button:active {
    transform: translateY(0);
  }
  
  /* Export dropdown styles */
  .export-dropdown {
    position: relative;
    display: inline-block;
  }
  
  .export-dropdown-content {
    display: none;
    position: absolute;
    background-color: var(--surface-color);
    min-width: 200px;
    box-shadow: 0px 8px 16px 0px rgba(0,0,0,0.2);
    z-index: 1;
    border-radius: var(--border-radius);
    border: 1px solid var(--border-color);
  }
  
  .export-dropdown-content button {
    color: var(--text-color);
    padding: 12px 16px;
    text-decoration: none;
    display: block;
    background: none;
    border: none;
    text-align: left;
    width: 100%;
    cursor: pointer;
    transition: background-color 0.2s;
    font-weight: 500;
  }
  
  .export-dropdown-content button:hover {
    background-color: var(--primary-color-light, #e6f0ff);
    color: var(--primary-color);
  }
  
  .export-dropdown:hover .export-dropdown-content {
    display: block;
  }
  
  /* Speaker editor styles */
  .speaker-editor-container {
    margin-top: 1rem;
    padding: 1.5rem;
    border: 1px solid var(--border-color, #e5e7eb);
    border-radius: 16px;
    background-color: var(--card-background, var(--surface-color, #ffffff));
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  }
  
  .speaker-list {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    margin-top: 1rem;
  }
  
  .speaker-item {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 0.75rem;
    background-color: var(--card-background, var(--surface-color, #ffffff));
    border-radius: 12px;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.03);
    transition: all 0.2s ease;
  }
  
  .speaker-item:hover {
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.06);
    transform: translateY(-1px);
  }
  
  .speaker-original {
    min-width: 100px;
    font-weight: bold;
    color: var(--text-color, #4b5563);
  }
  
  .speaker-item input {
    flex: 1;
    padding: 0.6rem 0.8rem;
    border: 1px solid var(--border-color, #e5e7eb);
    border-radius: 8px;
    background-color: var(--input-background, var(--surface-color, #ffffff));
    color: var(--text-color, #1f2937);
    transition: all 0.2s ease;
  }
  
  .speaker-item input:focus {
    border-color: var(--primary-color, #3b82f6);
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15);
    outline: none;
  }
  
  .save-speakers-button {
    margin-top: 1.25rem;
    align-self: flex-start;
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
