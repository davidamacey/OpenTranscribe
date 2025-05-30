<script lang="ts">
  import { onMount, onDestroy, afterUpdate } from 'svelte';
  import { writable } from 'svelte/store';
  import Plyr from 'plyr';
  import 'plyr/dist/plyr.css';
  import axiosInstance from '$lib/axios';
  import { formatTimestampWithMillis } from '$lib/utils/formatting';
  
  // Import new components
  import VideoPlayer from '$components/VideoPlayer.svelte';
  import MetadataDisplay from '$components/MetadataDisplay.svelte';
  import AnalyticsSection from '$components/AnalyticsSection.svelte';
  import TranscriptDisplay from '$components/TranscriptDisplay.svelte';
  import FileHeader from '$components/FileHeader.svelte';
  import TagsSection from '$components/TagsSection.svelte';
  import CommentSection from '$components/CommentSection.svelte';

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

  // UI state
  let showMetadata = false;
  let isTagsExpanded = false;
  let isAnalyticsExpanded = false;
  let isEditingTranscript = false;
  let editedTranscript = '';
  let savingTranscript = false;
  let transcriptError = '';
  let editingSegmentId: string | number | null = null;
  let editingSegmentText = '';
  let isEditingSpeakers = false;
  let speakerList: any[] = [];

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
        reactiveFile.set(file);

        // Set up video URL using the simple-video endpoint
        setupVideoUrl(targetFileId);

        // Set up video URL
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
        
        transcriptData.forEach((segment: any) => {
          // Use display name if available, otherwise fall back to original speaker label
          const speaker = segment.speaker?.display_name || segment.speaker_label || segment.speaker?.name || 'Unknown';
          const words = segment.text.split(/\s+/).filter(Boolean).length;
          const segmentDuration = (segment.end_time || 0) - (segment.start_time || 0);
          
          speakerCounts[speaker] = (speakerCounts[speaker] || 0) + words;
          speakerTimes[speaker] = (speakerTimes[speaker] || 0) + segmentDuration;
          totalWords += words;
          totalDuration += segmentDuration;
        });
        
        file.analytics = {
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
        speakerList = response.data.map((speaker: any) => ({
          id: speaker.id,
          name: speaker.name,
          display_name: speaker.display_name || speaker.name,
          uuid: speaker.uuid,
          verified: speaker.verified
        }));
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
          speakerList = Array.from(speakers.values());
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
        speakerList = Array.from(speakers.values());
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
    if (player) {
      player.currentTime = startTime;
      
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

  // Handle speaker name updates
  async function handleSpeakerUpdate(event: CustomEvent) {
    const { speakerId, newName } = event.detail;
    
    // Update the speaker in the speakerList
    speakerList = speakerList.map(speaker => {
      if (speaker.id === speakerId || speaker.uuid === speakerId) {
        return { ...speaker, display_name: newName, name: newName };
      }
      return speaker;
    });
    
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
          content = transcriptData.map((seg: any) => 
            `[${formatSimpleTimestamp(seg.start_time)}] ${getSpeakerDisplayName(seg)}: ${seg.text}`
          ).join('\n\n');
          break;
        case 'json':
          // Include updated speaker display names in JSON export
          const enrichedData = transcriptData.map((seg: any) => ({
            ...seg,
            speaker_display_name: getSpeakerDisplayName(seg)
          }));
          content = JSON.stringify(enrichedData, null, 2);
          break;
        case 'csv':
          content = 'Start Time,End Time,Speaker,Text\n' + transcriptData.map((seg: any) => 
            `${seg.start_time},${seg.end_time},"${getSpeakerDisplayName(seg)}","${seg.text.replace(/"/g, '""')}"`
          ).join('\n');
          break;
        case 'srt':
          content = transcriptData.map((seg: any, index: number) => {
            const startTime = formatSrtTimestamp(seg.start_time || seg.start || 0);
            const endTime = formatSrtTimestamp(seg.end_time || seg.end || 0);
            const speaker = getSpeakerDisplayName(seg);
            const text = `${speaker}: ${seg.text}`;
            return `${index + 1}\n${startTime} --> ${endTime}\n${text}\n`;
          }).join('\n');
          break;
        case 'vtt':
          content = 'WEBVTT\n\n' + transcriptData.map((seg: any) => {
            const startTime = formatVttTimestamp(seg.start_time || seg.start || 0);
            const endTime = formatVttTimestamp(seg.end_time || seg.end || 0);
            const speaker = getSpeakerDisplayName(seg);
            const text = `${speaker}: ${seg.text}`;
            return `${startTime} --> ${endTime}\n${text}\n`;
          }).join('\n');
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

  async function handleSaveSpeakerNames() {
    if (!speakerList || speakerList.length === 0) return;
    
    try {
      // Update speakers in the backend
      const updatePromises = speakerList.map(async (speaker: any) => {
        if (speaker.id) {
          // Update existing speaker
          return axiosInstance.put(`/api/speakers/${speaker.id}`, {
            display_name: speaker.display_name,
            name: speaker.name
          });
        }
        return null;
      });
      
      await Promise.all(updatePromises.filter(p => p !== null));
      
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
        
        // Regenerate analytics with updated speaker names
        if (file?.id) {
          await fetchAnalytics(file.id.toString());
        }
        
        // Speaker names updated locally only (database update failed)
      }
    }
  }

  function handleSeekTo(event: any) {
    const time = event.detail.time;
    if (player) {
      player.currentTime = time;
    }
  }

  function handleTagsUpdated(event: any) {
    if (file) {
      file.tags = event.detail.tags;
      reactiveFile.set(file);
    }
  }

  function handleVideoRetry() {
    fetchFileDetails();
  }

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
  });

  onDestroy(() => {
    if (player) {
      try {
        player.destroy();
      } catch (err) {
        console.error('Error destroying player:', err);
      }
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
          on:segmentClick={handleSegmentClick}
          on:editSegment={handleEditSegment}
          on:saveSegment={handleSaveSegment}
          on:cancelEditSegment={handleCancelEditSegment}
          on:saveTranscript={handleSaveTranscript}
          on:exportTranscript={handleExportTranscript}
          on:saveSpeakerNames={handleSaveSpeakerNames}
          on:speakerUpdate={handleSpeakerUpdate}
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