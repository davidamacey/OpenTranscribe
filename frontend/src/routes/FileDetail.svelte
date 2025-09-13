<script lang="ts">
  import { onMount, onDestroy, afterUpdate } from 'svelte';
  import { writable } from 'svelte/store';
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
  import { toastStore } from '$stores/toast';
  import ConfirmationModal from '$components/ConfirmationModal.svelte';
  import SummaryModal from '$components/SummaryModal.svelte';
  import TranscriptModal from '$components/TranscriptModal.svelte';
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
  let videoPlayerComponent: any = null;
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
  let savingSpeakers = false;
  let transcriptError = '';
  let editingSegmentId: string | number | null = null;
  let editingSegmentText = '';
  let isEditingSpeakers = false;
  let speakerList: any[] = [];
  let reprocessing = false;
  let summaryData: any = null;
  let showSummaryModal = false;
  let showTranscriptModal = false;
  let generatingSummary = false;
  let summaryError = '';
  let summaryGenerating = false; // WebSocket-driven summary generation status
  let currentProcessingStep = ''; // Current processing step from WebSocket notifications
  let lastProcessedNotificationState = ''; // Track processed notification state globally
  // LLM availability for summary functionality
  $: llmAvailable = $isLLMAvailable;
  
  

  // Confirmation modal state
  let showExportConfirmation = false;
  let pendingExportFormat = '';

  // Reactive store for file updates
  const reactiveFile = writable(null);
  

  /**
   * Fetches file details from the API
   */
  /**
   * Fetch transcript and related data to update the page without overwriting file state
   */
  async function fetchTranscriptData(): Promise<void> {
    if (!fileId) {
      console.error('FileDetail: No file ID provided to fetchTranscriptData');
      return;
    }

    try {
      const response = await axiosInstance.get(`/api/files/${fileId}`);
      
      if (response.data && typeof response.data === 'object' && file) {
        // Update all transcript and processing-related fields while preserving UI state flags
        file.transcript_segments = response.data.transcript_segments || [];
        file.speakers = response.data.speakers || [];
        file.waveform_data = response.data.waveform_data;
        file.duration = response.data.duration;
        file.duration_seconds = response.data.duration_seconds;
        
        // Update metadata and processing info
        file.processed_at = response.data.processed_at;
        file.analytics = response.data.analytics;
        
        // Update collections if they changed
        collections = response.data.collections || [];
        
        // Update file object
        file = { ...file };
        reactiveFile.set(file);
        
        // Process the new transcript data
        processTranscriptData();
        
        // Fetch analytics separately to get the latest data
        await fetchAnalytics(fileId);
        
      }
    } catch (error) {
      console.error('Error fetching transcript data:', error);
    }
  }

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
            cross_video_matches: (speaker.cross_video_matches || []).filter((match) => parseFloat(match.confidence) >= 0.50), // Show high and medium confidence matches (≥50%)
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
   * Refresh subtitle track when transcript changes (debounced)
   */

  /**
   * Initialize the video player with enhanced streaming capabilities
   */
  function initializePlayer() {
    if (playerInitialized || !videoUrl) {
      return;
    }
    
    const mediaElement = document.querySelector('#player') as HTMLMediaElement;
    
    if (!mediaElement) {
      return;
    }

    // Mark as initialized - all player initialization is now handled by VideoPlayer component
    playerInitialized = true;
    console.log('Media player initialization is now handled by VideoPlayer component');
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
            
            
            // Clear cached processed videos so downloads will use updated transcript
            try {
              await axiosInstance.delete(`/api/files/${file.id}/cache`);
            } catch (error) {
              console.warn('Could not clear video cache:', error);
            }
          }
        }
        
        editingSegmentId = null;
        editingSegmentText = '';
        transcriptError = '';

        // Update subtitles in the video player
        if (videoPlayerComponent && videoPlayerComponent.updateSubtitles) {
          try {
            await videoPlayerComponent.updateSubtitles();
          } catch (error) {
            console.warn('Failed to update subtitles after segment edit:', error);
          }
        }
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
    
    savingSpeakers = true;
    
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
      
      
      // Clear cached processed videos so downloads will use updated speaker names
      try {
        await axiosInstance.delete(`/api/files/${file.id}/cache`);
        // Note: No user notification needed - this is automatic background cleanup
      } catch (error) {
        console.warn('Could not clear video cache:', error);
      }
      
      // Speaker names saved to database and updated locally
      toastStore.success('Speaker names saved successfully!');
    } catch (error) {
      console.error('Error saving speaker names:', error);
      toastStore.error('Failed to save speaker names. Changes applied locally only.');
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
        
        
        // Clear cached processed videos so downloads will use updated speaker names (fallback)
        try {
          await axiosInstance.delete(`/api/files/${file.id}/cache`);
        } catch (error) {
          console.warn('Could not clear video cache (fallback):', error);
        }
        
        // Speaker names updated locally only (database update failed)
      }
    } finally {
      savingSpeakers = false;
    }
  }

  function handleSeekTo(event: any) {
    const time = event.detail.time || event.detail;
    seekToTime(time);
  }


  // Speaker verification event handlers

  function seekToTime(time: number) {
    // Add 0.5 second padding before the target time for better context
    const paddedTime = Math.max(0, time - 0.5);

    // Use VideoPlayer component's seek function for all media types
    if (videoPlayerComponent && videoPlayerComponent.seekToTime) {
      videoPlayerComponent.seekToTime(paddedTime);
    } else {
      console.warn('VideoPlayer component not available for seeking');
    }
  }

  function handleTagsUpdated(event: any) {
    if (file) {
      file.tags = event.detail.tags;
      reactiveFile.set(file);
    }
  }

  function handleCollectionsUpdated(event: any) {
    const { collections: updatedCollections } = event.detail;
    
    // Update collections array
    collections = updatedCollections;
    
    // Update file object if it exists
    if (file) {
      file.collections = updatedCollections;
      file = { ...file }; // Trigger reactivity
      reactiveFile.set(file);
    }
  }

  function handleVideoRetry() {
    fetchFileDetails();
  }

  // Audio player event handlers for custom player
  function handleTimeUpdate(event: CustomEvent) {
    currentTime = event.detail.currentTime;
    duration = event.detail.duration;
    updateCurrentSegment(currentTime);
  }

  function handlePlay(event: CustomEvent) {
    // Handle play event if needed
  }

  function handlePause(event: CustomEvent) {
    // Handle pause event if needed
  }

  function handleLoadedMetadata(event: CustomEvent) {
    duration = event.detail.duration;
  }

  function handleWaveformSeek(event: CustomEvent) {
    const seekTime = event.detail.time;
    seekToTime(seekTime);
  }

  async function handleReprocess(event: CustomEvent) {
    const { fileId } = event.detail;
    
    
    try {
      reprocessing = true;
      
      // Reset notification processing state for reprocessing
      lastProcessedNotificationState = '';
      
      // Optimistically set file to processing state for immediate UI feedback
      if (file) {
        file.status = 'processing';
        file.progress = 0;
        // Clear transcript data to show placeholder state during reprocessing
        file.transcript_segments = [];
        file.summary = null;
        file.summary_opensearch_id = null;
        
        // Set summary generating state if LLM is available (reprocessing triggers auto-summary)
        if (llmAvailable) {
          summaryGenerating = true;
          generatingSummary = true;
          summaryError = '';
        }
        
        file = file; // Trigger reactivity
      }
      
      await axiosInstance.post(`/api/files/${fileId}/reprocess`);
      
      // Don't immediately fetch - let WebSocket notifications handle updates
      // The file is now pending/processing and notifications will update the UI
      
    } catch (error) {
      console.error('❌ Error starting reprocess:', error);
      toastStore.error('Failed to start reprocessing. Please try again.');
      
      // Revert optimistic update on error
      if (file) {
        await fetchFileDetails(fileId);
      }
    } finally {
      reprocessing = false;
    }
  }

  async function handleReprocessHeader() {
    if (!file?.id) return;
    
    try {
      reprocessing = true;
      
      // Reset notification processing state for reprocessing
      lastProcessedNotificationState = '';
      
      // Optimistically set file to processing state for immediate UI feedback
      file.status = 'processing';
      file.progress = 0;
      // Clear transcript data to show placeholder state during reprocessing
      file.transcript_segments = [];
      file.summary = null;
      file.summary_opensearch_id = null;
      
      // Set summary generating state if LLM is available (reprocessing triggers auto-summary)
      if (llmAvailable) {
        summaryGenerating = true;
        generatingSummary = true;
        summaryError = '';
      }
      
      file = file; // Trigger reactivity
      
      await axiosInstance.post(`/api/files/${file.id}/reprocess`);
      
      // Don't immediately fetch - let WebSocket notifications handle updates
      toastStore.success('Reprocessing started successfully');
      
    } catch (error) {
      console.error('❌ Error starting reprocess (header):', error);
      toastStore.error('Failed to start reprocessing. Please try again.');
      
      // Revert optimistic update on error
      await fetchFileDetails(file.id);
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
      return;
    }
    
    try {
      generatingSummary = true;
      summaryError = '';
      
      const response = await axiosInstance.post(`/api/files/${file.id}/summarize`);
      
      // Don't refresh page - let WebSocket notifications handle status updates
      // This preserves user's editing state
      
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
    // Use the correct backend API base URL (port 5174, not frontend port 5173)
    apiBaseUrl = window.location.protocol + '//' + window.location.hostname + ':5174';
    
    if (id) {
      fileId = id;
    } else {
      console.error('FileDetail: No id parameter provided');
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

    // Subscribe to WebSocket notifications for real-time updates
    wsUnsubscribe = websocketStore.subscribe(($ws) => {
      
      
      if ($ws.notifications.length > 0) {
        
        // Find the most recently updated notification for the current file
        const currentFileNotifications = $ws.notifications.filter(n => {
          const notificationFileId = String(n.data?.file_id || n.fileId || '');
          const currentFileId = String(fileId);
          return notificationFileId === currentFileId;
        });
        
        if (currentFileNotifications.length === 0) {
          return;
        }
        
        // Sort by last update time (most recent first)
        currentFileNotifications.sort((a, b) => {
          const aTime = a.lastUpdated || a.timestamp;
          const bTime = b.lastUpdated || b.timestamp;
          return new Date(bTime).getTime() - new Date(aTime).getTime();
        });
        
        const latestNotification = currentFileNotifications[0];
        
        
        // Create a unique state signature to detect content changes, not just ID changes
        const notificationState = `${latestNotification.id}_${latestNotification.status}_${latestNotification.progress?.percentage}_${latestNotification.currentStep}_${latestNotification.timestamp}`;
        
        // Only process if the notification content has changed (not just new ID)
        if (notificationState !== lastProcessedNotificationState) {
          lastProcessedNotificationState = notificationState;
          
          // Check if this notification is for our current file
          // Skip if fileId is not set yet (component still initializing)
          if (!fileId) {
            return;
          }
          
          // Convert both to strings for comparison since notification sends file_id as string
          const notificationFileId = String(latestNotification.data?.file_id);
          const currentFileId = String(fileId);
          
          
          if (notificationFileId === currentFileId && notificationFileId !== 'undefined' && currentFileId !== 'undefined') {
            
            // Handle transcription status updates
            if (latestNotification.type === 'transcription_status') {
              
              // Get status from notification (progressive notifications set it at root level)
              const notificationStatus = latestNotification.status || latestNotification.data?.status;
              const notificationProgress = latestNotification.progress?.percentage || latestNotification.data?.progress;
              
              
              // Update progress in real-time for processing updates
              if (notificationStatus === 'processing' && notificationProgress !== undefined) {
                if (file) {
                  file.progress = notificationProgress;
                  file.status = 'processing';
                  // Update the current processing step from the progressive notification
                  currentProcessingStep = latestNotification.currentStep || latestNotification.message || latestNotification.data?.message || 'Processing...';
                  file = { ...file }; // Trigger reactivity
                  reactiveFile.set(file);
                  
                }
              } else if (notificationStatus === 'completed' || notificationStatus === 'success' || notificationStatus === 'complete' || notificationStatus === 'finished') {
                // Transcription completed - show completion and refresh
                if (file) {
                  file.progress = 100;
                  file.status = 'completed';
                  currentProcessingStep = 'Processing complete!';
                  
                  // If LLM is available, always show AI summary spinner after transcription completion
                  // This handles the automatic summarization that triggers after transcription
                  if (llmAvailable) {
                    summaryGenerating = true;
                    generatingSummary = true;
                    summaryError = '';
                    // Keep reprocessing flag true until summary completes to maintain proper UI state
                  } else {
                    // No LLM available, safe to reset reprocessing flag
                    reprocessing = false;
                  }
                  
                  file = { ...file }; // Trigger reactivity
                  reactiveFile.set(file);
                }
                
                // Clear processing step and refresh transcript data after completion
                setTimeout(async () => {
                  currentProcessingStep = ''; // Clear processing step

                  // Only refresh the transcript data, not the entire file object to preserve spinner state
                  if (file?.id && (file.status === 'completed' || file.status === 'success')) {
                    await fetchTranscriptData();

                    // Refresh subtitles in the video player now that transcript is available
                    if (videoPlayerComponent && videoPlayerComponent.updateSubtitles) {
                      try {
                        await videoPlayerComponent.updateSubtitles();
                      } catch (error) {
                        console.warn('Failed to update subtitles:', error);
                      }
                    }
                  }
                }, 1000);
              } else if (notificationStatus === 'error' || notificationStatus === 'failed') {
                // Error state - refresh immediately
                currentProcessingStep = ''; // Clear processing step
                fetchFileDetails();
              }
            }
            
            // WebSocket notifications for file updates
            
            // Handle summarization status updates  
            if (latestNotification.type === 'summarization_status') {
              // Only process notifications for the current file
              const notificationFileId = String(latestNotification.data?.file_id || '');
              const currentFileId = String(fileId || '');
              
              if (notificationFileId !== currentFileId) {
              } else {
              
              // Get status from notification (progressive notifications set it at root level)
              const status = latestNotification.status || latestNotification.data?.status;
              
              
              if (status === 'queued' || status === 'processing' || status === 'generating') {
                // Summary generation started - show spinner
                summaryGenerating = true;
                generatingSummary = true;
                summaryError = '';
                
              } else if (status === 'completed' || status === 'success' || status === 'complete' || status === 'finished') {
                // Summary completed - stop spinners and update file
                
                summaryGenerating = false;
                generatingSummary = false;
                summaryError = '';
                
                // Reset reprocessing flag when summary completes (final step of reprocessing)
                reprocessing = false;
                
                if (file) {
                  // Update summary-related fields from notification data
                  const summaryContent = latestNotification.data?.summary;
                  const summaryId = latestNotification.data?.summary_opensearch_id;
                  
                  
                  if (summaryContent) {
                    file.summary = summaryContent;
                  }
                  if (summaryId) {
                    file.summary_opensearch_id = summaryId;
                  }
                  
                  
                  // Force reactivity update
                  file = { ...file };
                  reactiveFile.set(file);
                  
                }
              } else if (status === 'failed' || status === 'error') {
                // Summary failed - stop spinners and show error
                summaryGenerating = false;
                generatingSummary = false;
                
                // Get error message from notification
                const errorMessage = latestNotification.data?.message || latestNotification.message || 'Failed to generate summary';
                const isLLMConfigError = errorMessage.toLowerCase().includes('llm service is not available') || 
                                       errorMessage.toLowerCase().includes('configure an llm provider') ||
                                       errorMessage.toLowerCase().includes('llm provider');
                
                if (!isLLMConfigError) {
                  summaryError = errorMessage;
                }
                
              }
              } // Close the else block for file ID matching
            }
          } else {
          }
        } else {
        }
      } else {
      }
    });
  });

  onDestroy(() => {
    if (player) {
      try {
        // Clean up any subtitle blob URLs before destroying player
        const mediaElement = player.media;
        if (mediaElement) {
          const tracks = Array.from(mediaElement.querySelectorAll('track[kind="subtitles"]')) as HTMLTrackElement[];
          tracks.forEach((track: HTMLTrackElement) => {
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
      <FileHeader {file} {currentProcessingStep} />
      
      
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
          <!-- Action Buttons - right aligned above video -->
          <div class="header-buttons">
            <!-- View Full Transcript Button - LEFT of AI Summary -->
            {#if file && file.transcript_segments && file.transcript_segments.length > 0 && file.status !== 'processing'}
              <button 
                class="view-transcript-btn"
                on:click={() => showTranscriptModal = true}
                title="View full transcript in modal"
              >
                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" class="transcript-icon">
                  <path d="M4 2a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H4zm0 1h8a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/>
                  <path d="M5 5h6v1H5V5zm0 2h6v1H5V7zm0 2h4v1H5V9z"/>
                </svg>
                Transcript
              </button>
            {/if}
          <!-- Debug: Summary button state: hasSummary={!!(file?.summary || file?.summary_opensearch_id)}, summaryGenerating={summaryGenerating}, generatingSummary={generatingSummary}, fileStatus={file?.status} -->
          {#if file?.summary || file?.summary_opensearch_id}
            <button 
              class="view-summary-btn"
              on:click={handleShowSummary}
              title="View AI-generated summary in BLUF format"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" class="ai-icon">
                <path d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456zM16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423L16.5 15.75l.394 1.183a2.25 2.25 0 001.423 1.423L19.5 18.75l-1.183.394a2.25 2.25 0 00-1.423 1.423z"/>
              </svg>
              Summary
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
          <!-- Reprocess Button - icon only with tooltip -->
          {#if file && (file.status === 'error' || file.status === 'completed' || file.status === 'failed')}
            <button 
              class="reprocess-button-header" 
              on:click={handleReprocessHeader}
              disabled={reprocessing}
              title={reprocessing ? 'Reprocessing file with transcription AI...' : 'Reprocess this file with transcription AI'}
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M23 4v6h-6"></path>
                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
              </svg>
              {#if reprocessing}
                <div class="spinner-small"></div>
              {/if}
            </button>
          {/if}
          </div>
        </div>
        
        <VideoPlayer 
          bind:this={videoPlayerComponent}
          {videoUrl} 
          {file} 
          {isPlayerBuffering} 
          {loadProgress} 
          {errorMessage}
          on:retry={handleVideoRetry}
          on:timeupdate={handleTimeUpdate}
          on:play={handlePlay}
          on:pause={handlePause}
          on:loadedmetadata={handleLoadedMetadata}
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
          on:collectionsUpdated={handleCollectionsUpdated}
        />

        <AnalyticsSection 
          {file} 
          bind:isAnalyticsExpanded 
          {speakerList}
        />

        <CommentSection 
          fileId={file?.id ? String(file.id) : ''} 
          {currentTime} 
          on:seekTo={handleSeekTo}
        />
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
          {savingSpeakers}
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
          <div class="no-transcript">
            {#if file?.status === 'processing' || file?.status === 'pending'}
              <div class="processing-placeholder">
                <div class="spinner-large"></div>
                <p>Generating transcript...</p>
                <small>This may take a few minutes depending on the length of your file.</small>
              </div>
            {:else}
              <p>No transcript available for this file.</p>
            {/if}
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
      } catch (error) {
        console.error('Failed to start reprocess:', error);
        summaryError = 'Failed to start summary reprocessing';
        summaryGenerating = false;
      }
    }}
  />
{/if}

<!-- Transcript Modal -->
{#if file?.id}
  <TranscriptModal
    bind:isOpen={showTranscriptModal}
    fileId={file.id}
    fileName={file?.filename || 'Unknown File'}
    transcriptSegments={file?.transcript_segments || []}
    on:close={() => showTranscriptModal = false}
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
  
  
  .transcript-header {
    display: flex;
    align-items: center;
    margin-bottom: 6px;
    width: 100%;
    min-height: 32px;
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
    margin-bottom: 0px;
    min-height: 32px;
  }

  .header-buttons {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .view-transcript-btn {
    background-color: var(--bg-primary);
    color: var(--text-primary);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 0.6rem 1rem;
    font-size: 0.9rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    height: 40px;
    white-space: nowrap;
  }

  .view-transcript-btn:hover {
    background-color: var(--hover-bg);
    border-color: var(--primary-color);
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
  }

  .view-transcript-btn:active {
    transform: scale(0.98);
  }

  .view-transcript-btn .transcript-icon {
    flex-shrink: 0;
    opacity: 0.8;
  }

  .reprocess-button-header {
    background-color: var(--bg-primary);
    color: var(--text-primary);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 0.6rem;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.25rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    width: 40px;
    height: 40px;
  }

  .reprocess-button-header:hover:not(:disabled) {
    background-color: var(--hover-bg);
    border-color: var(--primary-color);
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
  }

  .reprocess-button-header:active {
    transform: scale(0.98);
  }

  .reprocess-button-header:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .reprocess-button-header .spinner-small {
    border: 2px solid rgba(128, 128, 128, 0.3);
    border-top: 2px solid var(--primary-color);
    border-radius: 50%;
    width: 12px;
    height: 12px;
    animation: spin 1s linear infinite;
    flex-shrink: 0;
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
    background-color: var(--bg-primary);
    color: var(--text-primary);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 0.6rem 1rem;
    font-size: 0.9rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    height: 40px;
    white-space: nowrap;
  }

  .view-summary-btn:hover {
    background-color: var(--hover-bg);
    border-color: var(--primary-color);
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
  }
  
  .view-summary-btn:active {
    transform: scale(0.98);
  }

  .view-summary-btn .ai-icon {
    flex-shrink: 0;
    opacity: 0.8;
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
    width: 100%;
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

  /* All Plyr styling is now handled in VideoPlayer.svelte */


</style>