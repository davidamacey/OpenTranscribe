<script lang="ts">
  import { onMount, onDestroy, afterUpdate } from 'svelte';
  import { writable, get } from 'svelte/store';
  import axiosInstance from '$lib/axios';
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
  import { t } from '$stores/locale';
  import ConfirmationModal from '$components/ConfirmationModal.svelte';
  import SummaryModal from '$components/SummaryModal.svelte';
  import TranscriptModal from '$components/TranscriptModal.svelte';
  import { isLLMAvailable } from '$stores/llmStatus';
  import { transcriptStore, processedTranscriptSegments } from '$stores/transcriptStore';
  import { getAISuggestions, type TagSuggestion, type CollectionSuggestion } from '$lib/api/suggestions';
  import { getAppBaseUrl, getVideoUrl } from '$lib/utils/url';
  import {
    getTranscriptionSettings,
    getTranscriptionSystemDefaults,
    type TranscriptionSettings,
    type TranscriptionSystemDefaults,
    DEFAULT_TRANSCRIPTION_SETTINGS
  } from '$lib/api/transcriptionSettings';

  // No need for a global commentsForExport variable - we'll fetch when needed

  // Props - SvelteKit passes data from +page.ts
  export let data;
  $: id = data.id;

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
  let loadingVoiceSuggestions = false; // Loading state for voice suggestions during OpenSearch refresh
  let editingSegmentId: string | number | null = null;
  let editingSegmentText = '';
  let isEditingSpeakers = false;
  let speakerList: any[] = [];
  let originalSpeakerNames: Map<string, string> = new Map(); // Track original names for change detection
  let speakerNamesChanged = false; // Track if any speaker names have been modified
  let reprocessing = false;
  let showReprocessSettings = false;
  let reprocessDropdownMode: 'settings' | 'confirmation' = 'settings';
  let reprocessFadeTimeout: ReturnType<typeof setTimeout> | null = null;
  let reprocessMinSpeakers: number | null = null;
  let reprocessMaxSpeakers: number | null = null;
  let reprocessNumSpeakers: number | null = null;
  let reprocessContainerRef: HTMLDivElement;

  // User transcription preferences
  let transcriptionSettings: TranscriptionSettings | null = null;
  let transcriptionSystemDefaults: TranscriptionSystemDefaults | null = null;
  let transcriptionPrefsLoaded = false;
  let summaryData: any = null;
  let showSummaryModal = false;
  let showTranscriptModal = false;
  let generatingSummary = false;
  let summaryGenerating = false; // WebSocket-driven summary generation status
  let currentProcessingStep = ''; // Current processing step from WebSocket notifications
  let lastProcessedNotificationState = ''; // Track processed notification state globally

  // Transcript pagination state
  let totalSegments = 0;
  let segmentLimit = 500;
  let segmentOffset = 0;
  let loadingMoreSegments = false;
  $: hasMoreSegments = totalSegments > (file?.transcript_segments?.length || 0);

  // AI Suggestions state
  let aiTagSuggestions: TagSuggestion[] = [];
  let aiCollectionSuggestions: CollectionSuggestion[] = [];

  // LLM availability for summary functionality
  $: llmAvailable = $isLLMAvailable;

  // Detect changes in speaker names - depends on speaker display_name values
  $: speakerNamesChanged = speakerList.length > 0 && speakerList.some(speaker => {
    const originalName = originalSpeakerNames.get(speaker.uuid) || '';
    const currentName = (speaker.display_name || '').trim();
    return originalName !== currentName;
  });

  // Reset spinners when LLM becomes unavailable
  $: if (!llmAvailable && (summaryGenerating || generatingSummary)) {
    summaryGenerating = false;
    generatingSummary = false;
  }




  // Confirmation modal state
  let showExportConfirmation = false;
  let pendingExportFormat = '';

  // Speaker profile confirmation modal state
  let showSpeakerProfileConfirmation = false;
  let pendingSpeakerUpdate = null;
  let profileUpdateMessage = '';
  let profileUpdateTitle = '';

  // Bulk speaker save confirmation state
  let speakerConfirmationQueue = [];
  let currentConfirmationIndex = 0;
  let bulkSaveInProgress = false;
  let bulkSaveDecisions = new Map();

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
      errorMessage = $t('fileDetail.noFileIdProvided');
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

        // Track pagination metadata
        totalSegments = response.data.total_segments || 0;
        segmentLimit = response.data.segment_limit || 500;
        segmentOffset = response.data.segment_offset || 0;

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
      errorMessage = $t('fileDetail.failedToLoadFile');
      isLoading = false;
    }
  }

  /**
   * Load more transcript segments for large transcripts
   */
  async function loadMoreSegments(): Promise<void> {
    if (!fileId || loadingMoreSegments || !hasMoreSegments) return;

    try {
      loadingMoreSegments = true;
      const currentCount = file?.transcript_segments?.length || 0;
      const nextOffset = currentCount;

      const response = await axiosInstance.get(`/api/files/${fileId}`, {
        params: {
          segment_limit: segmentLimit,
          segment_offset: nextOffset
        }
      });

      if (response.data && response.data.transcript_segments) {
        // Append new segments to existing ones
        file.transcript_segments = [
          ...(file.transcript_segments || []),
          ...response.data.transcript_segments
        ];
        file = { ...file }; // Trigger reactivity
        reactiveFile.set(file);

        // Update pagination state
        totalSegments = response.data.total_segments || totalSegments;

        // Update transcript store so TranscriptModal gets the new segments
        if (file?.uuid && file.transcript_segments && speakerList) {
          transcriptStore.loadTranscriptData(file.uuid, file.transcript_segments, speakerList);
        }
      }
    } catch (error) {
      console.error('Error loading more segments:', error);
      toastStore.error($t('fileDetail.failedToLoadMoreSegments'));
    } finally {
      loadingMoreSegments = false;
    }
  }


  /**
   * Load AI suggestions for tags and collections
   *
   * Always loads suggestions if they exist in the database, regardless of current LLM configuration.
   * This ensures users can see and use previously generated suggestions even if LLM is no longer configured.
   */
  async function loadAISuggestions(): Promise<void> {
    if (!fileId) return;

    try {
      const suggestions = await getAISuggestions(fileId);
      // Load suggestions regardless of status or current LLM configuration
      // The UI components will handle display logic based on status
      if (suggestions && suggestions.status !== 'rejected') {
        aiTagSuggestions = suggestions.tags || [];
        aiCollectionSuggestions = suggestions.collections || [];
      }
    } catch (error) {
      console.error('Error loading AI suggestions:', error);
      // Silent fail - suggestions are optional (404 is expected if none exist)
    }
  }

  /**
   * Analytics are provided by the backend - no client-side computation needed
   */
  async function fetchAnalytics(fileId: string) {
    // Analytics are pre-computed by the backend and included in the API response
    // No client-side processing required - just use what the backend provides
  }

  /**
   * Process transcript data from the main file response
   */
  function processTranscriptData() {
    // Use transcript_segments from backend (already sorted by backend)
    let transcriptData = file?.transcript_segments;

    if (!file || !transcriptData || !Array.isArray(transcriptData)) {
      return;
    }

    try {
      // Backend now provides pre-sorted transcript segments - no client-side sorting needed

      // Update the file with sorted data
      file.transcript_segments = transcriptData;

      // Update transcript text for editing
      editedTranscript = transcriptData.map((seg: any) =>
        `${seg.display_timestamp || seg.formatted_timestamp || formatSimpleTimestamp(seg.start_time)} [${seg.speaker_label || seg.speaker?.name || 'Speaker'}]: ${seg.text}`
      ).join('\n');

      // Load speakers and update store after they're loaded
      loadSpeakers();
    } catch (error) {
      console.error('Error processing transcript:', error);
    }
  }

  // Speaker sorting is now handled by the backend

  /**
   * Load cross-media appearances for labeled speakers
   */
  async function loadCrossMediaDataForLabeledSpeakers(): Promise<void> {
    if (!speakerList || speakerList.length === 0) return;

    // Find speakers that need cross-media data (labeled speakers without individual matches)
    const speakersNeedingCrossMedia = speakerList.filter(speaker => speaker.needsCrossMediaCall);

    // Load cross-media data for each labeled speaker
    for (const speaker of speakersNeedingCrossMedia) {
      try {
        const response = await axiosInstance.get(`/api/speakers/${speaker.uuid}/cross-media`);

        // Update the speaker's cross_video_matches with actual file appearances
        speaker.cross_video_matches = response.data || [];

      } catch (error) {
        console.error(`Error loading cross-media data for speaker ${speaker.uuid}:`, error);
        speaker.cross_video_matches = [];
      }
    }


    // Trigger reactivity by updating the speakerList reference
    speakerList = [...speakerList];

    // Update transcript store with the new cross-media data
    if (file?.uuid && file.transcript_segments) {
      transcriptStore.loadTranscriptData(file.uuid, file.transcript_segments, speakerList);
    }
  }

  /**
   * Load speakers for the current file
   */
  async function loadSpeakers(): Promise<void> {
    if (!file?.uuid) return;

    try {
      // Load speakers from the backend API
      const response = await axiosInstance.get(`/api/speakers/`, {
        params: { file_uuid: file.uuid }  // Use file_uuid parameter (file.uuid contains UUID)
      });

      if (response.data && Array.isArray(response.data)) {
        // Use pre-processed data directly from backend - no frontend business logic
        speakerList = response.data.map((speaker: any) => ({
            ...speaker,
            showMatches: false,  // Only UI state, not business logic
            showSuggestions: false  // Only UI state, not business logic
          }));

        // Store original speaker names for change detection (trimmed for consistent comparison)
        originalSpeakerNames = new Map(
          speakerList.map(speaker => [speaker.uuid, (speaker.display_name || '').trim()])
        );

        // Speakers are now pre-sorted by the backend

        // Load cross-media data for labeled speakers
        await loadCrossMediaDataForLabeledSpeakers();

        // Load data into the transcript store for reactive updates
        if (file?.uuid && file.transcript_segments) {
          transcriptStore.loadTranscriptData(file.uuid, file.transcript_segments, speakerList);
        }

      } else {
        // Fallback: extract from transcript data
        const transcriptData = file?.transcript_segments;
        if (transcriptData) {
          const speakers = new Map();
          transcriptData.forEach((segment: any) => {
            const speakerLabel = segment.speaker_label || segment.speaker?.name || $t('fileDetail.unknownSpeaker');
            if (!speakers.has(speakerLabel)) {
              speakers.set(speakerLabel, {
                name: speakerLabel,
                display_name: segment.speaker?.display_name || speakerLabel
              });
            }
          });
          speakerList = Array.from(speakers.values());
          // Backend provides pre-sorted speakers

          // Load data into the transcript store for fallback case
          if (file?.uuid && file.transcript_segments) {
            transcriptStore.loadTranscriptData(file.uuid, file.transcript_segments, speakerList);
          }
        }
      }
    } catch (error) {
      console.error('Error loading speakers:', error);
      // Fallback: extract from transcript data
      const transcriptData = file?.transcript_segments;
      if (transcriptData) {
        const speakers = new Map();
        transcriptData.forEach((segment: any) => {
          const speakerLabel = segment.speaker_label || segment.speaker?.name || get(t)('fileDetail.unknownSpeaker');
          if (!speakers.has(speakerLabel)) {
            speakers.set(speakerLabel, {
              name: speakerLabel,
              display_name: segment.speaker?.display_name || speakerLabel
            });
          }
        });
        speakerList = Array.from(speakers.values());
        // Backend provides pre-sorted speakers

        // Load data into the transcript store for error fallback case
        if (file?.uuid && file.transcript_segments) {
          transcriptStore.loadTranscriptData(file.uuid, file.transcript_segments, speakerList);
        }
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
    videoUrl = getVideoUrl(fileId);

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
      const segmentElement = document.querySelector(`[data-segment-id="${currentSegment.uuid || currentSegment.id || `${currentSegment.start_time}-${currentSegment.end_time}`}"]`);
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


  // Validate speaker name
  function validateSpeakerName(name: string, speakerId: string | number): { isValid: boolean; error?: string } {
    if (!name || typeof name !== 'string') {
      return { isValid: false, error: $t('speakerValidation.nameRequired') };
    }

    const trimmedName = name.trim();
    if (trimmedName.length === 0) {
      return { isValid: false, error: $t('speakerValidation.nameEmpty') };
    }

    if (trimmedName.length > 100) {
      return { isValid: false, error: $t('speakerValidation.nameTooLong') };
    }

    // Check for duplicate names (excluding the current speaker)
    const existingNames = speakerList
      .filter(s => s.uuid !== speakerId)
      .map(s => (s.display_name || s.name).toLowerCase());

    if (existingNames.includes(trimmedName.toLowerCase())) {
      return { isValid: false, error: $t('speakerValidation.nameDuplicate') };
    }

    return { isValid: true };
  }

  // Handle speaker name input changes (for reactivity)
  function handleSpeakerNameChanged(event: CustomEvent) {
    // Trigger reactivity by reassigning the speakerList array
    // This ensures the reactive statement detects the change
    speakerList = [...speakerList];
  }

  // Handle speakers merged event - refresh all related data silently (no loading spinner)
  async function handleSpeakersMerged() {
    if (!file?.uuid) return;

    try {
      // Silently refresh file data without showing loading state
      const response = await axiosInstance.get(`/api/files/${file.uuid}`);

      if (response.data && typeof response.data === 'object') {
        // Update file data (includes analytics and transcript segments)
        file = response.data;
        collections = response.data.collections || [];
        reactiveFile.set(file);

        // Process transcript data from the refreshed response
        processTranscriptData();
      }

      // Reload speakers to get updated list
      await loadSpeakers();
    } catch (error) {
      console.error('Error refreshing data after speaker merge:', error);
      toastStore.error($t('fileDetail.dataRefreshFailed'));
    }
  }

  // Handle new speaker created - just reload speakers without touching file/analytics
  // The segment assignment will trigger analyticsRefreshNeeded which handles analytics
  async function handleSpeakerCreated() {
    await loadSpeakers();
  }

  // Handle speaker deletion after segment reassignment leaves a speaker with no segments
  async function handleSpeakerDeleted(event: CustomEvent) {
    const { speakerUuid } = event.detail;
    if (!speakerUuid) return;

    // Use the same comprehensive refresh as handleSpeakersMerged
    // This ensures all speaker-related components (Edit Speakers, Merge Speakers, Analytics)
    // stay in sync - just calling loadSpeakers() wasn't triggering proper reactivity
    await handleSpeakersMerged();
  }

  // Handle analytics refresh after segment speaker change (backend refreshes analytics, frontend fetches)
  async function handleAnalyticsRefreshNeeded() {
    if (!file?.uuid) return;

    try {
      // Silently refresh file data to get updated analytics
      const response = await axiosInstance.get(`/api/files/${file.uuid}`);

      if (response.data && typeof response.data === 'object') {
        // Update analytics from refreshed response
        file.analytics = response.data.analytics;
        reactiveFile.set(file);
      }
    } catch (error) {
      console.error('Error refreshing analytics after speaker change:', error);
      // Don't show error toast - analytics refresh is not critical to user workflow
    }
  }

  // Handle speaker name updates
  async function handleSpeakerUpdate(event: CustomEvent) {
    const { speakerId, newName } = event.detail;

    // Validate the speaker name
    const validation = validateSpeakerName(newName, speakerId);
    if (!validation.isValid) {
      toastStore.error(validation.error);
      return;
    }

    // Find the speaker to check if they have a profile
    const speaker = speakerList.find(s => s.uuid === speakerId);

    // Check if this speaker has a profile and the name is changing
    if (speaker && speaker.profile && speaker.profile.name !== newName) {
      // Show confirmation modal for profile update decision
      pendingSpeakerUpdate = { speakerId, newName, speaker };
      profileUpdateTitle = $t('speakerProfile.updateTitle');
      profileUpdateMessage = $t('speakerProfile.linkedMessage', {
        speakerName: speaker.display_name || speaker.name,
        profileName: speaker.profile.name
      });
      showSpeakerProfileConfirmation = true;
      return;
    }

    // If no profile or name is the same, proceed with normal update
    await performSpeakerUpdate(speakerId, newName, 'normal');
  }

  // Handle speaker profile confirmation decision
  async function handleProfileConfirmation(decision: 'update_profile' | 'create_new_profile') {
    if (bulkSaveInProgress) {
      // Handle bulk save confirmation
      await handleBulkConfirmation(decision);
    } else if (pendingSpeakerUpdate) {
      // Handle individual speaker confirmation
      const { speakerId, newName } = pendingSpeakerUpdate;
      await performSpeakerUpdate(speakerId, newName, decision);

      // Reset modal state
      showSpeakerProfileConfirmation = false;
      pendingSpeakerUpdate = null;
      profileUpdateMessage = '';
      profileUpdateTitle = '';
    }
  }

  // Handle modal cancellation
  function handleProfileConfirmationCancel() {
    showSpeakerProfileConfirmation = false;
    pendingSpeakerUpdate = null;
    profileUpdateMessage = '';
    profileUpdateTitle = '';

    // Reset bulk save state if it was in progress
    if (bulkSaveInProgress) {
      bulkSaveInProgress = false;
      speakerConfirmationQueue = [];
      currentConfirmationIndex = 0;
      bulkSaveDecisions.clear();
      savingSpeakers = false;
    }
  }

  // Handle bulk save confirmation
  async function handleBulkConfirmation(decision: 'update_profile' | 'create_new_profile') {
    if (!pendingSpeakerUpdate || speakerConfirmationQueue.length === 0) return;

    const { speakerId, newName } = pendingSpeakerUpdate;

    // Store the decision for this speaker
    bulkSaveDecisions.set(speakerId, { decision, newName });

    // Move to next confirmation or finish
    currentConfirmationIndex++;

    if (currentConfirmationIndex < speakerConfirmationQueue.length) {
      // Show next confirmation
      showNextConfirmation();
    } else {
      // All confirmations done, proceed with bulk save
      showSpeakerProfileConfirmation = false;
      await performBulkSaveWithDecisions();
    }
  }

  // Show next confirmation in the queue
  function showNextConfirmation() {
    if (currentConfirmationIndex < speakerConfirmationQueue.length) {
      const speaker = speakerConfirmationQueue[currentConfirmationIndex];
      pendingSpeakerUpdate = {
        speakerId: speaker.uuid,
        newName: speaker.display_name,
        speaker
      };
      profileUpdateTitle = $t('fileDetail.updateSpeakerProfileCounter', { current: currentConfirmationIndex + 1, total: speakerConfirmationQueue.length });
      profileUpdateMessage = $t('fileDetail.profileLinkedMessage', { displayName: speaker.display_name || speaker.name, profileName: speaker.profile.name });
      showSpeakerProfileConfirmation = true;
    }
  }

  // Perform the actual speaker update with the specified action
  async function performSpeakerUpdate(speakerId: number | string, newName: string, action: 'normal' | 'update_profile' | 'create_new_profile') {
    // Update the speaker in the speakerList and maintain sort order
    // IMPORTANT: Only update display_name, NEVER change name (original speaker ID for color consistency)
    speakerList = speakerList
      .map(speaker => {
        if (speaker.uuid === speakerId) {
          return { ...speaker, display_name: newName };
        }
        return speaker;
      });
      // Backend provides pre-sorted speakers

    // Update the transcript store FIRST - this will trigger reactive updates in TranscriptModal
    transcriptStore.updateSpeakerName(String(speakerId), newName);

    // Update transcript segment speaker names in file object (for other components)
    const transcriptData = file?.transcript_segments;
    if (transcriptData && Array.isArray(transcriptData)) {
      transcriptData.forEach(segment => {
        if (segment.speaker_id === speakerId) {
          // Update ALL speaker name fields that components might use
          segment.resolved_speaker_name = newName;
          if (segment.speaker) {
            segment.speaker.display_name = newName;
          } else {
            // Create speaker object if it doesn't exist
            segment.speaker = {
              id: speakerId,
              name: segment.speaker_label || `SPEAKER_${speakerId}`,
              display_name: newName
            };
          }
        }
      });

      // Update file data
      file.transcript_segments = transcriptData.map(segment => ({ ...segment }));
      file = { ...file }; // Trigger reactivity
      reactiveFile.set(file);
    }

    // Update subtitles in the video player with new speaker names
    if (videoPlayerComponent && videoPlayerComponent.updateSubtitles) {
      try {
        await videoPlayerComponent.updateSubtitles();
      } catch (error) {
        console.warn('Failed to update subtitles after speaker update:', error);
      }
    }

    // Persist to database with the action decision
    try {
      const speaker = speakerList.find(s => s.uuid === speakerId);
      if (speaker && speaker.uuid) {
        const payload: any = {
          display_name: newName
          // NEVER update 'name' field - it contains the original speaker ID for color consistency
        };

        // Add profile action if needed
        if (action !== 'normal') {
          payload.profile_action = action;
        }

        await axiosInstance.put(`/api/speakers/${speaker.uuid}`, payload);

        // Show success feedback with appropriate message
        const successMessage = action === 'update_profile'
          ? $t('speakerProfile.updatedGlobally', { name: newName })
          : action === 'create_new_profile'
          ? $t('speakerProfile.newCreated', { name: newName })
          : $t('speakerProfile.renamed', { name: newName });

        toastStore.success(successMessage);
      }
    } catch (error: any) {
      console.error('Failed to update speaker name in database:', error);

      // Show user-friendly error with option to retry
      const errorMessage = error.response?.status === 404
        ? $t('speakerProfile.notFound')
        : error.response?.status === 403
        ? $t('speakerProfile.permissionDenied')
        : $t('speakerProfile.saveFailed');

      toastStore.error($t('speakerProfile.errorWithLocal', { error: errorMessage }));

      // Note: We don't revert frontend changes as they're useful even without backend persistence
    }
  }

  function handleEditSegment(event: any) {
    const segment = event.detail.segment;
    editingSegmentId = segment.uuid;
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

      const segmentUuid = segment.uuid;
      const response = await axiosInstance.put(`/api/files/${fileId}/transcript/segments/${segmentUuid}`, segmentUpdate);

      if (response.data) {
        // Update the transcript store FIRST for reactivity
        transcriptStore.updateSegmentText(segmentUuid, editingSegmentText);

        // Update the specific segment in local data
        const transcriptData = file?.transcript_segments;
        if (transcriptData && file) {
          const segmentIndex = transcriptData.findIndex((s: any) => s.uuid === segmentUuid);

          if (segmentIndex !== -1) {
            // Create a new array with the updated segment, preserving speaker data
            const updatedSegments = [...transcriptData];
            const originalSegment = updatedSegments[segmentIndex];

            // CRITICAL: Merge response data but preserve original speaker information
            updatedSegments[segmentIndex] = {
              ...originalSegment, // Keep all original data (including speaker info)
              ...response.data,   // Apply backend updates
              // Explicitly preserve speaker-related fields that determine colors
              speaker_label: originalSegment.speaker_label,
              speaker_id: originalSegment.speaker_id,
              speaker: originalSegment.speaker,
              resolved_speaker_name: originalSegment.resolved_speaker_name
            };


            // Update file with new segments array
            file = {
              ...file,
              transcript_segments: updatedSegments
            };
            reactiveFile.set(file);


            // Clear cached processed videos so downloads will use updated transcript
            try {
              await axiosInstance.delete(`/api/files/${file.uuid}/cache`);
            } catch (error) {
              console.warn('Could not clear video cache:', error);
            }
          }
        }

        editingSegmentId = null;
        editingSegmentText = '';

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

      // Show error as toast notification for consistency
      if (error.response?.status === 405) {
        toastStore.error($t('fileDetail.transcriptEditingNotSupported'));
      } else if (error.response?.status === 404) {
        toastStore.error($t('fileDetail.transcriptSegmentNotFound'));
      } else if (error.response?.status === 422) {
        toastStore.error($t('fileDetail.invalidSegmentData'));
      } else {
        toastStore.error($t('fileDetail.failedToSaveSegment'));
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
        // Refresh file data to get updated segments
        await fetchFileDetails(fileId);

        // The fetchFileDetails will reload the transcript store via processTranscriptData() and loadSpeakers()
        // so the transcript modal will automatically update

        isEditingTranscript = false;
      }
    } catch (error) {
      console.error('Error saving transcript:', error);
      toastStore.error($t('fileDetail.failedToSaveTranscript'));
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
        const endpoint = `/comments/files/${file.uuid}/comments`;
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
          const endpoint = `/comments/files/${file.uuid}/comments`;
          const response = await axiosInstance.get(endpoint, { headers });
          fileComments = response.data || [];

          // Get current user data from localStorage
          const userData = JSON.parse(localStorage.getItem('user') || '{}');

          // Add current user data to each comment
          fileComments = fileComments.map((comment: any) => {
            // If the comment is from the current user, add their details
            if (!comment.user && comment.user_id === userData.uuid) {
              comment.user = {
                full_name: userData.full_name,
                username: userData.username,
                email: userData.email
              };
            } else if (!comment.user) {
              // For other users' comments that have no user object,
              // create a placeholder to avoid 'Anonymous'
              comment.user = {
                full_name: $t('fileDetail.adminUser'), // Default from browser info
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
        const speakerName = segment.speaker_label || segment.speaker?.name || $t('fileDetail.speakerDefault');
        return speakerMapping.get(speakerName) || segment.speaker?.display_name || speakerName;
      };

      // Client-side export with updated speaker names
      let content = '';
      const filename = file.filename.replace(/\.[^/.]+$/, '');

      switch (format) {
        case 'txt':
          // Create transcript content with segments
          let segments = transcriptData.map((seg: any) =>
            `[${formatSimpleTimestamp(seg.start_time || seg.start || 0)} --> ${formatSimpleTimestamp(seg.end_time || seg.end || 0)}] ${getSpeakerDisplayName(seg)}: ${seg.text}`
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
          let csvHeader = $t('fileDetail.csvHeaderDefault');
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
            csvHeader = $t('fileDetail.csvHeaderWithComments');

            // Add comments as separate rows
            const commentRows = fileComments.map((comment: any) => {
              const timestamp = comment.timestamp;
              const userName = comment.user?.full_name || comment.user?.username || comment.user?.email || 'Anonymous';
              const escapedText = `"${comment.text.replace(/"/g, '""')}"`;
              // Add comment rows with user info in the Speaker column and 'COMMENT' in Comment Type
              return `${timestamp},${timestamp},"${$t('fileDetail.userComment')}: ${userName}",${escapedText},"${$t('fileDetail.commentType')}"`;
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
              const text = `${$t('fileDetail.userComment')}: ${userName}: ${comment.text}`;

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
              const text = `${$t('fileDetail.userComment')}: ${userName}: ${comment.text}`;

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
      // Validate all speaker names first
      const speakersToUpdate = speakerList.filter(speaker =>
        speaker.uuid &&
        speaker.display_name &&
        speaker.display_name.trim() !== "" &&
        !speaker.display_name.startsWith('SPEAKER_')
      );

      // Validate each speaker name
      for (const speaker of speakersToUpdate) {
        const validation = validateSpeakerName(speaker.display_name, speaker.uuid);
        if (!validation.isValid) {
          toastStore.error(`${speaker.name}: ${validation.error}`);
          savingSpeakers = false;
          return;
        }
      }

      // Check for speakers that need profile confirmation
      const speakersNeedingConfirmation = speakersToUpdate.filter(speaker =>
        speaker.profile && speaker.profile.name !== speaker.display_name.trim()
      );

      if (speakersNeedingConfirmation.length > 0) {
        // Start bulk confirmation process
        speakerConfirmationQueue = speakersNeedingConfirmation;
        currentConfirmationIndex = 0;
        bulkSaveInProgress = true;
        bulkSaveDecisions.clear();

        // Start with first confirmation
        showNextConfirmation();
        return;
      }

      // No confirmations needed, proceed with regular save
      await performBulkSave(speakersToUpdate);

    } catch (error) {
      console.error('Error saving speaker names:', error);
      toastStore.error($t('speakerProfile.saveAllFailed'));
      savingSpeakers = false;
    }
  }

  // Perform bulk save with confirmation decisions
  async function performBulkSaveWithDecisions() {
    try {
      const speakersToUpdate = speakerList.filter(speaker =>
        speaker.uuid &&
        speaker.display_name &&
        speaker.display_name.trim() !== "" &&
        !speaker.display_name.startsWith('SPEAKER_')
      );

      await performBulkSave(speakersToUpdate, bulkSaveDecisions);

      // Reset bulk save state
      bulkSaveInProgress = false;
      speakerConfirmationQueue = [];
      currentConfirmationIndex = 0;
      bulkSaveDecisions.clear();

    } catch (error) {
      console.error('Error in bulk save with decisions:', error);
      toastStore.error($t('speakerProfile.saveAllFailed'));
      savingSpeakers = false;

      // Reset bulk save state
      bulkSaveInProgress = false;
      speakerConfirmationQueue = [];
      currentConfirmationIndex = 0;
      bulkSaveDecisions.clear();
    }
  }

  // Perform the actual bulk save operation
  async function performBulkSave(speakersToUpdate, decisions = new Map()) {
    // STEP 1: Optimistic UI updates - immediately update voice suggestions with new names
    const nameChanges = new Map(); // Track profile name changes for voice suggestions

    speakersToUpdate.forEach((speaker: any) => {
      const decision = decisions.get(speaker.uuid);
      const newName = speaker.display_name.trim();

      // If updating a profile globally, track the name change
      if (decision && decision.decision === 'update_profile' && speaker.profile) {
        nameChanges.set(speaker.profile.uuid, { oldName: speaker.profile.name, newName });
      }
    });

    // Optimistically update voice suggestions for all speakers
    if (nameChanges.size > 0) {
      speakerList = speakerList.map(s => {
        if (s.voice_suggestions && s.voice_suggestions.length > 0) {
          s.voice_suggestions = s.voice_suggestions.map((suggestion: any) => {
            // Find if this suggestion's name matches any profile being updated
            for (const [profileId, change] of nameChanges) {
              if (suggestion.name === change.oldName && suggestion.suggestion_type === 'profile') {
                return { ...suggestion, name: change.newName };
              }
            }
            return suggestion;
          });
        }
        return s;
      });
    }

    // STEP 2: Set loading state for voice suggestions (they'll refresh after OpenSearch updates)
    loadingVoiceSuggestions = true;

    // STEP 3: Update speakers in the backend with decisions
    const updatePromises = speakersToUpdate.map(async (speaker: any) => {
      const decision = decisions.get(speaker.uuid);
      const payload: any = {
        display_name: speaker.display_name.trim(),
        name: speaker.name
      };

      // Add profile action if there's a decision for this speaker
      if (decision) {
        payload.profile_action = decision.decision;
      }

      return axiosInstance.put(`/api/speakers/${speaker.uuid}`, payload);
    });

    await Promise.all(updatePromises);

    // STEP 4: PostgreSQL updates complete - stop save button spinner immediately!
    savingSpeakers = false;
    isEditingSpeakers = false;
    toastStore.success($t('speakerProfile.savedSuccess'));

    // Reset original names to current values (no changes after save)
    originalSpeakerNames = new Map(
      speakerList.map(speaker => [speaker.uuid, (speaker.display_name || '').trim()])
    );

    // STEP 5: Update the transcript store for reactive updates (instant)
    speakerList.forEach((speaker: any) => {
      if (speaker.uuid && speaker.display_name && speaker.display_name.trim() !== "" && !speaker.display_name.startsWith('SPEAKER_')) {
        transcriptStore.updateSpeakerName(speaker.uuid, speaker.display_name.trim());
      }
    });

    // Update local transcript data with new display names
    const transcriptData = file?.transcript_segments;
    if (transcriptData) {
      const speakerMapping = new Map();
      speakerList.forEach((speaker: any) => {
        if (speaker.display_name && speaker.display_name.trim() !== "" && !speaker.display_name.startsWith('SPEAKER_')) {
          speakerMapping.set(speaker.name, speaker.display_name.trim());
        }
      });

      transcriptData.forEach((segment: any) => {
        const speakerName = segment.speaker_label || segment.speaker?.name;
        const newDisplayName = speakerMapping.get(speakerName);
        if (newDisplayName) {
          segment.resolved_speaker_name = newDisplayName;
          if (segment.speaker) {
            segment.speaker.display_name = newDisplayName;
          } else {
            segment.speaker = {
              id: segment.speaker_id,
              name: speakerName,
              display_name: newDisplayName
            };
          }
        }
      });

      file.transcript_segments = [...transcriptData];
      file = { ...file };
      reactiveFile.set(file);
    }

    // Update subtitles and clear cache (async, don't block)
    if (videoPlayerComponent && videoPlayerComponent.updateSubtitles) {
      videoPlayerComponent.updateSubtitles().catch(error => {
        console.warn('Failed to update subtitles after saving speaker names:', error);
      });
    }

    axiosInstance.delete(`/api/files/${file.uuid}/cache`).catch(error => {
      console.warn('Could not clear video cache:', error);
    });

    // STEP 6: Voice suggestions will be refreshed via WebSocket notification
    // The speaker_updated WebSocket event will trigger loadSpeakers() and clear the loading state
    // This happens automatically when the backend finishes OpenSearch updates
    // If WebSocket fails, fallback to timeout-based reload
    setTimeout(async () => {
      if (loadingVoiceSuggestions) {
        // WebSocket didn't arrive in time, reload manually
        await loadSpeakers();
        loadingVoiceSuggestions = false;
      }
    }, 3000); // 3 second failsafe timeout

    // Refresh speakers from the backend to sync local state
    speakerList.forEach((speaker: any) => {
      if (speaker.uuid && speaker.display_name && speaker.display_name.trim() !== "" && !speaker.display_name.startsWith('SPEAKER_')) {
        transcriptStore.updateSpeakerName(speaker.uuid, speaker.display_name.trim());
      }
    });
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

  function handlePlay(_event: CustomEvent) {
    // Handle play event if needed
  }

  function handlePause(_event: CustomEvent) {
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
        file.summary_data = null;
        file.summary_opensearch_id = null;

        // Set summary generating state if LLM is available (reprocessing triggers auto-summary)
        if (llmAvailable) {
          summaryGenerating = true;
          generatingSummary = true;
        }

        file = file; // Trigger reactivity
      }

      await axiosInstance.post(`/api/files/${fileId}/reprocess`);

      // Don't immediately fetch - let WebSocket notifications handle updates
      // The file is now pending/processing and notifications will update the UI

    } catch (error) {
      console.error('❌ Error starting reprocess:', error);
      toastStore.error($t('reprocess.startFailed'));

      // Revert optimistic update on error
      if (file) {
        await fetchFileDetails(fileId);
      }
    } finally {
      reprocessing = false;
    }
  }

  async function handleReprocessHeader() {
    if (!file?.uuid) return;

    try {
      reprocessing = true;

      // Reset notification processing state for reprocessing
      lastProcessedNotificationState = '';

      // Optimistically set file to processing state for immediate UI feedback
      file.status = 'processing';
      file.progress = 0;
      // Clear transcript data to show placeholder state during reprocessing
      file.transcript_segments = [];
      file.summary_data = null;
      file.summary_opensearch_id = null;

      // Set summary generating state if LLM is available (reprocessing triggers auto-summary)
      if (llmAvailable) {
        summaryGenerating = true;
        generatingSummary = true;
      }

      file = file; // Trigger reactivity

      // Build request body with speaker parameters if provided
      const requestBody: any = {};
      if (reprocessMinSpeakers !== null) {
        requestBody.min_speakers = reprocessMinSpeakers;
      }
      if (reprocessMaxSpeakers !== null) {
        requestBody.max_speakers = reprocessMaxSpeakers;
      }
      if (reprocessNumSpeakers !== null) {
        requestBody.num_speakers = reprocessNumSpeakers;
      }

      await axiosInstance.post(`/api/files/${file.uuid}/reprocess`, Object.keys(requestBody).length > 0 ? requestBody : undefined);

      // Reset settings after starting
      showReprocessSettings = false;
      reprocessMinSpeakers = null;
      reprocessMaxSpeakers = null;
      reprocessNumSpeakers = null;

      // Don't immediately fetch - let WebSocket notifications handle updates
      toastStore.success($t('reprocess.startedSuccess'));

    } catch (error) {
      console.error('❌ Error starting reprocess (header):', error);
      toastStore.error($t('reprocess.startFailed'));

      // Revert optimistic update on error
      await fetchFileDetails(file.uuid);
    } finally {
      reprocessing = false;
    }
  }

  // Validation for reprocess settings
  $: reprocessSettingsValid = !(reprocessMinSpeakers !== null && reprocessMaxSpeakers !== null && reprocessMinSpeakers > reprocessMaxSpeakers);


  /**
   * Generate summary for the transcript
   */
  async function handleGenerateSummary() {
    if (!file?.uuid) return;

    // Check if LLM is available
    if (!$isLLMAvailable) {
      return;
    }

    try {
      generatingSummary = true;

      await axiosInstance.post(`/api/files/${file.uuid}/summarize`);

      // Don't refresh page - let WebSocket notifications handle status updates
      // This preserves user's editing state

      // The WebSocket will update summaryGenerating = true when processing starts
    } catch (error: any) {
      console.error('Error generating summary:', error);
      const errorMessage = error.response?.data?.detail || $t('fileDetail.failedToGenerateSummary');

      toastStore.error(errorMessage, 5000);
    } finally {
      generatingSummary = false;
    }
  }

  /**
   * Load summary data from the backend
   */
  async function loadSummary() {
    if (!file?.uuid) return;

    try {
      const response = await axiosInstance.get(`/api/files/${file.uuid}/summary`);
      summaryData = response.data.summary_data;
    } catch (error: any) {
      console.error('Error loading summary:', error);
      if (error.response?.status !== 404) {
        toastStore.error($t('fileDetail.failedToLoadSummary'), 5000);
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

  // Load user transcription preferences
  async function loadTranscriptionPreferences() {
    try {
      const [userSettings, systemDefaults] = await Promise.all([
        getTranscriptionSettings(),
        getTranscriptionSystemDefaults()
      ]);
      transcriptionSettings = userSettings;
      transcriptionSystemDefaults = systemDefaults;
    } catch (err) {
      console.error('Failed to load transcription settings:', err);
      transcriptionSettings = { ...DEFAULT_TRANSCRIPTION_SETTINGS };
    } finally {
      transcriptionPrefsLoaded = true;
    }
  }

  // Handle reprocess with user preferences
  function handleReprocessWithPrefs() {
    if (!transcriptionSettings) {
      // Settings not loaded yet, show the settings dropdown
      reprocessDropdownMode = 'settings';
      showReprocessSettings = true;
      return;
    }

    const behavior = transcriptionSettings.speaker_prompt_behavior;

    if (behavior === 'always_prompt') {
      // Pre-fill with user's saved values and show settings dropdown
      reprocessMinSpeakers = transcriptionSettings.min_speakers || null;
      reprocessMaxSpeakers = transcriptionSettings.max_speakers || null;
      reprocessDropdownMode = 'settings';
      showReprocessSettings = !showReprocessSettings;
    } else {
      // Show confirmation dropdown with start button
      reprocessDropdownMode = 'confirmation';
      showReprocessSettings = true;
    }
  }

  // Execute reprocess from confirmation mode
  function handleReprocessFromConfirmation() {
    const behavior = transcriptionSettings?.speaker_prompt_behavior;
    if (behavior === 'use_defaults') {
      reprocessMinSpeakers = null;
      reprocessMaxSpeakers = null;
      reprocessNumSpeakers = null;
    } else if (behavior === 'use_custom' && transcriptionSettings) {
      reprocessMinSpeakers = transcriptionSettings.min_speakers;
      reprocessMaxSpeakers = transcriptionSettings.max_speakers;
      reprocessNumSpeakers = null;
    }
    handleReprocessHeader();
  }

  // Get reprocess confirmation message
  function getReprocessConfirmationMessage(): string {
    if (!transcriptionSettings) return '';

    if (transcriptionSettings.speaker_prompt_behavior === 'use_defaults') {
      const min = transcriptionSystemDefaults?.min_speakers ?? 1;
      const max = transcriptionSystemDefaults?.max_speakers ?? 20;
      return $t('fileDetail.usingSystemDefaults', { min, max });
    } else if (transcriptionSettings.speaker_prompt_behavior === 'use_custom') {
      return $t('fileDetail.usingYourSettings', { min: transcriptionSettings.min_speakers, max: transcriptionSettings.max_speakers });
    }
    return '';
  }

  // Handle customize from confirmation mode
  function handleReprocessCustomize() {
    if (reprocessFadeTimeout) {
      clearTimeout(reprocessFadeTimeout);
      reprocessFadeTimeout = null;
    }

    // Pre-fill with current effective values
    if (transcriptionSettings) {
      if (transcriptionSettings.speaker_prompt_behavior === 'use_custom') {
        reprocessMinSpeakers = transcriptionSettings.min_speakers || null;
        reprocessMaxSpeakers = transcriptionSettings.max_speakers || null;
      } else if (transcriptionSystemDefaults) {
        reprocessMinSpeakers = transcriptionSystemDefaults.min_speakers;
        reprocessMaxSpeakers = transcriptionSystemDefaults.max_speakers;
      }
    }
    reprocessDropdownMode = 'settings';
  }

  // Close reprocess dropdown
  function closeReprocessDropdown() {
    showReprocessSettings = false;
    if (reprocessFadeTimeout) {
      clearTimeout(reprocessFadeTimeout);
      reprocessFadeTimeout = null;
    }
    reprocessMinSpeakers = null;
    reprocessMaxSpeakers = null;
    reprocessNumSpeakers = null;
  }

  // Click outside handler for reprocess dropdown
  function handleReprocessClickOutside(event: MouseEvent) {
    if (showReprocessSettings && reprocessContainerRef && !reprocessContainerRef.contains(event.target as Node)) {
      closeReprocessDropdown();
    }
  }

  // Component mount logic
  onMount(() => {
    // Add click-outside listener for reprocess dropdown
    document.addEventListener('click', handleReprocessClickOutside);

    // Use dynamic URL based on current location (works with reverse proxy)
    apiBaseUrl = getAppBaseUrl();

    // Load user transcription preferences
    loadTranscriptionPreferences();

    if (id) {
      fileId = id;
    } else {
      console.error('FileDetail: No id parameter provided');
      const urlParams = new URLSearchParams(window.location.search);
      const pathParts = window.location.pathname.split('/');
      fileId = urlParams.get('id') || pathParts[pathParts.length - 1] || '';
    }

    if (fileId) {
      // Load file details
      fetchFileDetails().catch(err => {
        console.error('Error loading file details:', err);
      });

      // Load AI suggestions if available
      loadAISuggestions().catch(err => {
        console.error('Error loading AI suggestions:', err);
      });
    } else {
      errorMessage = $t('fileDetail.invalidFileId');
      isLoading = false;
    }

    // LLM status monitoring is now handled by the Settings component and reactive store

    // Subscribe to WebSocket notifications for real-time updates
    wsUnsubscribe = websocketStore.subscribe(($ws) => {


      if ($ws.notifications.length > 0) {

        // Find the most recently updated notification for the current file
        const currentFileNotifications = $ws.notifications.filter(n => {
          const notificationFileId = String(n.data?.file_id || '');
          const currentFileId = String(fileId);
          return notificationFileId === currentFileId;
        });

        if (currentFileNotifications.length === 0) {
          return;
        }

        // Sort by timestamp (most recent first)
        currentFileNotifications.sort((a, b) => {
          const aTime = a.timestamp;
          const bTime = b.timestamp;
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
                  currentProcessingStep = latestNotification.currentStep || latestNotification.message || latestNotification.data?.message || $t('fileDetail.processingDefault');
                  file = { ...file }; // Trigger reactivity
                  reactiveFile.set(file);

                }
              } else if (notificationStatus === 'completed' || notificationStatus === 'success' || notificationStatus === 'complete' || notificationStatus === 'finished') {
                // Transcription completed - show completion and refresh
                if (file) {
                  file.progress = 100;
                  file.status = 'completed';
                  currentProcessingStep = $t('fileDetail.processingComplete');

                  // Show AI summary spinner only if LLM is available after transcription completion
                  if (llmAvailable) {
                    summaryGenerating = true;
                    generatingSummary = true;
                    // Keep reprocessing flag true until summary completes to maintain proper UI state
                  } else {
                    // No LLM available, ensure spinners are off and reset reprocessing flag
                    summaryGenerating = false;
                    generatingSummary = false;
                    reprocessing = false;
                  }

                  file = { ...file }; // Trigger reactivity
                  reactiveFile.set(file);
                }

                // Clear processing step and refresh transcript data after completion
                setTimeout(async () => {
                  currentProcessingStep = ''; // Clear processing step

                  // Only refresh the transcript data, not the entire file object to preserve spinner state
                  if (file?.uuid && (file.status === 'completed' || file.status === 'success')) {
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
                // Skip notifications for other files
              } else {

              // Get status from notification (progressive notifications set it at root level)
              const status = latestNotification.status || latestNotification.data?.status;


              if (status === 'queued' || status === 'processing' || status === 'generating') {
                // Summary generation started - show spinner only if LLM is available
                if (llmAvailable) {
                  summaryGenerating = true;
                  generatingSummary = true;
                } else {
                  // LLM not available, ensure spinners are off
                  summaryGenerating = false;
                  generatingSummary = false;
                }

              } else if (status === 'completed' || status === 'success' || status === 'complete' || status === 'finished') {
                // Summary completed - stop spinners and update file
                summaryGenerating = false;
                generatingSummary = false;

                // Reset reprocessing flag when summary completes (final step of reprocessing)
                reprocessing = false;

                if (file) {
                  // Update summary-related fields from notification data
                  // Note: The notification contains a brief preview, not the full summary_data
                  const summaryPreview = latestNotification.data?.summary;
                  const summaryId = latestNotification.data?.summary_opensearch_id;

                  // Set a flag to indicate summary exists (full data fetched via API)
                  if (summaryPreview || summaryId) {
                    file.summary_data = { preview: summaryPreview }; // Minimal indicator
                  }
                  if (summaryId) {
                    file.summary_opensearch_id = summaryId;
                  }

                  // Force reactivity update by creating new object reference
                  file = { ...file };
                  reactiveFile.set(file);
                }
              } else if (status === 'failed' || status === 'error') {
                // Summary failed - stop spinners and show error
                summaryGenerating = false;
                generatingSummary = false;

                // Get error message from notification
                const errorMessage = latestNotification.data?.message || latestNotification.message || $t('fileDetail.failedToGenerateSummaryGeneric');
                const isLLMConfigError = errorMessage.toLowerCase().includes('llm service is not available') ||
                                       errorMessage.toLowerCase().includes('configure an llm provider') ||
                                       errorMessage.toLowerCase().includes('llm provider');

                if (!isLLMConfigError) {
                  toastStore.error(errorMessage, 5000);
                }

              }
              } // Close the else block for file ID matching
            }

            // Handle speaker update notifications (for real-time voice suggestion refresh)
            if (latestNotification.type === 'speaker_updated') {
              // Reload speakers to get fresh voice suggestions from OpenSearch
              if (loadingVoiceSuggestions) {
                loadSpeakers().then(() => {
                  loadingVoiceSuggestions = false;
                });
              }
            }

            // Handle topic extraction status updates (AI suggestions for tags/collections)
            if (latestNotification.type === 'topic_extraction_status') {
              const status = latestNotification.status || latestNotification.data?.status;
              const message = latestNotification.message || latestNotification.data?.message;

              if (status === 'processing') {
                // Update processing step to show what's happening
                currentProcessingStep = message || $t('fileDetail.analyzingTranscript');

              } else if (status === 'completed') {
                // Show completion message briefly before clearing
                currentProcessingStep = message || $t('fileDetail.aiSuggestionsComplete');

                // Reload AI suggestions when extraction completes
                // This will fetch the newly generated suggestions and update the UI dynamically
                loadAISuggestions().catch(err => {
                  console.error('Error reloading AI suggestions after extraction:', err);
                });

                // Clear processing step after a brief delay
                setTimeout(() => {
                  currentProcessingStep = '';
                }, 2000);

              } else if (status === 'failed' || status === 'not_configured') {
                // Clear processing step on failure
                currentProcessingStep = '';
              }
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
    // Player cleanup is now handled by VideoPlayer component
    playerInitialized = false;

    // LLM status cleanup is handled by the Settings component

    // Clean up WebSocket subscription
    if (wsUnsubscribe) {
      wsUnsubscribe();
    }

    // Clean up click-outside listener for reprocess dropdown
    document.removeEventListener('click', handleReprocessClickOutside);

    // Clear the transcript store when leaving the page
    transcriptStore.clear();
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
  <title>{file?.filename || $t('fileDetail.loadingFile')}</title>
</svelte:head>

<div class="file-detail-page">
  {#if isLoading}
    <div class="loading-container">
      <div class="spinner"></div>
      <p>{$t('fileDetail.loading')}</p>
    </div>
  {:else if errorMessage}
    <div class="error-container">
      <p class="error-message">{errorMessage}</p>
      <button
        on:click={() => fetchFileDetails()}
        title={$t('fileDetail.retryTooltip')}
      >{$t('fileDetail.tryAgain')}</button>
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
          <h4>{file?.content_type?.startsWith('audio/') ? $t('fileDetail.audio') : $t('fileDetail.video')}</h4>
          <!-- Action Buttons - right aligned above video -->
          <div class="header-buttons">
            <!-- View Full Transcript Button - LEFT of AI Summary -->
            {#if file && file.transcript_segments && file.transcript_segments.length > 0 && file.status !== 'processing'}
              <button
                class="view-transcript-btn"
                on:click={() => showTranscriptModal = true}
                title={$t('fileDetail.viewTranscript')}
              >
                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" class="transcript-icon">
                  <path d="M4 2a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H4zm0 1h8a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/>
                  <path d="M5 5h6v1H5V5zm0 2h6v1H5V7zm0 2h4v1H5V9z"/>
                </svg>
                {$t('fileDetail.transcript')}
              </button>
            {/if}
          <!-- Debug: Summary button state: hasSummary={!!(file?.summary_data || file?.summary_opensearch_id)}, summaryGenerating={summaryGenerating}, generatingSummary={generatingSummary}, fileStatus={file?.status} -->
          {#if file?.summary_data || file?.summary_opensearch_id}
            <button
              class="view-summary-btn"
              on:click={handleShowSummary}
              title={$t('fileDetail.viewSummaryTooltip')}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" class="ai-icon">
                <path d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456zM16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423L16.5 15.75l.394 1.183a2.25 2.25 0 001.423 1.423L19.5 18.75l-1.183.394a2.25 2.25 0 00-1.423 1.423z"/>
              </svg>
              {$t('fileDetail.summary')}
            </button>
          {:else if summaryGenerating || generatingSummary}
            <!-- Show generating state even when no summary exists yet -->
            <button
              class="generate-summary-btn"
              disabled
              title={$t('fileDetail.aiSummaryGenerating')}
            >
              <div class="spinner-small"></div>
              <span>{$t('fileDetail.aiSummary')}</span>
            </button>
          {:else if file?.status === 'completed'}
            <button
              class="generate-summary-btn"
              on:click={handleGenerateSummary}
              disabled={generatingSummary || summaryGenerating || !llmAvailable}
              title={!llmAvailable ? $t('fileDetail.aiNotAvailable') :
                     (generatingSummary || summaryGenerating) ? $t('fileDetail.aiSummaryGenerating') :
                     $t('fileDetail.generateSummaryTooltip')}
            >
              {#if generatingSummary || summaryGenerating}
                <div class="spinner-small"></div>
                <span>{$t('fileDetail.aiSummary')}</span>
              {:else}
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" class="ai-icon">
                  <path d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456zM16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423L16.5 15.75l.394 1.183a2.25 2.25 0 001.423 1.423L19.5 18.75l-1.183.394a2.25 2.25 0 00-1.423 1.423z"/>
                </svg>
                {$t('fileDetail.generateSummary')}
              {/if}
            </button>
          {/if}
          <!-- Reprocess Button with settings dropdown -->
          {#if file && (file.status === 'error' || file.status === 'completed' || file.status === 'failed')}
            <div class="reprocess-dropdown-container" bind:this={reprocessContainerRef}>
              <button
                class="reprocess-button-header"
                on:click={handleReprocessWithPrefs}
                disabled={reprocessing}
                title={reprocessing ? $t('fileDetail.reprocessingTooltip') : $t('fileDetail.reprocessTooltip')}
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M23 4v6h-6"></path>
                  <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
                </svg>
                {#if reprocessing}
                  <div class="spinner-small"></div>
                {/if}
              </button>

              {#if showReprocessSettings}
                <div class="reprocess-settings-dropdown">
                  {#if reprocessDropdownMode === 'confirmation'}
                    <!-- Confirmation message -->
                    <div class="reprocess-confirmation-content">
                      <div class="reprocess-confirmation-info">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                          <circle cx="12" cy="12" r="10"></circle>
                          <line x1="12" y1="16" x2="12" y2="12"></line>
                          <line x1="12" y1="8" x2="12.01" y2="8"></line>
                        </svg>
                        <span class="reprocess-confirmation-message">{getReprocessConfirmationMessage()}</span>
                      </div>
                      <div class="reprocess-confirmation-actions">
                        <button class="btn-cancel" on:click={handleReprocessCustomize}>{$t('reprocess.customize')}</button>
                        <button class="btn-confirm" on:click={handleReprocessFromConfirmation}>{$t('reprocess.start')}</button>
                      </div>
                    </div>
                  {:else}
                    <!-- Settings form -->
                    <div class="reprocess-settings-header">
                      <h4>{$t('reprocess.settingsTitle')}</h4>
                      <p>{$t('reprocess.settingsHint')}</p>
                    </div>

                    <div class="reprocess-settings-row">
                      <div class="reprocess-setting-field">
                        <label for="header-min-speakers">{$t('reprocess.minSpeakers')}</label>
                        <input
                          id="header-min-speakers"
                          type="number"
                          min="1"
                          placeholder={$t('reprocess.defaultPlaceholder')}
                          bind:value={reprocessMinSpeakers}
                          disabled={reprocessNumSpeakers !== null}
                        />
                      </div>

                      <div class="reprocess-setting-field">
                        <label for="header-max-speakers">{$t('reprocess.maxSpeakers')}</label>
                        <input
                          id="header-max-speakers"
                          type="number"
                          min="1"
                          placeholder={$t('reprocess.defaultPlaceholder')}
                          bind:value={reprocessMaxSpeakers}
                          disabled={reprocessNumSpeakers !== null}
                        />
                      </div>
                    </div>

                    <div class="reprocess-setting-field">
                      <label for="header-num-speakers">
                        {$t('reprocess.fixedCount')}
                        <span class="setting-hint">{$t('reprocess.fixedCountHint')}</span>
                      </label>
                      <input
                        id="header-num-speakers"
                        type="number"
                        min="1"
                        placeholder={$t('reprocess.autoPlaceholder')}
                        bind:value={reprocessNumSpeakers}
                      />
                    </div>

                    {#if !reprocessSettingsValid}
                      <div class="reprocess-validation-error">
                        {$t('reprocess.validationError')}
                      </div>
                    {/if}

                    <div class="reprocess-settings-actions">
                      <button class="btn-cancel" on:click={closeReprocessDropdown}>
                        {$t('reprocess.cancel')}
                      </button>
                      <button
                        class="btn-confirm"
                        on:click={handleReprocessHeader}
                        disabled={reprocessing || !reprocessSettingsValid}
                      >
                        {$t('reprocess.start')}
                      </button>
                    </div>
                  {/if}
                </div>
              {/if}
            </div>
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
          {speakerList}
          on:retry={handleVideoRetry}
          on:timeupdate={handleTimeUpdate}
          on:play={handlePlay}
          on:pause={handlePause}
          on:loadedmetadata={handleLoadedMetadata}
        />

        <!-- Waveform visualization -->
        {#if file && file.uuid && (file.content_type?.startsWith('audio/') || file.content_type?.startsWith('video/')) && file.status === 'completed'}
          <div class="waveform-section">
            <WaveformPlayer
              fileId={file.uuid}
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
          {aiTagSuggestions}
          on:tagsUpdated={handleTagsUpdated}
        />

        <CollectionsSection
          bind:collections
          fileId={file?.uuid}
          bind:isExpanded={isCollectionsExpanded}
          {aiCollectionSuggestions}
          on:collectionsUpdated={handleCollectionsUpdated}
        />


        <AnalyticsSection
          {file}
          bind:isAnalyticsExpanded
          {speakerList}
          transcriptStore={$transcriptStore}
        />

        <CommentSection
          fileId={file?.uuid ? String(file.uuid) : ''}
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
          {loadingVoiceSuggestions}
          {speakerNamesChanged}
          {editingSegmentId}
          bind:editingSegmentText
          {isEditingSpeakers}
          {speakerList}
          {reprocessing}
          {totalSegments}
          {hasMoreSegments}
          {loadingMoreSegments}
          on:segmentClick={handleSegmentClick}
          on:editSegment={handleEditSegment}
          on:saveSegment={handleSaveSegment}
          on:cancelEditSegment={handleCancelEditSegment}
          on:saveTranscript={handleSaveTranscript}
          on:exportTranscript={handleExportTranscript}
          on:saveSpeakerNames={handleSaveSpeakerNames}
          on:speakerUpdate={handleSpeakerUpdate}
          on:speakerNameChanged={handleSpeakerNameChanged}
          on:speakersMerged={handleSpeakersMerged}
          on:speakerCreated={handleSpeakerCreated}
          on:speakerDeleted={handleSpeakerDeleted}
          on:analyticsRefreshNeeded={handleAnalyticsRefreshNeeded}
          on:reprocess={handleReprocess}
          on:seekToPlayhead={handleSeekTo}
          on:loadMore={loadMoreSegments}
        />
        </section>
      {:else}
        <section class="transcript-column">
          <div class="no-transcript">
            {#if file?.status === 'processing' || file?.status === 'pending'}
              <div class="processing-placeholder">
                <div class="spinner-large"></div>
                <p>{$t('fileDetail.generatingTranscript')}</p>
                <small>{$t('fileDetail.generatingTranscriptHint')}</small>
              </div>
            {:else}
              <p>{$t('fileDetail.noTranscript')}</p>
            {/if}
          </div>
        </section>
      {/if}
    </div>

  {:else}
    <div class="no-file-container">
      <p>{$t('fileDetail.fileNotFound')}</p>
    </div>
  {/if}
</div>

<!-- Export Confirmation Modal -->
<ConfirmationModal
  bind:isOpen={showExportConfirmation}
  title={$t('exportConfirm.title')}
  message={$t('exportConfirm.message')}
  confirmText={$t('exportConfirm.includeComments')}
  cancelText={$t('exportConfirm.exportWithout')}
  on:confirm={handleExportConfirm}
  on:cancel={handleExportCancel}
  on:close={handleExportModalClose}
/>

<!-- Speaker Profile Confirmation Modal -->
{#if showSpeakerProfileConfirmation}
  <div class="modal-overlay">
    <div class="modal-dialog">
      <div class="modal-content">
        <div class="modal-header">
          <h2 class="modal-title">{profileUpdateTitle}</h2>
          <button
            class="modal-close-btn"
            on:click={handleProfileConfirmationCancel}
            aria-label={$t('modal.closeDialog')}
          >
            ×
          </button>
        </div>

        <div class="modal-body">
          <p class="modal-message">{profileUpdateMessage}</p>
        </div>

        <div class="modal-footer">
          <button
            class="btn btn-primary"
            on:click={() => handleProfileConfirmation('update_profile')}
          >
            {$t('speakerProfile.updateGlobally')}
          </button>
          <button
            class="btn btn-secondary"
            on:click={() => handleProfileConfirmation('create_new_profile')}
          >
            {$t('speakerProfile.createNew')}
          </button>
          <button
            class="btn btn-cancel"
            on:click={handleProfileConfirmationCancel}
          >
            {$t('common.cancel')}
          </button>
        </div>
      </div>
    </div>
  </div>
{/if}

<!-- Summary Modal -->
{#if file?.uuid}
  <SummaryModal
    bind:isOpen={showSummaryModal}
    fileId={file.uuid}
    fileName={file?.filename || 'Unknown File'}
    on:close={() => showSummaryModal = false}
    on:reprocessSummary={async (_event) => {
      // 1. Close modal immediately
      showSummaryModal = false;

      // 2. Update button to show spinner state
      summaryGenerating = true;

      // 3. Clear the summary from file object to trigger "generating" button state
      if (file) {
        file.summary_data = null;
        file.summary_opensearch_id = null;
        file = { ...file }; // Trigger reactivity
      }

      // 4. Trigger the API call for reprocessing
      try {
        await axiosInstance.post(`/api/files/${file.uuid}/summarize`, {
          force_regenerate: true
        });

        // WebSocket will handle the rest of the status updates
      } catch (error) {
        console.error('Failed to start reprocess:', error);
        toastStore.error($t('fileDetail.failedToStartSummaryReprocess'), 5000);
        summaryGenerating = false;
      }
    }}
  />
{/if}

<!-- Transcript Modal -->
{#if file?.uuid}
  <TranscriptModal
    bind:isOpen={showTranscriptModal}
    fileId={file.uuid}
    fileName={file?.filename || 'Unknown File'}
    {totalSegments}
    {hasMoreSegments}
    {loadingMoreSegments}
    on:close={() => showTranscriptModal = false}
    on:loadMore={loadMoreSegments}
  />
{/if}

<style>
  div.file-detail-page {
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
    gap: 0.5rem;
    flex-wrap: wrap;
    justify-content: flex-end;
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

  .reprocess-dropdown-container {
    position: relative;
    z-index: 1000;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .reprocess-settings-dropdown {
    position: absolute;
    top: 100%;
    right: 0;
    margin-top: 0.5rem;
    width: 320px;
    padding: 1rem;
    background-color: var(--card-background);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    z-index: 1001;
    animation: slideDown 0.15s ease;
  }

  @keyframes slideDown {
    from {
      opacity: 0;
      transform: translateY(-8px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  /* Confirmation content */
  .reprocess-confirmation-content {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .reprocess-confirmation-info {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.75rem;
    background-color: rgba(59, 130, 246, 0.08);
    border: 1px solid rgba(59, 130, 246, 0.2);
    border-radius: 6px;
  }

  .reprocess-confirmation-info svg {
    color: var(--primary-color, #3b82f6);
    flex-shrink: 0;
  }

  .reprocess-confirmation-message {
    font-size: 0.85rem;
    color: var(--text-primary);
  }

  .reprocess-confirmation-actions {
    display: flex;
    gap: 0.5rem;
    justify-content: flex-end;
  }

  .reprocess-settings-header {
    margin-bottom: 1rem;
  }

  .reprocess-settings-header h4 {
    margin: 0 0 0.25rem 0;
    font-size: 0.95rem;
    font-weight: 600;
    color: var(--text-primary);
  }

  .reprocess-settings-header p {
    margin: 0;
    font-size: 0.8rem;
    color: var(--text-secondary);
  }

  .reprocess-settings-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.75rem;
    margin-bottom: 0.75rem;
  }

  .reprocess-setting-field {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    margin-bottom: 0.75rem;
  }

  .reprocess-setting-field label {
    font-size: 0.85rem;
    font-weight: 500;
    color: var(--text-primary);
  }

  .reprocess-setting-field .setting-hint {
    font-size: 0.75rem;
    font-weight: 400;
    color: var(--text-secondary);
    display: block;
  }

  .reprocess-setting-field input {
    padding: 0.5rem;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    background-color: var(--input-background, var(--card-background));
    color: var(--text-primary);
    font-size: 0.9rem;
  }

  .reprocess-setting-field input:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.1);
  }

  .reprocess-setting-field input:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    background-color: var(--disabled-background, #f5f5f5);
  }

  :global(.dark) .reprocess-setting-field input:disabled {
    background-color: rgba(255, 255, 255, 0.05);
  }

  .reprocess-setting-field input::placeholder {
    color: var(--text-light);
  }

  .reprocess-validation-error {
    padding: 0.5rem;
    background-color: rgba(239, 68, 68, 0.1);
    border: 1px solid rgba(239, 68, 68, 0.3);
    border-radius: 6px;
    color: #dc2626;
    font-size: 0.8rem;
    margin-bottom: 0.75rem;
  }

  :global(.dark) .reprocess-validation-error {
    background-color: rgba(239, 68, 68, 0.15);
    color: #f87171;
  }

  .reprocess-settings-actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
    margin-top: 0.5rem;
  }

  .reprocess-settings-actions .btn-cancel,
  .reprocess-confirmation-actions .btn-cancel {
    padding: 0.4rem 0.8rem;
    background: #6b7280;
    border: 1px solid #6b7280;
    border-radius: 10px;
    color: white;
    font-size: 0.85rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }

  .reprocess-settings-actions .btn-cancel:hover,
  .reprocess-confirmation-actions .btn-cancel:hover {
    background: #4b5563;
    border-color: #4b5563;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(75, 85, 99, 0.25);
  }

  .reprocess-settings-actions .btn-cancel:active,
  .reprocess-confirmation-actions .btn-cancel:active {
    transform: translateY(0);
    box-shadow: 0 2px 4px rgba(75, 85, 99, 0.2);
  }

  .reprocess-settings-actions .btn-confirm,
  .reprocess-confirmation-actions .btn-confirm {
    padding: 0.4rem 0.8rem;
    background: #3b82f6;
    color: white;
    border: none;
    border-radius: 10px;
    font-size: 0.85rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }

  .reprocess-settings-actions .btn-confirm:hover:not(:disabled),
  .reprocess-confirmation-actions .btn-confirm:hover:not(:disabled) {
    background: #2563eb;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }

  .reprocess-settings-actions .btn-confirm:active:not(:disabled),
  .reprocess-confirmation-actions .btn-confirm:active:not(:disabled) {
    transform: translateY(0);
  }

  .reprocess-settings-actions .btn-confirm:disabled,
  .reprocess-confirmation-actions .btn-confirm:disabled {
    opacity: 0.6;
    cursor: not-allowed;
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

  .spinner-small {
    border: 2px solid rgba(255, 255, 255, 0.3);
    border-top: 2px solid white;
    border-radius: 50%;
    width: 14px;
    height: 14px;
    animation: spin 1s linear infinite;
    flex-shrink: 0;
  }

  .waveform-section {
    width: 100%;
  }


  @media (max-width: 1024px) {
    .main-content-grid {
      grid-template-columns: 1fr;
      gap: 24px;
    }
  }

  @media (max-width: 768px) {
    div.file-detail-page {
      padding: 1rem;
    }

    .main-content-grid {
      gap: 20px;
    }
  }

  /* Transcript segment highlighting styles */
  :global(.transcript-segment .segment-content) {
    border: 1px solid transparent;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0);
    transition: all 0.2s ease;
  }

  :global(.transcript-segment.active-segment .segment-content) {
    background-color: rgba(59, 130, 246, 0.12);
    border-color: rgba(59, 130, 246, 0.3);
    box-shadow: 0 1px 3px rgba(59, 130, 246, 0.2);
  }

  :global(.transcript-segment.active-segment .segment-content:hover) {
    background-color: rgba(59, 130, 246, 0.16);
    border-color: rgba(59, 130, 246, 0.4);
  }

  /* All Plyr styling is now handled in VideoPlayer.svelte */

  /* Speaker Profile Confirmation Modal */
  .modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    padding: 1rem;
  }

  .modal-dialog {
    background: var(--background-color);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    max-width: 500px;
    width: 100%;
    overflow: hidden;
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
    animation: slideIn 0.2s ease-out;
  }

  @keyframes slideIn {
    from {
      opacity: 0;
      transform: translateY(-20px) scale(0.95);
    }
    to {
      opacity: 1;
      transform: translateY(0) scale(1);
    }
  }

  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1.5rem;
    border-bottom: 1px solid var(--border-color);
  }

  .modal-title {
    margin: 0;
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--text-color);
    line-height: 1.4;
  }

  .modal-close-btn {
    background: none;
    border: none;
    cursor: pointer;
    padding: 0.5rem;
    color: var(--text-secondary);
    transition: color 0.2s ease;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.5rem;
    line-height: 1;
  }

  .modal-close-btn:hover {
    color: var(--text-color);
    background: var(--button-hover);
  }

  .modal-body {
    padding: 1.5rem;
  }

  .modal-message {
    margin: 0;
    color: var(--text-secondary);
    line-height: 1.5;
    font-size: 0.95rem;
  }

  .modal-footer {
    display: flex;
    gap: 0.75rem;
    padding: 1rem 1.5rem 1.5rem;
    justify-content: flex-end;
    border-top: 1px solid var(--border-color);
    flex-wrap: wrap;
  }

  .btn {
    padding: 0.6rem 1.2rem;
    border: none;
    border-radius: 10px;
    font-size: 0.95rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    min-width: 120px;
  }

  .btn-primary {
    background: #3b82f6;
    color: white;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }

  .btn-primary:hover {
    background: #2563eb;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }

  .btn-primary:active {
    transform: translateY(0);
  }

  .btn-secondary {
    background: var(--success-color);
    color: white;
    box-shadow: 0 2px 4px rgba(16, 185, 129, 0.2);
  }

  .btn-secondary:hover {
    background: #059669; /* Darker green to match app pattern */
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(16, 185, 129, 0.3);
  }

  .btn-cancel {
    background: var(--card-background);
    color: var(--text-color);
    border: 1px solid var(--border-color);
    box-shadow: var(--card-shadow);
  }

  .btn-cancel:hover {
    background: var(--button-hover);
    border-color: var(--primary-color);
    transform: translateY(-1px);
  }

  /* Responsive design */
  @media (max-width: 480px) {
    .modal-dialog {
      margin: 1rem;
      max-width: none;
    }

    .modal-footer {
      flex-direction: column-reverse;
    }

    .btn {
      width: 100%;
    }
  }

  /* Dark mode adjustments */
  :global([data-theme='dark']) .modal-overlay {
    background: rgba(0, 0, 0, 0.7);
  }

  :global([data-theme='dark']) .modal-dialog {
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3), 0 10px 10px -5px rgba(0, 0, 0, 0.2);
  }

</style>
