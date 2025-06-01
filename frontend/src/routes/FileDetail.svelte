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
  import MetadataDisplay from '$components/MetadataDisplay.svelte';
  import AnalyticsSection from '$components/AnalyticsSection.svelte';
  import TranscriptDisplay from '$components/TranscriptDisplay.svelte';
  import FileHeader from '$components/FileHeader.svelte';
  import TagsSection from '$components/TagsSection.svelte';
  import CommentSection from '$components/CommentSection.svelte';
  import CollectionsSection from '$components/CollectionsSection.svelte';
  
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

  // Reactive store for file updates
  const reactiveFile = writable(null);

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
        speakerList = response.data
          .map((speaker: any) => ({
            id: speaker.id,
            name: speaker.name,
            display_name: speaker.display_name || speaker.name,
            uuid: speaker.uuid,
            verified: speaker.verified
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
    videoUrl = `${apiBaseUrl}/api/files/${fileId}/simple-video`;
    
    // Ensure URL has proper formatting
    if (videoUrl && !videoUrl.startsWith('/') && !videoUrl.startsWith('http')) {
      videoUrl = '/' + videoUrl;
    }
    
    // Reset video element check flag to prompt afterUpdate to try initialization
    videoElementChecked = false;
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

      // Initialize Plyr
      player = new Plyr(videoElement, {
        controls: ['play-large', 'play', 'progress', 'current-time', 'duration', 'mute', 'volume', 'settings', 'fullscreen'],
        settings: ['quality', 'speed'],
        quality: { default: 720, options: [1080, 720, 480, 360] },
        speed: { selected: 1, options: [0.5, 0.75, 1, 1.25, 1.5, 2] },
        ratio: '16:9',
        fullscreen: { enabled: true, fallback: true, iosNative: true }
      });

      // Set up event listeners
      player.on('ready', () => {
        playerInitialized = true;
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
    
    // Prompt user to include comments
    const includeComments = confirm('Would you like to include comments in the exported transcript?');
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
        
        // Speaker names updated locally only (database update failed)
      }
    }
  }

  function handleSeekTo(event: any) {
    const time = event.detail.time || event.detail;
    seekToTime(time);
  }

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
      fetchFileDetails();
    } else {
      errorMessage = 'Invalid file ID';
      isLoading = false;
    }

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
          if (String(latestNotification.data?.file_id) === String(fileId) && 
              latestNotification.type === 'transcription_status') {
            
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
        }
      }
    });
  });

  onDestroy(() => {
    if (player) {
      try {
        player.destroy();
        player = null;
        playerInitialized = false;
      } catch (err) {
        console.error('Error destroying player:', err);
      }
    }
    
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
        <h4>Video</h4>
        <VideoPlayer 
          {videoUrl} 
          {file} 
          {isPlayerBuffering} 
          {loadProgress} 
          {errorMessage}
          on:retry={handleVideoRetry}
        />
        
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
      
      <!-- Transcript section - right side -->
      {#if file && file.transcript_segments}
        <TranscriptDisplay 
          {file}
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
        />
      {:else}
        <section class="transcript-column">
          <h4>Transcript</h4>
          <div class="no-transcript">
            <p>No transcript available for this file.</p>
            <p>Debug: file={!!file}, transcript_segments={!!file?.transcript_segments}</p>
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
    gap: 20px;
  }

  .video-column h4 {
    margin: 0 0 16px 0;
    font-size: 18px;
    font-weight: 600;
    color: var(--text-primary);
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