<script lang="ts">
  import { onMount, onDestroy, afterUpdate } from 'svelte';
  import { writable } from 'svelte/store';
  import Plyr from 'plyr';
  import 'plyr/dist/plyr.css';
  import axiosInstance from '$lib/axios';
  import { formatTimestampWithMillis } from '$lib/utils/formatting';
  import { websocketStore } from '$stores/websocket';
  
  // Import new components
  import VideoPlayer from '$components/VideoPlayer.svelte';
  import WaveformPlayer from '$components/WaveformPlayer.svelte';
  import MetadataDisplay from '$components/MetadataDisplay.svelte';
  import AnalyticsSection from '$components/AnalyticsSection.svelte';
  import TranscriptDisplay from '$components/TranscriptDisplay.svelte';
  import FileHeader from '$components/FileHeader.svelte';
  import TagsSection from '$components/TagsSection.svelte';
  import CommentSection from '$components/CommentSection.svelte';
  import CollectionsSection from '$components/CollectionsSection.svelte';
  import ReprocessButton from '$components/ReprocessButton.svelte';
  import ConfirmationModal from '$components/ConfirmationModal.svelte';
  import SummaryModal from '$components/SummaryModal.svelte';
  import { llmStatusStore, isLLMAvailable } from '../stores/llmStatus';
  
  // No need for a global commentsForExport variable - we'll fetch when needed

  // Props
  export let id = '';

  // State variables
  let file: any = null;
  let fileId = '';
  let videoUrl = '';
  let errorMessage = '';
  let apiBaseUrl = '';
  let player: Plyr | null = null;
  let currentTime = 0;
  let duration = 0;
  let isLoading = true;
  let isPlayerBuffering = false;
  let loadProgress = 0;
  let playerInitialized = false;
  let videoElementChecked = false;
  let collections: any[] = [];

  // UI state
  let showMetadata = false;
  let isTagsExpanded = false;
  let isCollectionsExpanded = false;
  let isAnalyticsExpanded = false;
  let isEditingTranscript = false;
  let editedTranscript = '';
  let savingTranscript = false;
  let transcriptError = '';
  let editingSegmentId: string | number | null = null;
  let editingSegmentText = '';
  let isEditingSpeakers = false;
  let speakerList: any[] = [];
  let reprocessing = false;
  let summaryData: any = null;
  let showSummaryModal = false;
  let generatingSummary = false;
  let summaryError = '';
  let summaryGenerating = false; // WebSocket-driven summary generation status
  // LLM availability for summary functionality
  $: llmAvailable = $isLLMAvailable;
  
  

  // Confirmation modal state
  let showExportConfirmation = false;
  let pendingExportFormat = '';

  // Reactive store for file updates
  const reactiveFile = writable(null);
  
  // Debounce timer for subtitle refresh
  let subtitleRefreshTimer: number;

  /**
   * Fetches file details from the API
   */
  async function fetchFileDetails(fileIdOrEvent?: string): Promise<void> {
    const targetFileId = typeof fileIdOrEvent === 'string' ? fileIdOrEvent : fileId;
    
    if (!targetFileId) {
      console.error('FileDetail: No file ID provided to fetchFileDetails');
      errorMessage = 'No file ID provided';
      isLoading = false;
      return;
    }

    try {
      isLoading = true;
      errorMessage = '';

      const response = await axiosInstance.get(`/api/files/${targetFileId}`);
      
      if (response.data && typeof response.data === 'object') {
        file = response.data;
        collections = response.data.collections || [];
        reactiveFile.set(file);

        // Set up video URL using the simple-video endpoint
        setupVideoUrl(targetFileId);
        
        // Process transcript data from the file response
        processTranscriptData();
        
        // Fetch analytics separately
        await fetchAnalytics(targetFileId);

        isLoading = false;
      } else {
        throw new Error('Invalid response format');
      }
    } catch (error) {
      console.error('Error fetching file details:', error);
      errorMessage = 'Failed to load file details. Please try again.';
      isLoading = false;
    }
  }

  /**
   * Fetch analytics data for a file
   */
  async function fetchAnalytics(fileId: string) {
    try {
      // Since there's no dedicated analytics endpoint, create analytics from available data
      const transcriptData = file?.transcript_segments;
      if (file && transcriptData && transcriptData.length > 0) {
        const speakerCounts: any = {};
        const speakerTimes: any = {};
        let totalWords = 0;
        let totalDuration = 0;
        
        // Create a speaker mapping from current speakerList for latest display names
        const speakerMapping = new Map();
        speakerList.forEach((speaker: any) => {
          // Map both the original name and any existing display names to the current display name
          speakerMapping.set(speaker.name, speaker.display_name || speaker.name);
          if (speaker.display_name) {
            speakerMapping.set(speaker.display_name, speaker.display_name);
          }
        });
        
        transcriptData.forEach((segment: any) => {
          // Get the speaker identifier from the segment
          const segmentSpeakerLabel = segment.speaker_label || segment.speaker?.name || 'Unknown';
          // Use the latest display name from speakerList, or fall back to segment data
          const speaker = speakerMapping.get(segmentSpeakerLabel) || 
                         segment.speaker?.display_name || 
                         segmentSpeakerLabel;
          
          const words = segment.text.split(/\s+/).filter(Boolean).length;
          const segmentDuration = (segment.end_time || 0) - (segment.start_time || 0);
          
          speakerCounts[speaker] = (speakerCounts[speaker] || 0) + words;
          speakerTimes[speaker] = (speakerTimes[speaker] || 0) + segmentDuration;
          totalWords += words;
          totalDuration += segmentDuration;
        });
        
        // Create new analytics object
        const newAnalytics = {
          overall: {
            word_count: totalWords,
            duration_seconds: file.duration || totalDuration,
            talk_time: {
              by_speaker: speakerTimes,
              total: totalDuration
            },
            interruptions: {
              by_speaker: {},
              total: 0
            },
            turn_taking: {
              by_speaker: speakerCounts,
              total_turns: transcriptData.length
            },
            questions: {
              by_speaker: {},
              total: 0
            }
          }
        };
        
        // Create a new file object to trigger reactivity
        file = {
          ...file,
          analytics: newAnalytics
        };
        
        reactiveFile.set(file);
      } else {
        console.warn('FileDetail: No transcript data available for analytics');
      }
    } catch (error) {
      console.error('Error creating analytics:', error);
    }
  }

  /**
   * Process transcript data from the main file response
   */
  function processTranscriptData() {
    // Use transcript_segments from backend
    let transcriptData = file?.transcript_segments;
    
    if (!file || !transcriptData || !Array.isArray(transcriptData)) {
      return;
    }
    
    try {
      // Sort transcript segments by start_time to ensure proper ordering
      transcriptData = [...transcriptData].sort((a: any, b: any) => {
        const aStart = parseFloat(a.start_time || a.start || 0);
        const bStart = parseFloat(b.start_time || b.start || 0);
        return aStart - bStart;
      });
      
      // Update the file with sorted data
      file.transcript_segments = transcriptData;
      
      // Update transcript text for editing
      editedTranscript = transcriptData.map((seg: any) => 
        `${formatTimestampWithMillis(seg.start_time)} [${seg.speaker_label || seg.speaker?.name || 'Speaker'}]: ${seg.text}`
      ).join('\n');
      
      loadSpeakers();
    } catch (error) {
      console.error('Error processing transcript:', error);
    }
  }

  /**
   * Extract speaker number from SPEAKER_XX format for sorting
   */
  function getSpeakerNumber(speakerName: string): number {
    const match = speakerName.match(/^SPEAKER_(\d+)$/);
    return match ? parseInt(match[1], 10) : 999; // Unknown speakers go to end
  }

  /**
   * Load speakers for the current file
   */
  async function loadSpeakers() {
    if (!file?.id) return;
    
    try {
      // Load speakers from the backend API
      const response = await axiosInstance.get(`/api/speakers/`, {
        params: { file_id: file.id }
      });
      
      if (response.data && Array.isArray(response.data)) {
        console.log('Raw speaker data from API:', response.data);
        speakerList = response.data
          .map((speaker: any) => ({
            id: speaker.id,
            name: speaker.name,
            display_name: speaker.display_name || '',  // Empty for unlabeled speakers to show suggestions
            suggested_name: speaker.suggested_name,
            uuid: speaker.uuid,
            verified: speaker.verified,
            confidence: speaker.confidence,
            profile: speaker.profile,
            cross_video_matches: (speaker.cross_video_matches || []).filter((match) => parseFloat(match.confidence) >= 0.75), // Only high-confidence matches (≥75%)
            showMatches: false  // Add this for the collapsible UI
          }))
          .sort((a, b) => getSpeakerNumber(a.name) - getSpeakerNumber(b.name));
        
      } else {
        // Fallback: extract from transcript data
        const transcriptData = file?.transcript_segments;
        if (transcriptData) {
          const speakers = new Map();
          transcriptData.forEach((segment: any) => {
            const speakerLabel = segment.speaker_label || segment.speaker?.name || 'Unknown';
            if (!speakers.has(speakerLabel)) {
              speakers.set(speakerLabel, {
                name: speakerLabel,
                display_name: segment.speaker?.display_name || speakerLabel
              });
            }
          });
          speakerList = Array.from(speakers.values())
            .sort((a, b) => getSpeakerNumber(a.name) - getSpeakerNumber(b.name));
        }
      }
    } catch (error) {
      console.error('Error loading speakers:', error);
      // Fallback: extract from transcript data
      const transcriptData = file?.transcript_segments;
      if (transcriptData) {
        const speakers = new Map();
        transcriptData.forEach((segment: any) => {
          const speakerLabel = segment.speaker_label || segment.speaker?.name || 'Unknown';
          if (!speakers.has(speakerLabel)) {
            speakers.set(speakerLabel, {
              name: speakerLabel,
              display_name: segment.speaker?.display_name || speakerLabel
            });
          }
        });
        speakerList = Array.from(speakers.values())
          .sort((a, b) => getSpeakerNumber(a.name) - getSpeakerNumber(b.name));
      }
    }
  }

  /**
   * Set up the video URL for streaming
   */
  function setupVideoUrl(fileId: string) {
    // Check if this is a video file with completed transcription
    const isVideo = file?.content_type && file.content_type.startsWith('video/');
    const hasTranscript = file?.status === 'completed';
    
    // Always use the original video for playback - we'll add subtitles via WebVTT tracks
    videoUrl = `${apiBaseUrl}/api/files/${fileId}/simple-video`;
    
    // Ensure URL has proper formatting
    if (videoUrl && !videoUrl.startsWith('/') && !videoUrl.startsWith('http')) {
      videoUrl = '/' + videoUrl;
    }
    
    // Reset video element check flag to prompt afterUpdate to try initialization
    videoElementChecked = false;
  }


  /**
   * Add subtitle track to video element dynamically
   */
  async function addSubtitleTrack() {
    if (!file || !player) return;
    
    try {
      // Get the video element from Plyr
      const videoElement = player.media;
      if (!videoElement) return;
      
      // Fetch subtitles using axios to include authentication
      const timestamp = Date.now();
      const response = await axiosInstance.get(`/files/${file.id}/subtitles`, {
        params: {
          format: 'webvtt',
          include_speakers: true,
          t: timestamp
        },
        responseType: 'text'
      });
      
      // Create a blob URL from the subtitle content
      const blob = new Blob([response.data], { type: 'text/vtt' });
      const subtitleUrl = URL.createObjectURL(blob);
      
      // Create subtitle track element
      const track = document.createElement('track');
      track.kind = 'subtitles';
      track.label = 'English (Auto-generated)';
      track.srclang = 'en';
      track.default = true;
      track.src = subtitleUrl;
      
      // Add track to video element
      videoElement.appendChild(track);
      
      // Enable the track
      track.addEventListener('load', () => {
        if (videoElement.textTracks && videoElement.textTracks.length > 0) {
          const textTrack = videoElement.textTracks[videoElement.textTracks.length - 1];
          textTrack.mode = 'showing';
          
          // Enable captions in Plyr
          if (player && player.captions) {
            player.captions.active = true;
          }
          
          console.log('Subtitle track loaded and enabled');
        }
      });
      
      // Clean up blob URL when track is removed
      track.addEventListener('error', () => {
        URL.revokeObjectURL(subtitleUrl);
      });
      
    } catch (error) {
      console.error('Error adding subtitle track:', error);
    }
  }

  /**
   * Refresh subtitle track when transcript changes (debounced)
   */
  function refreshSubtitleTrack() {
    // Clear existing timer
    if (subtitleRefreshTimer) {
      clearTimeout(subtitleRefreshTimer);
    }
    
    // Set new timer for 1 second debounce
    subtitleRefreshTimer = setTimeout(() => {
      if (!player || !file) return;
      
      const videoElement = player.media;
      if (!videoElement) return;
      
      // Remove existing subtitle tracks and clean up blob URLs
      const tracks = Array.from(videoElement.querySelectorAll('track[kind="subtitles"]'));
      tracks.forEach(track => {
        // Clean up blob URL if it's a blob URL
        if (track.src && track.src.startsWith('blob:')) {
          URL.revokeObjectURL(track.src);
        }
        track.remove();
      });
      
      // Add updated subtitle track with cache-busting timestamp
      addSubtitleTrack();
      
      console.log('Subtitle track refreshed due to transcript changes');
    }, 1000);
  }

  /**
   * Initialize the video player with enhanced streaming capabilities
   */
  function initializePlayer() {
    if (playerInitialized || !videoUrl) {
      return;
    }
    
    const videoElement = document.querySelector('#player') as HTMLVideoElement;
    
    if (!videoElement) {
      return;
    }

    try {
      // Configure video element
      videoElement.preload = 'metadata';
      videoElement.crossOrigin = 'anonymous';
      videoElement.playsInline = true;

      // Check if this video has embedded subtitles
      const isVideo = file?.content_type && file.content_type.startsWith('video/');
      const hasTranscript = file?.status === 'completed';
      const hasEmbeddedSubtitles = isVideo && hasTranscript;

      // Initialize Plyr with subtitle support
      const plyrControls = ['play-large', 'play', 'progress', 'current-time', 'duration', 'mute', 'volume', 'settings', 'fullscreen'];
      const plyrSettings = ['quality', 'speed'];
      
      // Add captions/subtitles controls if the video has embedded subtitles
      if (hasEmbeddedSubtitles) {
        plyrControls.splice(-1, 0, 'captions'); // Add captions button before fullscreen
        plyrSettings.push('captions'); // Add captions to settings menu
      }

      player = new Plyr(videoElement, {
        controls: plyrControls,
        settings: plyrSettings,
        quality: { default: 720, options: [1080, 720, 480, 360] },
        speed: { selected: 1, options: [0.5, 0.75, 1, 1.25, 1.5, 2] },
        ratio: '16:9',
        fullscreen: { enabled: true, fallback: true, iosNative: true },
        captions: { 
          active: true, // Enable captions by default if available
          language: 'auto',
          update: true
        }
      });

      // Set up event listeners
      player.on('ready', () => {
        playerInitialized = true;
        
        // Add subtitle tracks dynamically if video has completed transcription
        if (hasEmbeddedSubtitles) {
          addSubtitleTrack();
        }
      });

      player.on('timeupdate', () => {
        currentTime = player?.currentTime || 0;
        updateCurrentSegment(currentTime);
      });

      player.on('loadedmetadata', () => {
        duration = player?.duration || 0;
      });

      player.on('loadstart', () => {
        isPlayerBuffering = true;
      });

      player.on('canplay', () => {
        isPlayerBuffering = false;
      });

      player.on('waiting', () => {
        isPlayerBuffering = true;
      });

      player.on('playing', () => {
        isPlayerBuffering = false;
      });

      player.on('progress', () => {
        if (videoElement.buffered.length > 0) {
          loadProgress = (videoElement.buffered.end(0) / videoElement.duration) * 100;
        }
      });
      
    } catch (error) {
      console.error('Error initializing player:', error);
      errorMessage = 'Failed to initialize video player';
      playerInitialized = false;
    }
  }

  /**
   * Update current segment highlighting without auto-scrolling
   */
  function updateCurrentSegment(currentPlaybackTime: number): void {
    const transcriptData = file?.transcript_segments;
    if (!file || !transcriptData || !Array.isArray(transcriptData)) return;
    
    const allSegments = document.querySelectorAll('.transcript-segment');
    allSegments.forEach(segment => {
      segment.classList.remove('active-segment');
    });
    
    const currentSegment = transcriptData.find((segment: any) => {
      return currentPlaybackTime >= segment.start_time && currentPlaybackTime <= segment.end_time;
    });
    
    if (currentSegment) {
      const segmentElement = document.querySelector(`[data-segment-id="${currentSegment.id || `${currentSegment.start_time}-${currentSegment.end_time}`}"]`);
      if (segmentElement) {
        segmentElement.classList.add('active-segment');
        // Remove auto-scroll to allow manual scrolling
      }
    }
  }

  // Event handlers for components
  function handleSegmentClick(event: any) {
    const startTime = event.detail.startTime;
    seekToTime(startTime);
  }

  // Handle speaker name updates
  async function handleSpeakerUpdate(event: CustomEvent) {
    const { speakerId, newName } = event.detail;
    
    // Update the speaker in the speakerList and maintain sort order
    speakerList = speakerList
      .map(speaker => {
        if (speaker.id === speakerId || speaker.uuid === speakerId) {
          return { ...speaker, display_name: newName, name: newName };
        }
        return speaker;
      })
      .sort((a, b) => getSpeakerNumber(a.name) - getSpeakerNumber(b.name));
    
    // Update transcript data with new speaker name
    const transcriptData = file?.transcript_segments;
    if (transcriptData && Array.isArray(transcriptData)) {
      transcriptData.forEach(segment => {
        if (segment.speaker_id === speakerId) {
          segment.speaker = newName;
        }
      });
      
      // Update file data
      file.transcript_segments = [...transcriptData];
      file = { ...file }; // Trigger reactivity
      reactiveFile.set(file);
      
      // Refresh subtitle track with debounce since speaker labels changed
      refreshSubtitleTrack();
    }
    
    // Persist to database
    try {
      const speaker = speakerList.find(s => s.id === speakerId || s.uuid === speakerId);
      if (speaker && speaker.id) {
        await axiosInstance.put(`/api/speakers/${speaker.id}`, {
          display_name: newName,
          name: newName
        });
      }
    } catch (error) {
      console.error('Failed to update speaker name in database:', error);
    }
  }

  function handleEditSegment(event: any) {
    const segment = event.detail.segment;
    editingSegmentId = segment.id;
    editingSegmentText = segment.text;
  }


  function formatSimpleTimestamp(seconds: number): string {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
  }

  // Format seconds to SRT timestamp format (HH:MM:SS,mmm)
  function formatSrtTimestamp(seconds: number): string {
    if (isNaN(seconds) || seconds < 0) seconds = 0;
    
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    const milliseconds = Math.floor((seconds % 1) * 1000);
    
    return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')},${String(milliseconds).padStart(3, '0')}`;
  }

  // Format seconds to VTT timestamp format (HH:MM:SS.mmm)
  function formatVttTimestamp(seconds: number): string {
    if (isNaN(seconds) || seconds < 0) seconds = 0;
    
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    const milliseconds = Math.floor((seconds % 1) * 1000);
    
    return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}.${String(milliseconds).padStart(3, '0')}`;
  }

  async function handleSaveSegment(event: any) {
    const segment = event.detail.segment;
    if (!segment || !editingSegmentText) return;
    
    try {
      savingTranscript = true;
      
      // Call backend API to update the specific segment
      const segmentUpdate = {
        text: editingSegmentText
      };
      
      const response = await axiosInstance.put(`/api/files/${fileId}/transcript/segments/${segment.id}`, segmentUpdate);
      
      if (response.data) {
        // Update the specific segment in local data
        const transcriptData = file?.transcript_segments;
        if (transcriptData && file) {
          const segmentIndex = transcriptData.findIndex((s: any) => s.id === segment.id);
          
          if (segmentIndex !== -1) {
            // Create a new array with the updated segment
            const updatedSegments = [...transcriptData];
            updatedSegments[segmentIndex] = response.data;
            
            // Update file with new segments array
            file = { 
              ...file, 
              transcript_segments: updatedSegments 
            };
            reactiveFile.set(file);
            
            // Refresh subtitle track with debounce
            refreshSubtitleTrack();
            
            // Clear cached processed videos so downloads will use updated transcript
            try {
              await axiosInstance.delete(`/api/files/${file.id}/cache`);
              console.log('Cleared video cache to ensure downloads use updated transcript');
            } catch (error) {
              console.warn('Could not clear video cache:', error);
            }
          }
        }
        
        editingSegmentId = null;
        editingSegmentText = '';
        transcriptError = '';
      }
    } catch (error: any) {
      console.error('Error saving segment:', error);
      
      // If API call fails, show specific error message
      if (error.response?.status === 405) {
        transcriptError = 'Transcript editing is not supported by the server';
      } else if (error.response?.status === 404) {
        transcriptError = 'Transcript segment not found';
      } else {
        transcriptError = 'Failed to save segment changes';
      }
    } finally {
      savingTranscript = false;
    }
  }

  function handleCancelEditSegment() {
    editingSegmentId = null;
    editingSegmentText = '';
  }

  async function handleSaveTranscript() {
    if (!editedTranscript || !file) return;
    
    try {
      savingTranscript = true;
      const response = await axiosInstance.put(`/api/files/${fileId}/transcript`, {
        transcript: editedTranscript
      });
      
      if (response.data) {
        // Refresh file data
        await fetchFileDetails(fileId);
        isEditingTranscript = false;
        transcriptError = '';
      }
    } catch (error) {
      console.error('Error saving transcript:', error);
      transcriptError = 'Failed to save transcript';
    } finally {
      savingTranscript = false;
    }
  }


  async function handleExportTranscript(event: any) {
    const format = event.detail.format;
    let transcriptData = file?.transcript_segments;
    if (!file || !transcriptData) return;
    
    // Check if there are any comments for this file
    let hasComments = false;
    try {
      const token = localStorage.getItem('token');
      if (token) {
        const headers = {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        };
        const numericFileId = Number(file.id);
        const endpoint = `/comments/files/${numericFileId}/comments`;
        const response = await axiosInstance.get(endpoint, { headers });
        const fileComments = response.data || [];
        hasComments = fileComments.length > 0;
      }
    } catch (error) {
      console.error('Error checking for comments:', error);
      // If we can't check comments, assume no comments
      hasComments = false;
    }
    
    // If no comments, export directly without modal
    if (!hasComments) {
      pendingExportFormat = format;
      processExportWithComments(false);
      return;
    }
    
    // If comments exist, show confirmation modal
    pendingExportFormat = format;
    showExportConfirmation = true;
  }

  async function processExportWithComments(includeComments: boolean) {
    const format = pendingExportFormat;
    let transcriptData = file?.transcript_segments;
    if (!file || !transcriptData) return;
    // Fetch comments if user wants to include them
    let fileComments: any[] = [];
    if (includeComments) {
      try {
        const token = localStorage.getItem('token');
        if (token) {
          const headers = {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          };
          const numericFileId = Number(file.id);
          const endpoint = `/comments/files/${numericFileId}/comments`;
          const response = await axiosInstance.get(endpoint, { headers });
          fileComments = response.data || [];
          
          // Get current user data from localStorage
          const userData = JSON.parse(localStorage.getItem('user') || '{}');
          
          // Add current user data to each comment
          fileComments = fileComments.map((comment: any) => {
            // If the comment is from the current user, add their details
            if (!comment.user && comment.user_id === userData.id) {
              comment.user = {
                full_name: userData.full_name,
                username: userData.username,
                email: userData.email
              };
            } else if (!comment.user) {
              // For other users' comments that have no user object,
              // create a placeholder to avoid 'Anonymous'
              comment.user = {
                full_name: 'Admin User', // Default from browser info
                username: 'admin',
                email: 'admin@example.com'
              };
            }
            return comment;
          });
          
          // Sort comments by timestamp
          fileComments.sort((a: any, b: any) => a.timestamp - b.timestamp);
        }
      } catch (error) {
        console.error('Error fetching comments for export:', error);
        // Continue with export even if comments can't be fetched
      }
    }
    
    try {
      // Sort transcript data by start_time to ensure proper ordering
      transcriptData = [...transcriptData].sort((a: any, b: any) => a.start_time - b.start_time);
      
      // Create speaker display name mapping
      const speakerMapping = new Map();
      speakerList.forEach((speaker: any) => {
        speakerMapping.set(speaker.name, speaker.display_name || speaker.name);
      });
      
      // Helper function to get speaker display name
      const getSpeakerDisplayName = (segment: any) => {
        const speakerName = segment.speaker_label || segment.speaker?.name || 'Speaker';
        return speakerMapping.get(speakerName) || segment.speaker?.display_name || speakerName;
      };
      
      // Client-side export with updated speaker names
      let content = '';
      const filename = file.filename.replace(/\.[^/.]+$/, '');
      
      switch (format) {
        case 'txt':
          // Create transcript content with segments
          let segments = transcriptData.map((seg: any) => 
            `[${formatSimpleTimestamp(seg.start_time)}] ${getSpeakerDisplayName(seg)}: ${seg.text}`
          );
          
          // Add comments if requested
          if (includeComments && fileComments.length > 0) {
            const commentLines = fileComments.map((comment: any) => {
              const userName = comment.user?.full_name || comment.user?.username || comment.user?.email || 'Anonymous';
              return `[${formatSimpleTimestamp(comment.timestamp)}] USER COMMENT: ${userName}: ${comment.text}`;
            });
            segments = mergeCommentsWithTranscript(segments, commentLines, transcriptData, fileComments);
          }
          
          content = segments.join('\n\n');
          break;
        case 'json':
          const jsonData: any = {
            filename: file.filename,
            duration: file.duration,
            segments: transcriptData.map((seg: any) => ({
              start_time: seg.start_time || seg.start || 0,
              end_time: seg.end_time || seg.end || 0,
              speaker: getSpeakerDisplayName(seg),
              text: seg.text
            }))
          };
          
          // Add comments to JSON if requested
          if (includeComments && fileComments.length > 0) {
            jsonData.comments = fileComments.map((comment: any) => ({
              timestamp: comment.timestamp,
              user: comment.user?.full_name || comment.user?.username || comment.user?.email || 'Anonymous',
              text: comment.text
            }));
          }
          
          content = JSON.stringify(jsonData, null, 2);
          break;
        case 'csv':
          let csvHeader = 'Start Time,End Time,Speaker,Text';
          let csvRows = transcriptData.map((seg: any) => {
            const start = seg.start_time || seg.start || 0;
            const end = seg.end_time || seg.end || 0;
            const speaker = getSpeakerDisplayName(seg);
            // Escape CSV fields properly
            const escapedText = `"${seg.text.replace(/"/g, '""')}"`;
            return `${start},${end},"${speaker}",${escapedText}`;
          });
          
          // Add comments to CSV if requested
          if (includeComments && fileComments.length > 0) {
            // Add comment column to header if comments are included
            csvHeader = 'Start Time,End Time,Speaker,Text,Comment Type';
            
            // Add comments as separate rows
            const commentRows = fileComments.map((comment: any) => {
              const timestamp = comment.timestamp;
              const userName = comment.user?.full_name || comment.user?.username || comment.user?.email || 'Anonymous';
              const escapedText = `"${comment.text.replace(/"/g, '""')}"`;
              // Add comment rows with user info in the Speaker column and 'COMMENT' in Comment Type
              return `${timestamp},${timestamp},"USER COMMENT: ${userName}",${escapedText},"COMMENT"`;
            });
            
            // Combine segment rows (with empty Comment Type) with comment rows
            csvRows = csvRows.map((row: string) => row + ',""');
            csvRows = mergeSortedArrays(csvRows, commentRows, 
              transcriptData.map((seg: any) => seg.start_time || seg.start || 0),
              fileComments.map((comment: any) => comment.timestamp));
          }
          
          content = csvHeader + '\n' + csvRows.join('\n');
          break;
        case 'srt':
          let srtItems: Array<{
            index: number;
            startTime: number;
            endTime: number;
            formattedStart: string;
            formattedEnd: string;
            text: string;
            isComment: boolean;
          }> = [];
          let counter = 1;
          
          // Add transcript segments
          transcriptData.forEach((seg: any) => {
            const startTime = formatSrtTimestamp(seg.start_time || seg.start || 0);
            const endTime = formatSrtTimestamp(seg.end_time || seg.end || 0);
            const speaker = getSpeakerDisplayName(seg);
            const text = `${speaker}: ${seg.text}`;
            srtItems.push({
              index: counter++,
              startTime: seg.start_time || seg.start || 0,
              endTime: seg.end_time || seg.end || 0,
              formattedStart: startTime,
              formattedEnd: endTime,
              text: text,
              isComment: false
            });
          });
          
          // Add comments if requested
          if (includeComments && fileComments.length > 0) {
            fileComments.forEach(comment => {
              const timestamp = comment.timestamp;
              const formattedTime = formatSrtTimestamp(timestamp);
              const userName = comment.user?.full_name || comment.user?.username || comment.user?.email || 'Anonymous';
              const text = `USER COMMENT: ${userName}: ${comment.text}`;
              
              srtItems.push({
                index: counter++,
                startTime: timestamp,
                endTime: timestamp + 2, // Show comment for 2 seconds
                formattedStart: formattedTime,
                formattedEnd: formatSrtTimestamp(timestamp + 2),
                text: text,
                isComment: true
              });
            });
            
            // Sort by start time
            srtItems.sort((a: any, b: any) => a.startTime - b.startTime);
            
            // Reassign indices after sorting
            srtItems.forEach((item: any, idx: number) => {
              item.index = idx + 1;
            });
          }
          
          // Generate SRT content
          content = srtItems.map((item: any) => 
            `${item.index}\n${item.formattedStart} --> ${item.formattedEnd}\n${item.text}\n`
          ).join('\n');
          break;
        case 'vtt':
          let vttItems: Array<{
            startTime: number;
            endTime: number;
            formattedStart: string;
            formattedEnd: string;
            text: string;
            isComment: boolean;
          }> = [];
          
          // Add transcript segments
          transcriptData.forEach((seg: any) => {
            const startTime = formatVttTimestamp(seg.start_time || seg.start || 0);
            const endTime = formatVttTimestamp(seg.end_time || seg.end || 0);
            const speaker = getSpeakerDisplayName(seg);
            const text = `${speaker}: ${seg.text}`;
            vttItems.push({
              startTime: seg.start_time || seg.start || 0,
              endTime: seg.end_time || seg.end || 0,
              formattedStart: startTime,
              formattedEnd: endTime,
              text: text,
              isComment: false
            });
          });
          
          // Add comments if requested
          if (includeComments && fileComments.length > 0) {
            fileComments.forEach(comment => {
              const timestamp = comment.timestamp;
              const formattedTime = formatVttTimestamp(timestamp);
              const userName = comment.user?.full_name || comment.user?.username || comment.user?.email || 'Anonymous';
              const text = `USER COMMENT: ${userName}: ${comment.text}`;
              
              vttItems.push({
                startTime: timestamp,
                endTime: timestamp + 2, // Show comment for 2 seconds
                formattedStart: formattedTime,
                formattedEnd: formatVttTimestamp(timestamp + 2),
                text: text,
                isComment: true
              });
            });
            
            // Sort by start time
            vttItems.sort((a: any, b: any) => a.startTime - b.startTime);
          }
          
          // Generate VTT content
          content = 'WEBVTT\n\n' + vttItems.map((item: any) => 
            `${item.formattedStart} --> ${item.formattedEnd}\n${item.text}\n`
          ).join('\n');
          break;
        default:
          content = transcriptData.map((seg: any) => seg.text).join(' ');
      }
      
      const blob = new Blob([content], { type: 'text/plain' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${filename}.${format}`;
      link.click();
      window.URL.revokeObjectURL(url);
      // Transcript exported successfully
    } catch (error) {
      console.error('Error exporting transcript:', error);
    }
  }

  // Confirmation modal handlers
  function handleExportConfirm() {
    processExportWithComments(true);
  }

  function handleExportCancel() {
    processExportWithComments(false);
  }

  function handleExportModalClose() {
    // Just close the modal without doing anything
    showExportConfirmation = false;
  }
  
  /**
   * Merges transcript segments and comments in chronological order
   * @param {string[]} segments - Array of formatted transcript segment strings
   * @param {string[]} commentLines - Array of formatted comment strings
   * @param {any[]} transcriptData - Raw transcript data with timestamps
   * @param {any[]} comments - Raw comments data with timestamps
   * @returns {string[]} - Combined array of segments and comments in order
   */
  function mergeCommentsWithTranscript(segments: string[], commentLines: string[], transcriptData: any[], comments: any[]): string[] {
    // Create arrays of timestamps for sorting
    const segmentTimes = transcriptData.map((seg: any) => seg.start_time || seg.start || 0);
    const commentTimes = comments.map((comment: any) => comment.timestamp);
    
    // Create merged array of segment and comment entries
    let merged = [];
    let si = 0, ci = 0;
    
    // Merge two sorted arrays (segments and comments) by timestamp
    while (si < segments.length && ci < commentLines.length) {
      if (segmentTimes[si] <= commentTimes[ci]) {
        merged.push(segments[si]);
        si++;
      } else {
        merged.push(commentLines[ci]);
        ci++;
      }
    }
    
    // Add any remaining segments
    while (si < segments.length) {
      merged.push(segments[si]);
      si++;
    }
    
    // Add any remaining comments
    while (ci < commentLines.length) {
      merged.push(commentLines[ci]);
      ci++;
    }
    
    return merged;
  }
  
  /**
   * Merges two arrays based on their corresponding timestamp arrays
   * @param {any[]} arr1 - First array
   * @param {any[]} arr2 - Second array
   * @param {number[]} times1 - Timestamps for first array
   * @param {number[]} times2 - Timestamps for second array
   * @returns {any[]} - Merged array in chronological order
   */
  function mergeSortedArrays<T>(arr1: T[], arr2: T[], times1: number[], times2: number[]): T[] {
    let merged = [];
    let i = 0, j = 0;
    
    while (i < arr1.length && j < arr2.length) {
      if (times1[i] <= times2[j]) {
        merged.push(arr1[i]);
        i++;
      } else {
        merged.push(arr2[j]);
        j++;
      }
    }
    
    while (i < arr1.length) {
      merged.push(arr1[i]);
      i++;
    }
    
    while (j < arr2.length) {
      merged.push(arr2[j]);
      j++;
    }
    
    return merged;
  }

  async function handleSaveSpeakerNames() {
    if (!speakerList || speakerList.length === 0) return;
    
    try {
      // Update speakers in the backend (only meaningful names)
      const updatePromises = speakerList
        .filter(speaker => 
          speaker.id && 
          speaker.display_name && 
          speaker.display_name.trim() !== "" && 
          !speaker.display_name.startsWith('SPEAKER_')
        )
        .map(async (speaker: any) => {
          // Update existing speaker with meaningful display name
          return axiosInstance.put(`/api/speakers/${speaker.id}`, {
            display_name: speaker.display_name.trim(),
            name: speaker.name
          });
        });
      
      await Promise.all(updatePromises);
      
      // Update local transcript data with new display names
      const transcriptData = file?.transcript_segments;
      if (transcriptData) {
        const speakerMapping = new Map();
        speakerList.forEach((speaker: any) => {
          speakerMapping.set(speaker.name, speaker.display_name);
        });
        
        transcriptData.forEach((segment: any) => {
          const speakerName = segment.speaker_label || segment.speaker?.name;
          const newDisplayName = speakerMapping.get(speakerName);
          if (newDisplayName && segment.speaker) {
            segment.speaker.display_name = newDisplayName;
          } else if (newDisplayName) {
            segment.speaker = {
              name: speakerName,
              display_name: newDisplayName
            };
          }
        });
        
        // Update file data
        file.transcript_segments = [...transcriptData];
        file = { ...file }; // Trigger reactivity
        reactiveFile.set(file);
      }
      
      // Reload speakers to ensure consistent data and sort order
      await loadSpeakers();
      
      // Regenerate analytics with updated speaker names
      if (file?.id) {
        await fetchAnalytics(file.id.toString());
      }
      
      // Refresh video subtitles with updated speaker names
      refreshSubtitleTrack();
      
      // Clear cached processed videos so downloads will use updated speaker names
      try {
        await axiosInstance.delete(`/api/files/${file.id}/cache`);
        console.log('Cleared video cache to ensure downloads use updated speaker names');
        // Note: No user notification needed - this is automatic background cleanup
      } catch (error) {
        console.warn('Could not clear video cache:', error);
      }
      
      // Speaker names saved to database and updated locally
    } catch (error) {
      console.error('Error saving speaker names:', error);
      // Fall back to local-only updates
      const transcriptData = file?.transcript_segments;
      if (transcriptData) {
        const speakerMapping = new Map();
        speakerList.forEach((speaker: any) => {
          speakerMapping.set(speaker.name, speaker.display_name);
        });
        
        transcriptData.forEach((segment: any) => {
          const speakerName = segment.speaker_label || segment.speaker?.name;
          const newDisplayName = speakerMapping.get(speakerName);
          if (newDisplayName && segment.speaker) {
            segment.speaker.display_name = newDisplayName;
          } else if (newDisplayName) {
            segment.speaker = {
              name: speakerName,
              display_name: newDisplayName
            };
          }
        });
        
        file = { ...file };
        reactiveFile.set(file);
        
        // Reload speakers to ensure consistent data and sort order
        await loadSpeakers();
        
        // Regenerate analytics with updated speaker names
        if (file?.id) {
          await fetchAnalytics(file.id.toString());
        }
        
        // Refresh video subtitles with updated speaker names (fallback)
        refreshSubtitleTrack();
        
        // Clear cached processed videos so downloads will use updated speaker names (fallback)
        try {
          await axiosInstance.delete(`/api/files/${file.id}/cache`);
          console.log('Cleared video cache to ensure downloads use updated speaker names (fallback)');
        } catch (error) {
          console.warn('Could not clear video cache (fallback):', error);
        }
        
        // Speaker names updated locally only (database update failed)
      }
    }
  }

  function handleSeekTo(event: any) {
    const time = event.detail.time || event.detail;
    seekToTime(time);
  }


  // Speaker verification event handlers

  function seekToTime(time: number) {
    if (player) {
      // Add 0.5 second padding before the target time for better context
      const paddedTime = Math.max(0, time - 0.5);
      player.currentTime = paddedTime;
      
      // Flash player controls briefly to show timestamp
      const playerContainer = document.querySelector('.plyr');
      if (playerContainer) {
        playerContainer.classList.add('plyr--show-controls');
        setTimeout(() => {
          playerContainer.classList.remove('plyr--show-controls');
        }, 3000); // Show controls for 3 seconds
      }
      
      if (player.paused) {
        const playPromise = player.play();
        if (playPromise && typeof playPromise.catch === 'function') {
          playPromise.catch(console.error);
        }
      }
    }
  }

  function handleTagsUpdated(event: any) {
    if (file) {
      file.tags = event.detail.tags;
      reactiveFile.set(file);
    }
  }

  function handleCollectionRemoved(event: any) {
    const { collectionId } = event.detail;
    
    // Update collections array by removing the collection
    collections = collections.filter(c => c.id !== collectionId);
    
    // Update file object if it has collections
    if (file && file.collections) {
      file.collections = file.collections.filter((c: any) => c.id !== collectionId);
      file = { ...file }; // Trigger reactivity
      reactiveFile.set(file);
    }
  }

  function handleVideoRetry() {
    fetchFileDetails();
  }

  function handleWaveformSeek(event: CustomEvent) {
    const seekTime = event.detail.time;
    seekToTime(seekTime);
  }

  async function handleReprocess(event: CustomEvent) {
    const { fileId } = event.detail;
    
    try {
      reprocessing = true;
      await axiosInstance.post(`/api/files/${fileId}/reprocess`);
      
      // Refresh file details to show updated status
      await fetchFileDetails(fileId);
      
      console.log('File reprocessing started');
    } catch (error) {
      console.error('Error starting reprocess:', error);
      errorMessage = 'Failed to start reprocessing. Please try again.';
    } finally {
      reprocessing = false;
    }
  }


  /**
   * Generate summary for the transcript
   */
  async function handleGenerateSummary() {
    if (!file?.id) return;
    
    // Check if LLM is available
    if (!$isLLMAvailable) {
      summaryError = 'AI summary features are not available. Please configure an LLM provider in Settings.';
      return;
    }
    
    try {
      generatingSummary = true;
      summaryError = '';
      
      const response = await axiosInstance.post(`/api/files/${file.id}/summarize`);
      
      // Don't refresh page - let WebSocket notifications handle status updates
      // This preserves user's editing state
      console.log('Summary generation started:', response.data);
      
      // The WebSocket will update summaryGenerating = true when processing starts
    } catch (error: any) {
      console.error('Error generating summary:', error);
      const errorMessage = error.response?.data?.detail || 'Failed to generate summary. Please try again.';
      
      summaryError = errorMessage;
    } finally {
      generatingSummary = false;
    }
  }

  /**
   * Load summary data from the backend
   */
  async function loadSummary() {
    if (!file?.id) return;
    
    try {
      const response = await axiosInstance.get(`/api/files/${file.id}/summary`);
      summaryData = response.data.summary_data;
    } catch (error: any) {
      console.error('Error loading summary:', error);
      if (error.response?.status !== 404) {
        summaryError = 'Failed to load summary.';
      }
    }
  }

  /**
   * Show the summary modal
   */
  function handleShowSummary() {
    if (summaryData) {
      showSummaryModal = true;
    } else {
      loadSummary().then(() => {
        if (summaryData) {
          showSummaryModal = true;
        }
      });
    }
  }

  // WebSocket subscription for real-time updates
  let wsUnsubscribe: () => void;

  // Component mount logic
  onMount(() => {
    apiBaseUrl = window.location.origin;
    
    if (id) {
      fileId = id;
    } else {
      const urlParams = new URLSearchParams(window.location.search);
      const pathParts = window.location.pathname.split('/');
      fileId = urlParams.get('id') || pathParts[pathParts.length - 1] || '';
    }

    if (fileId && !isNaN(Number(fileId))) {
      // Load file details and initialize LLM status
      Promise.all([
        fetchFileDetails(),
        llmStatusStore.initialize()
      ]).catch(err => {
        console.error('Error loading page data:', err);
      });
    } else {
      errorMessage = 'Invalid file ID';
      isLoading = false;
    }

    // LLM status monitoring is now handled by the Settings component and reactive store

    // Track last processed notification to avoid duplicate processing
    let lastProcessedNotificationId = '';

    // Subscribe to WebSocket notifications for real-time updates
    wsUnsubscribe = websocketStore.subscribe(($ws) => {
      if ($ws.notifications.length > 0) {
        const latestNotification = $ws.notifications[0];
        
        // Only process if this is a new notification we haven't handled
        if (latestNotification.id !== lastProcessedNotificationId) {
          lastProcessedNotificationId = latestNotification.id;
          
          // Check if this notification is for our current file
          // Convert both to strings for comparison since notification sends file_id as string
          if (String(latestNotification.data?.file_id) === String(fileId)) {
            
            // Handle transcription status updates
            if (latestNotification.type === 'transcription_status') {
              // Update progress in real-time without full refresh for progress updates
              if (latestNotification.data?.status === 'processing' && latestNotification.data?.progress !== undefined) {
                if (file) {
                  file.progress = latestNotification.data.progress;
                  file.status = 'processing';
                  file = { ...file }; // Trigger reactivity
                  reactiveFile.set(file);
                }
                console.log('Progress update for file:', fileId, 'Progress:', latestNotification.data.progress + '%', 'Message:', latestNotification.data.message);
              } else {
                // For status changes (completed, error), do a full refresh
                console.log('Status change for file:', fileId, 'Status:', latestNotification.data?.status);
                fetchFileDetails();
              }
            }
            
            // WebSocket notifications for file updates
            
            // Handle summarization status updates
            if (latestNotification.type === 'summary_status') {
              const status = latestNotification.data?.status;
              console.log('Received summary_status notification:', status);
              
              if (status === 'processing' || status === 'generating') {
                // Summary generation started - show spinner without full refresh
                summaryGenerating = true;
                summaryError = '';
              } else if (status === 'completed') {
                // Summary completed - update file object without disrupting user workflow
                summaryGenerating = false;
                if (file) {
                  // Smartly update only summary-related fields
                  // Use fallback values to ensure summary is marked as available
                  file.summary = latestNotification.data?.summary || 'completed';
                  file.summary_opensearch_id = latestNotification.data?.summary_opensearch_id || 'completed';
                  file = { ...file }; // Trigger reactivity for button state
                }
              } else if (status === 'failed' || status === 'error') {
                // Summary failed - show error without full refresh
                summaryGenerating = false;
                summaryError = latestNotification.data?.message || 'Failed to generate summary';
              }
            }
          }
        }
      }
    });
  });

  onDestroy(() => {
    if (player) {
      try {
        // Clean up any subtitle blob URLs before destroying player
        const videoElement = player.media;
        if (videoElement) {
          const tracks = Array.from(videoElement.querySelectorAll('track[kind="subtitles"]'));
          tracks.forEach(track => {
            if (track.src && track.src.startsWith('blob:')) {
              URL.revokeObjectURL(track.src);
            }
          });
        }
        
        player.destroy();
        player = null;
        playerInitialized = false;
      } catch (err) {
        console.error('Error destroying player:', err);
      }
    }
    
    // Clear any pending subtitle refresh timer
    if (subtitleRefreshTimer) {
      clearTimeout(subtitleRefreshTimer);
    }
    
    // LLM status cleanup is handled by the Settings component
    
    // Clean up WebSocket subscription
    if (wsUnsubscribe) {
      wsUnsubscribe();
    }
  });

  afterUpdate(() => {
    if (videoUrl && !playerInitialized && !isLoading && !videoElementChecked) {
      videoElementChecked = true;
      const videoElement = document.getElementById('player');
      if (videoElement) {
        // Video element found, initializing player
        setTimeout(() => initializePlayer(), 100); // Small delay to ensure element is fully rendered
      } else {
        // Video element not found yet, will try again next update
        videoElementChecked = false;
      }
    }
  });

  // Reactive statement to re-initialize player if videoUrl changes
  $: if (videoUrl && !playerInitialized && !isLoading) {
    // Video URL available but no player, scheduling initialization
    setTimeout(() => {
      if (!playerInitialized) {
        initializePlayer();
      }
    }, 200);
  }
</script>

<svelte:head>
  <title>{file?.filename || 'Loading File...'}</title>
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
      <button 
        on:click={() => fetchFileDetails()}
        title="Retry loading the file details"
      >Try Again</button>
    </div>
  {:else if file}
    <div class="file-header">
      <FileHeader {file} />
      
      
      <MetadataDisplay 
        {file} 
        bind:showMetadata 
      />
    </div>

    <div class="main-content-grid">
      <!-- Left column: Video player, tags, analytics, and comments -->
      <section class="video-column">
        <div class="video-header">
          <h4>{file?.content_type?.startsWith('audio/') ? 'Audio' : 'Video'}</h4>
          <!-- AI Summary Buttons - right aligned above video -->
          {#if file?.summary || file?.summary_opensearch_id}
            <button 
              class="view-summary-btn"
              on:click={handleShowSummary}
              title="View AI-generated summary in BLUF format"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" class="ai-icon">
                <path d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456zM16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423L16.5 15.75l.394 1.183a2.25 2.25 0 001.423 1.423L19.5 18.75l-1.183.394a2.25 2.25 0 00-1.423 1.423z"/>
              </svg>
              View Summary
            </button>
          {:else if summaryGenerating || generatingSummary}
            <!-- Show generating state even when no summary exists yet -->
            <button 
              class="generate-summary-btn"
              disabled
              title="AI summary is being generated..."
            >
              <div class="spinner-small"></div>
              <span>AI Summary</span>
            </button>
          {:else if file?.status === 'completed'}
            <button 
              class="generate-summary-btn"
              on:click={handleGenerateSummary}
              disabled={generatingSummary || summaryGenerating || !llmAvailable}
              title={!llmAvailable ? 'AI summary features are not available. Configure an LLM provider in Settings.' : 
                     (generatingSummary || summaryGenerating) ? 'AI summary is being generated...' : 
                     'Generate AI-powered summary with key insights and action items'}
            >
              {#if generatingSummary || summaryGenerating}
                <div class="spinner-small"></div>
                <span>AI Summary</span>
              {:else}
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" class="ai-icon">
                  <path d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456zM16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423L16.5 15.75l.394 1.183a2.25 2.25 0 001.423 1.423L19.5 18.75l-1.183.394a2.25 2.25 0 00-1.423 1.423z"/>
                </svg>
                Generate AI Summary
              {/if}
            </button>
          {/if}
        </div>
        
        <VideoPlayer 
          {videoUrl} 
          {file} 
          {isPlayerBuffering} 
          {loadProgress} 
          {errorMessage}
          on:retry={handleVideoRetry}
        />

        <!-- Error Messages -->
        {#if summaryError}
          <div class="summary-error-container">
            <div class="error-message">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" class="error-icon">
                <path d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"/>
              </svg>
              <span>{summaryError}</span>
            </div>
            <button 
              class="dismiss-error-btn" 
              on:click={() => summaryError = ''}
              title="Dismiss error"
            >
              ✕
            </button>
          </div>
        {/if}
        
        <!-- Waveform visualization -->
        {#if file && file.id && (file.content_type?.startsWith('audio/') || file.content_type?.startsWith('video/')) && file.status === 'completed'}
          <div class="waveform-section">
            <WaveformPlayer
              fileId={file.id}
              duration={file.duration_seconds || file.duration || 0}
              {currentTime}
              height={80}
              on:seek={handleWaveformSeek}
            />
          </div>
        {/if}
        
        <TagsSection 
          {file} 
          bind:isTagsExpanded 
          on:tagsUpdated={handleTagsUpdated}
        />
        
        <CollectionsSection 
          bind:collections 
          fileId={file?.id}
          bind:isExpanded={isCollectionsExpanded}
          on:collectionRemoved={handleCollectionRemoved}
        />

        <AnalyticsSection 
          {file} 
          bind:isAnalyticsExpanded 
          {speakerList}
        />

        <div class="comments-section">
          <h4 class="comments-heading">Comments & Discussion</h4>
          <div class="comments-section-wrapper">
            <CommentSection 
              fileId={file?.id ? String(file.id) : ''} 
              {currentTime} 
              on:seekTo={handleSeekTo}
            />
          </div>
        </div>
      </section>
      
      <!-- Right column: Transcript -->
      {#if file && file.transcript_segments}
        <section class="transcript-column">
          <TranscriptDisplay 
          {file}
          {currentTime}
          {isEditingTranscript}
          {editedTranscript}
          {savingTranscript}
          {transcriptError}
          {editingSegmentId}
          bind:editingSegmentText
          {isEditingSpeakers}
          {speakerList}
          {reprocessing}
          on:segmentClick={handleSegmentClick}
          on:editSegment={handleEditSegment}
          on:saveSegment={handleSaveSegment}
          on:cancelEditSegment={handleCancelEditSegment}
          on:saveTranscript={handleSaveTranscript}
          on:exportTranscript={handleExportTranscript}
          on:saveSpeakerNames={handleSaveSpeakerNames}
          on:speakerUpdate={handleSpeakerUpdate}
          on:reprocess={handleReprocess}
          on:seekToPlayhead={handleSeekTo}
        />
        </section>
      {:else}
        <section class="transcript-column">
          <div class="transcript-header">
            <h4>Transcript</h4>
            <div class="reprocess-button-wrapper">
              <ReprocessButton {file} {reprocessing} on:reprocess={handleReprocess} />
            </div>
          </div>
          <div class="no-transcript">
            <p>No transcript available for this file.</p>
          </div>
        </section>
      {/if}
    </div>

  {:else}
    <div class="no-file-container">
      <p>File data could not be loaded or does not exist.</p>
    </div>
  {/if}
</div>

<!-- Export Confirmation Modal -->
<ConfirmationModal
  bind:isOpen={showExportConfirmation}
  title="Include Comments in Export?"
  message="Would you like to include user comments in the exported transcript? Comments will be inserted at their respective timestamps."
  confirmText="Include Comments"
  cancelText="Export Without Comments"
  on:confirm={handleExportConfirm}
  on:cancel={handleExportCancel}
  on:close={handleExportModalClose}
/>

<!-- Summary Modal -->
{#if file?.id}
  <SummaryModal
    bind:isOpen={showSummaryModal}
    fileId={file.id}
    fileName={file?.filename || 'Unknown File'}
    on:close={() => showSummaryModal = false}
    on:reprocessSummary={async (event) => {
      // 1. Close modal immediately
      showSummaryModal = false;
      
      // 2. Update button to show spinner state
      summaryGenerating = true;
      summaryError = '';
      
      // 3. Clear the summary from file object to trigger "generating" button state
      if (file) {
        file.summary = null;
        file.summary_opensearch_id = null;
        file = { ...file }; // Trigger reactivity
      }
      
      // 4. Trigger the API call for reprocessing
      try {
        const response = await axiosInstance.post(`/api/files/${file.id}/summarize`, {
          force_regenerate: true
        });
        
        // WebSocket will handle the rest of the status updates
        console.log('Reprocess summary started successfully');
      } catch (error) {
        console.error('Failed to start reprocess:', error);
        summaryError = 'Failed to start summary reprocessing';
        summaryGenerating = false;
      }
    }}
  />
{/if}


<style>
  .file-detail-page {
    padding: 2rem;
    max-width: 1200px;
    margin: 0 auto;
    font-family: var(--font-family-sans);
    color: var(--text-color);
  }

  .loading-container, 
  .error-container, 
  .no-file-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 50vh;
    text-align: center;
  }

  .spinner {
    border: 3px solid rgba(0, 0, 0, 0.1);
    border-top: 3px solid var(--primary-color);
    border-radius: 50%;
    width: 40px;
    height: 40px;
    animation: spin 1s linear infinite;
    margin-bottom: 1rem;
  }

  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }

  .error-message {
    color: var(--error-color);
    margin-bottom: 1rem;
  }

  .error-container button {
    background: var(--primary-color);
    color: white;
    border: none;
    padding: 10px 20px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 14px;
    font-weight: 500;
  }

  .error-container button:hover {
    background: var(--primary-hover);
  }
  
  .reprocess-button-wrapper {
    display: inline-block;
  }
  
  .transcript-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
  }

  .file-header {
    margin-bottom: 24px;
  }


  .main-content-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 32px;
    align-items: start;
  }

  .video-column {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .video-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
  }

  .video-column h4 {
    margin: 0;
    font-size: 18px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .transcript-column {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .view-summary-btn {
    background-color: var(--primary-color, #3b82f6);
    color: white;
    border: none;
    border-radius: 6px;
    padding: 0.4rem 0.75rem;
    font-size: 0.8rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }

  .view-summary-btn:hover {
    background-color: var(--primary-color-dark, #2563eb);
    transform: translateY(-1px);
  }

  .view-summary-btn .ai-icon {
    flex-shrink: 0;
    opacity: 0.9;
  }

  .generate-summary-btn {
    background-color: var(--primary-color, #3b82f6);
    color: white;
    border: none;
    border-radius: 6px;
    padding: 0.5rem 1rem;
    font-size: 0.9rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .generate-summary-btn:hover:not(:disabled) {
    background-color: var(--primary-color-dark, #2563eb);
    transform: translateY(-1px);
  }

  .generate-summary-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }


  .status-text {
    white-space: nowrap;
  }

  .generate-summary-btn.checking {
    background-color: var(--warning-color, #f59e0b);
    opacity: 0.8;
  }

  .generate-summary-btn.unavailable {
    background-color: var(--error-color, #ef4444);
    color: white;
  }

  .generate-summary-btn.unavailable:hover {
    background-color: var(--error-color-dark, #dc2626);
  }

  .spinner-small {
    border: 2px solid rgba(255, 255, 255, 0.3);
    border-top: 2px solid white;
    border-radius: 50%;
    width: 14px;
    height: 14px;
    animation: spin 1s linear infinite;
    flex-shrink: 0;
  }

  .warning-icon {
    flex-shrink: 0;
    margin-right: 0.3rem;
    opacity: 0.9;
  }

  .summary-error-container {
    background-color: var(--error-bg, #fef2f2);
    border: 1px solid var(--error-border, #fecaca);
    border-radius: 8px;
    padding: 1rem;
    margin: 0.5rem 0;
    position: relative;
  }

  .error-message {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: var(--error-color, #dc2626);
    font-weight: 500;
    margin-bottom: 0.5rem;
  }

  .error-icon {
    flex-shrink: 0;
  }


  .dismiss-error-btn {
    position: absolute;
    top: 0.5rem;
    right: 0.5rem;
    background: none;
    border: none;
    font-size: 1.2rem;
    color: var(--text-secondary);
    cursor: pointer;
    padding: 0.25rem;
    border-radius: 4px;
    line-height: 1;
  }

  .dismiss-error-btn:hover {
    background-color: rgba(0, 0, 0, 0.05);
    color: var(--text-primary);
  }


  .waveform-section {
    margin-top: 6px;
    width: 100%;
  }

  .comments-section {
    margin-top: 20px;
  }

  .comments-heading {
    margin: 0 0 16px 0;
    font-size: 16px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .comments-section-wrapper {
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 20px;
  }

  .ai-summary-section {
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 20px;
  }

  .summary-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .summary-header h4 {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
    color: var(--text-primary);
  }


  @media (max-width: 1024px) {
    .main-content-grid {
      grid-template-columns: 1fr;
      gap: 24px;
    }
  }

  @media (max-width: 768px) {
    .file-detail-page {
      padding: 1rem;
    }
    
    .main-content-grid {
      gap: 20px;
    }
  }

  /* Transcript segment highlighting styles */
  :global(.transcript-segment.active-segment .segment-content) {
    background-color: rgba(59, 130, 246, 0.12);
    border: 1px solid rgba(59, 130, 246, 0.3);
    box-shadow: 0 1px 3px rgba(59, 130, 246, 0.2);
  }

  :global(.transcript-segment.active-segment .segment-content:hover) {
    background-color: rgba(59, 130, 246, 0.16);
    border-color: rgba(59, 130, 246, 0.4);
  }

  /* Player controls flash styling */
  :global(.plyr--show-controls .plyr__controls) {
    opacity: 1 !important;
    transform: translateY(0) !important;
  }

</style>