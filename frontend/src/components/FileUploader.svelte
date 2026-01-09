<script lang="ts">
  import { createEventDispatcher, onMount, onDestroy } from 'svelte';
  import axiosInstance from '../lib/axios';
  import type { AxiosProgressEvent, CancelTokenSource } from 'axios';
  import axios from 'axios';
  import ConfirmationModal from './ConfirmationModal.svelte';
  import AudioExtractionModal from './AudioExtractionModal.svelte';
  import BulkAudioExtractionModal from './BulkAudioExtractionModal.svelte';

  // Import global recording store
  import { recordingStore, recordingManager, hasActiveRecording, isRecording, recordingDuration, audioLevel, recordingStartTime } from '../stores/recording';

  // Import upload store for background uploads
  import { uploadsStore } from '../stores/uploads';
  import { toastStore } from '../stores/toast';
  import { settingsModalStore } from '../stores/settingsModalStore';
  import { loadProtectedMediaAuthConfig, getAuthConfigForHost, type ProtectedMediaAuthConfig } from '../lib/services/configService';

  // Import audio extraction types, service, and settings API
  import type { ExtractedAudio } from '../lib/types/audioExtraction';
  import { getAudioExtractionSettings, type AudioExtractionSettings } from '../lib/api/audioExtractionSettings';
  import { audioExtractionService } from '../lib/services/audioExtractionService';

  // Import transcription settings API
  import {
    getTranscriptionSettings,
    getTranscriptionSystemDefaults,
    type TranscriptionSettings,
    type TranscriptionSystemDefaults,
    type SpeakerPromptBehavior,
    DEFAULT_TRANSCRIPTION_SETTINGS
  } from '../lib/api/transcriptionSettings';

  // Import network connectivity store
  import { isOnline } from '../stores/network';

  // Import i18n for translations
  import { t } from '../stores/locale';

  // Derived stores for additional recording state
  $: recordedBlob = $recordingStore.recordedBlob;
  $: recordingError = $recordingStore.recordingError;
  $: recordingSupported = $recordingStore.recordingSupported;
  $: audioDevices = $recordingStore.audioDevices;
  $: selectedDeviceId = $recordingStore.selectedDeviceId;
  $: isPaused = $recordingStore.isPaused;

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
  let activeTab: 'file' | 'url' | 'record' = 'file';
  let file: FileWithSize | null = null;
  let fileInput: HTMLInputElement;
  let drag = false;
  let uploading = false;
  let progress = 0;
  let error = '';
  let statusMessage = '';
  let isDuplicateFile = false; // Track if the current file is a duplicate
  let duplicateFileId: string | null = null; // Track the UUID of the duplicate file
  let cancelTokenSource: CancelTokenSource | null = null;
  let isCancelling = false;
  let currentFileId: string | null = null; // Track the current file UUID for cancellation
  let token = ''; // Store the auth token

  // URL processing state (no inline messages - use toast notifications only)
  let mediaUrl = '';
  let processingUrl = false;

  // Local recording UI state
  let showRecordingInfo = false;
  let showRecordingWarningModal = false;
  let pendingNavigationAction: (() => void) | null = null;

  // Audio extraction modal state
  let showAudioExtractionModal = false;
  let videoFileForExtraction: File | null = null;
  let audioExtractionSettings: AudioExtractionSettings | null = null;

  // Bulk audio extraction modal state
  let showBulkAudioExtractionModal = false;
  let bulkVideosToExtract: File[] = [];
  let bulkRegularFiles: File[] = [];

  // Upload speed calculation variables
  let lastLoaded = 0;
  let lastTime = Date.now();
  let estimatedTimeRemaining = '';
  let uploadStartTime = 0;

  // Speaker diarization settings
  let showAdvancedSettings = false;
  let minSpeakers: number | null = null;
  let maxSpeakers: number | null = null;
  let numSpeakers: number | null = null;

  // User transcription preferences
  let transcriptionSettings: TranscriptionSettings | null = null;
  let transcriptionSystemDefaults: TranscriptionSystemDefaults | null = null;
  let userHasManuallyToggledSettings = false; // Track if user manually expanded/collapsed

  // Reactive validation for speaker settings - ensure values are >= 1 if set
  $: if (minSpeakers !== null && minSpeakers < 1) minSpeakers = 1;
  $: if (maxSpeakers !== null && maxSpeakers < 1) maxSpeakers = 1;
  $: if (numSpeakers !== null && numSpeakers < 1) numSpeakers = 1;

  // Cleanup references for onDestroy
  let dragDropCleanup: (() => void) | null = null;
  let handleSetTabEvent: ((event: Event) => void) | null = null;
  let handleDirectUpload: ((event: Event) => void) | null = null;

  // Get token from localStorage on component mount
  onMount(() => {
    token = localStorage.getItem('token') || '';
    dragDropCleanup = initDragAndDrop();
    // Fire-and-forget: load protected media auth config for URL uploads
    void loadProtectedMediaAuthConfig();
    loadRecordingSettings();

    // Load audio extraction settings (async, no return value needed)
    (async () => {
      try {
        audioExtractionSettings = await getAudioExtractionSettings();
      } catch (err) {
        console.error('Failed to load audio extraction settings:', err);
        // Use default settings if loading fails
        audioExtractionSettings = {
          auto_extract_enabled: true,
          extraction_threshold_mb: 100,
          remember_choice: false,
          show_modal: true,
        };
      }
    })();

    // Load transcription settings (user preferences and system defaults)
    (async () => {
      try {
        const [userSettings, systemDefaults] = await Promise.all([
          getTranscriptionSettings(),
          getTranscriptionSystemDefaults()
        ]);
        transcriptionSettings = userSettings;
        transcriptionSystemDefaults = systemDefaults;

        // Apply initial behavior based on user preference
        applyTranscriptionPreferences();
      } catch (err) {
        console.error('Failed to load transcription settings:', err);
        // Use client-side defaults if loading fails
        transcriptionSettings = { ...DEFAULT_TRANSCRIPTION_SETTINGS };
        transcriptionSystemDefaults = {
          min_speakers: 1,
          max_speakers: 20,
          garbage_cleanup_enabled: true,
          garbage_cleanup_threshold: 50,
          valid_speaker_prompt_behaviors: ['always_prompt', 'use_defaults', 'use_custom'],
          available_source_languages: { auto: 'Auto-detect', en: 'English' },
          available_llm_output_languages: { en: 'English' },
          common_languages: ['auto', 'en'],
          languages_with_alignment: ['en']
        };
      }
    })();

    // Listen for events to set active tab
    handleSetTabEvent = (event: Event) => {
      const customEvent = event as CustomEvent;
      if (customEvent.detail?.activeTab) {
        activeTab = customEvent.detail.activeTab;
        // Tab change is handled by reactive updates
      }
    };

    // Listen for direct file upload from recording popup
    handleDirectUpload = (event: Event) => {
      const customEvent = event as CustomEvent;
      if (customEvent.detail?.file) {
        file = customEvent.detail.file;
        activeTab = 'file';
        // Trigger upload immediately
        setTimeout(() => {
          uploadFile();
        }, 100);
      }
    };

    window.addEventListener('setFileUploaderTab', handleSetTabEvent);
    window.addEventListener('directFileUpload', handleDirectUpload);
  });

  onDestroy(() => {
    if (dragDropCleanup) dragDropCleanup();
    if (handleSetTabEvent) window.removeEventListener('setFileUploaderTab', handleSetTabEvent);
    if (handleDirectUpload) window.removeEventListener('directFileUpload', handleDirectUpload);
  });

  // Event dispatcher with proper types
  const dispatch = createEventDispatcher<{
    uploadComplete: {
      fileId?: string;  // UUID
      uploadId?: string;
      isDuplicate?: boolean;
      isUrl?: boolean;
      multiple?: boolean;
      count?: number;
      isRecording?: boolean;
      isFile?: boolean;
    };
    uploadError: { error: string };
  }>();

  // URL validation regex - accepts any HTTP/HTTPS URL
  const MEDIA_URL_REGEX = /^https?:\/\/.+$/;

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

  // Recording settings - loaded from user preferences
  let maxRecordingDuration = 2 * 60 * 60; // Default 2 hours in seconds
  let recordingQuality = 'high';
  let autoStopEnabled = true;

  const RECORDING_OPTIONS = {
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
      sampleRate: 44100
    },
    video: false
  };

  // Load recording settings from localStorage
  function loadRecordingSettings() {
    const settings = localStorage.getItem('recordingSettings');
    if (settings) {
      try {
        const parsed = JSON.parse(settings);
        maxRecordingDuration = (parsed.maxRecordingDuration || 120) * 60; // Convert minutes to seconds
        recordingQuality = parsed.recordingQuality || 'high';
        autoStopEnabled = parsed.autoStopEnabled !== undefined ? parsed.autoStopEnabled : true;
      } catch (err) {
        // Recording settings loading failed - using defaults
      }
    }
  }

  /**
   * Apply transcription preferences based on user settings.
   * Called on component mount and when a file is selected.
   *
   * Behavior based on speaker_prompt_behavior:
   * - "always_prompt": Auto-expand Advanced Settings, pre-fill with user's saved values
   * - "use_defaults": Hide Advanced Settings, use null values (backend uses system defaults)
   * - "use_custom": Hide Advanced Settings, use user's saved min/max values
   */
  function applyTranscriptionPreferences() {
    if (!transcriptionSettings || userHasManuallyToggledSettings) {
      return; // Don't override if user has manually changed settings
    }

    const behavior = transcriptionSettings.speaker_prompt_behavior;

    switch (behavior) {
      case 'always_prompt':
        // Auto-expand and pre-fill with user's saved values (or null if not set)
        showAdvancedSettings = true;
        minSpeakers = transcriptionSettings.min_speakers || null;
        maxSpeakers = transcriptionSettings.max_speakers || null;
        break;

      case 'use_defaults':
        // Keep settings collapsed, use null (backend applies system defaults)
        showAdvancedSettings = false;
        minSpeakers = null;
        maxSpeakers = null;
        break;

      case 'use_custom':
        // Keep settings collapsed, pre-fill with user's saved values
        showAdvancedSettings = false;
        minSpeakers = transcriptionSettings.min_speakers || null;
        maxSpeakers = transcriptionSettings.max_speakers || null;
        break;

      default:
        // Fallback: show settings panel
        showAdvancedSettings = false;
    }
  }

  /**
   * Handle manual toggle of Advanced Settings panel.
   * Once user manually toggles, we don't auto-apply preferences anymore.
   */
  function toggleAdvancedSettings() {
    userHasManuallyToggledSettings = true;
    showAdvancedSettings = !showAdvancedSettings;
  }

  /**
   * Get the effective speaker settings for upload based on user preferences.
   * Returns the values to pass to the upload API.
   */
  function getEffectiveSpeakerSettings(): { minSpeakers: number | null; maxSpeakers: number | null; numSpeakers: number | null } {
    // If user manually interacted with settings, use current form values
    if (userHasManuallyToggledSettings) {
      return { minSpeakers, maxSpeakers, numSpeakers };
    }

    // Otherwise, apply behavior based on preferences
    if (!transcriptionSettings) {
      return { minSpeakers, maxSpeakers, numSpeakers };
    }

    const behavior = transcriptionSettings.speaker_prompt_behavior;

    switch (behavior) {
      case 'use_defaults':
        // Return null to let backend use system defaults
        return { minSpeakers: null, maxSpeakers: null, numSpeakers: null };

      case 'use_custom':
        // Use user's saved preferences
        return {
          minSpeakers: transcriptionSettings.min_speakers || null,
          maxSpeakers: transcriptionSettings.max_speakers || null,
          numSpeakers: null
        };

      case 'always_prompt':
      default:
        // Use current form values (user should have seen/modified them)
        return { minSpeakers, maxSpeakers, numSpeakers };
    }
  }

  /**
   * Reset the transcription preferences state when a new file is selected.
   * This allows the automatic behavior to re-apply.
   */
  function resetTranscriptionPreferencesState() {
    userHasManuallyToggledSettings = false;
    numSpeakers = null;
    applyTranscriptionPreferences();
  }

  // Start recording using global recording manager
  async function startRecording() {
    try {
      await recordingManager.startRecording();
    } catch (err) {
      console.error('Recording error:', err);
    }
  }

  // Stop recording using global recording manager
  function stopRecording() {
    recordingManager.stopRecording();
  }

  // Pause/resume recording using global recording manager
  function togglePauseRecording() {
    let currentState: any;
    const unsubscribe = recordingStore.subscribe(state => currentState = state);
    unsubscribe();

    if (currentState?.isPaused) {
      recordingManager.resumeRecording();
    } else {
      recordingManager.pauseRecording();
    }
  }


  // Format recording duration
  function formatDuration(seconds: number): string {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;

    if (hours > 0) {
      return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
  }

  // Upload recorded audio using global recording manager
  async function uploadRecordedAudio() {
    const recordedBlob = recordingManager.getRecordedBlob();
    if (!recordedBlob) {
      return;
    }

    try {
      // Use background upload service for recording
      const filename = `recording_${new Date().toISOString().replace(/[:.]/g, '-')}.webm`;
      const uploadId = uploadsStore.addRecording(recordedBlob, filename);

      // Clear recording state when starting upload
      recordingManager.clearRecording();

      // Clear any UI state
      file = null;
      error = '';

      // Dispatch upload event
      dispatch('uploadComplete', { uploadId, isRecording: true });

      // Show success toast
      toastStore.success($t('uploader.recordingAddedToQueue'));

    } catch (error) {
      console.error('Error adding recording to upload queue:', error);
      toastStore.error($t('uploader.failedToAddToQueue'));
    }
  }

  // Clear recording using global recording manager
  function clearRecording() {
    recordingManager.clearRecording();
  }

  // Handle device selection change
  function handleDeviceChange(event: Event) {
    const target = event.target as HTMLSelectElement;
    recordingStore.update(state => ({
      ...state,
      selectedDeviceId: target.value
    }));
  }

  // Reset recording state with protection check
  function resetRecordingState() {
    // Only reset if no active recording in progress
    let currentState: any;
    const unsubscribe = recordingStore.subscribe(state => currentState = state);
    unsubscribe();

    if (!currentState?.hasActiveRecording) {
      recordingManager.clearRecording();
    }
  }

  // Recording warning modal handlers
  function handleRecordingWarningConfirm() {
    // User confirmed to discard recording
    recordingManager.clearRecording();

    if (pendingNavigationAction) {
      pendingNavigationAction();
      pendingNavigationAction = null;
    }
    showRecordingWarningModal = false;
  }

  function handleRecordingWarningCancel() {
    pendingNavigationAction = null;
    showRecordingWarningModal = false;
  }

  // Audio extraction modal handlers
  function handleAudioExtractionStarted() {
    // Extraction has started - close upload modal immediately and clear state
    file = null;
    videoFileForExtraction = null;
    showAudioExtractionModal = false;
    if (fileInput) {
      fileInput.value = '';
    }

    // Dispatch upload complete to close the upload modal
    // Don't pass uploadId since extraction is still running
    dispatch('uploadComplete', { isFile: true });
  }

  function handleAudioExtractionConfirm(event: CustomEvent<{ extractedAudio: ExtractedAudio }>) {
    const { extractedAudio } = event.detail;

    // Add extracted audio to upload queue
    const uploadId = uploadsStore.addExtractedAudio(
      extractedAudio.blob,
      extractedAudio.filename,
      extractedAudio.metadata,
      extractedAudio.metadata.compressionRatio
    );

    // Show success message
    toastStore.success($t('uploader.audioExtractedSuccess', { ratio: extractedAudio.metadata.compressionRatio }));
  }

  function handleAudioExtractionUploadFull() {
    // User chose to upload full video instead
    if (videoFileForExtraction) {
      file = videoFileForExtraction;
      videoFileForExtraction = null;
      showAudioExtractionModal = false;

      // Trigger normal upload flow
      uploadFile();
    }
  }

  function handleAudioExtractionCancel() {
    // User clicked X button - clear file selection completely and reset to fresh dropzone
    videoFileForExtraction = null;
    file = null;
    error = ''; // Clear any error messages
    showAudioExtractionModal = false;
    // Clear the file input element so selection is visually cleared
    if (fileInput) {
      fileInput.value = '';
    }
  }

  // Bulk audio extraction modal handlers
  function handleBulkExtractionConfirm() {
    showBulkAudioExtractionModal = false;

    // Add regular files to upload queue
    if (bulkRegularFiles.length > 0) {
      uploadsStore.addFiles(bulkRegularFiles);
    }

    // Start extracting audio from large videos
    if (bulkVideosToExtract.length > 0) {
      startBulkExtraction(bulkVideosToExtract);
    }

    // Close upload modal and show success
    dispatch('uploadComplete', { multiple: true, count: bulkVideosToExtract.length + bulkRegularFiles.length });

    const regularCount = bulkRegularFiles.length;
    const extractCount = bulkVideosToExtract.length;

    if (regularCount > 0 && extractCount > 0) {
      toastStore.success($t('uploader.addedToQueue', { count: regularCount, extractCount: extractCount }));
    } else if (extractCount > 0) {
      toastStore.success($t('uploader.extractingAudioOnly', { count: extractCount }));
    }

    // Clear state
    bulkVideosToExtract = [];
    bulkRegularFiles = [];
  }

  function handleBulkUploadAllFull() {
    showBulkAudioExtractionModal = false;

    // Upload all files as-is (no extraction)
    const allFiles = [...bulkVideosToExtract, ...bulkRegularFiles];
    if (allFiles.length > 0) {
      uploadsStore.addFiles(allFiles);
    }

    // Close upload modal and show success
    dispatch('uploadComplete', { multiple: true, count: allFiles.length });
    toastStore.success($t('uploader.addedToQueueOnly', { count: allFiles.length }));

    // Clear state
    bulkVideosToExtract = [];
    bulkRegularFiles = [];
  }

  function handleBulkExtractionCancel() {
    showBulkAudioExtractionModal = false;
    bulkVideosToExtract = [];
    bulkRegularFiles = [];
  }

  // Helper function to start bulk extraction
  function startBulkExtraction(videoFiles: File[]) {
    toastStore.info($t('uploader.extractingAudioFrom', { count: videoFiles.length }));

    videoFiles.forEach(async (videoFile) => {
      try {
        const extractedAudio = await audioExtractionService.extractAudio(videoFile);

        // Add extracted audio to upload queue
        uploadsStore.addExtractedAudio(
          extractedAudio.blob,
          extractedAudio.filename,
          extractedAudio.metadata,
          extractedAudio.metadata.compressionRatio
        );
      } catch (error) {
        console.error(`Failed to extract audio from ${videoFile.name}:`, error);
        toastStore.error($t('uploader.failedToExtractAudio', { filename: videoFile.name }));
      }
    });
  }

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
      if (files.length === 1) {
        // Single file - use traditional modal upload
        handleFileSelect(files[0]);
      } else {
        // Multiple files - use background upload service
        handleMultipleFiles(Array.from(files));
      }
    }
  }

  // Handle file selection
  function handleFileSelect(selectedFile: File) {
    error = '';
    file = selectedFile;

    // Reset transcription preferences state to allow auto-behavior for new file
    resetTranscriptionPreferencesState();

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
        error = $t('uploader.fileTypeError');
        file = null;
        return;
      }
    }

    // Check file type
    if (!allowedTypes.some(type => selectedFile.type.startsWith(type.split('/')[0]))) {
      error = $t('uploader.unsupportedTypeError', { type: selectedFile.type });
      return;
    }

    // Check file size
    if (selectedFile.size > MAX_FILE_SIZE) {
      const fileSizeFormatted = formatFileSize(selectedFile.size);
      const maxSizeFormatted = formatFileSize(MAX_FILE_SIZE);
      error = $t('uploader.fileTooLargeError', { fileSize: fileSizeFormatted, maxSize: maxSizeFormatted });
      return;
    }

    // Additional checks for very large files
    if (selectedFile.size > 2 * 1024 * 1024 * 1024) { // > 2GB
      // Warn about potential upload time for very large files
      error = $t('uploader.largeFileWarning', { fileSize: formatFileSize(selectedFile.size) });
      file = selectedFile;
      return;
    }

    // Check if this is a large video file that could benefit from audio extraction
    const isVideo = selectedFile.type.startsWith('video/');
    const thresholdMb = audioExtractionSettings?.extraction_threshold_mb || 100;
    const thresholdBytes = thresholdMb * 1024 * 1024;
    const isLargeFile = selectedFile.size > thresholdBytes;

    // Check if audio extraction is enabled and should be shown
    const shouldShowExtraction =
      audioExtractionSettings?.auto_extract_enabled !== false &&
      isVideo &&
      isLargeFile;

    if (shouldShowExtraction) {
      // Show audio extraction modal for large video files (if show_modal is true)
      if (audioExtractionSettings?.show_modal !== false) {
        videoFileForExtraction = selectedFile;
        showAudioExtractionModal = true;
        return;
      }
      // If show_modal is false, auto-extract would happen here
      // For now, we still show the modal for safety
      videoFileForExtraction = selectedFile;
      showAudioExtractionModal = true;
      return;
    }

    file = selectedFile;
  }

  // Handle multiple files using background upload service
  async function handleMultipleFiles(files: File[]) {
    // Validate each file
    const validFiles: File[] = [];
    const invalidFiles: string[] = [];

    files.forEach(file => {
      // Check file size
      if (file.size > FILE_SIZE_LIMIT) {
        invalidFiles.push(`${file.name} (${$t('uploader.tooLarge', { size: formatFileSize(file.size) })})`);
        return;
      }

      // Check file type
      const isValidType = file.type && (
        file.type.startsWith('audio/') ||
        file.type.startsWith('video/')
      );

      if (!isValidType) {
        // Try to determine type from extension
        const extension = file.name.split('.').pop()?.toLowerCase() || '';
        const validExtensions = [
          'mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a', 'wma', 'opus',
          'mp4', 'avi', 'mov', 'wmv', 'flv', 'webm', 'mkv', '3gp', 'f4v'
        ];

        if (!validExtensions.includes(extension)) {
          invalidFiles.push(`${file.name} (${$t('uploader.unsupportedFormat')})`);
          return;
        }
      }

      validFiles.push(file);
    });

    // Show validation results
    if (invalidFiles.length > 0) {
      toastStore.error($t('uploader.skippedInvalidFiles', { count: invalidFiles.length, files: invalidFiles.join('\n') }));
    }

    if (validFiles.length > 0) {
      // Check for large video files that need audio extraction
      const filesToUpload: File[] = [];
      const videosToExtract: File[] = [];

      const extractionThresholdBytes = (audioExtractionSettings?.extraction_threshold_mb || 100) * 1024 * 1024;
      const autoExtractEnabled = audioExtractionSettings?.auto_extract_enabled !== false;

      validFiles.forEach(file => {
        // Determine if file is a video (check both type and extension)
        let isVideo = file.type && file.type.startsWith('video/');

        if (!isVideo) {
          // Check extension as fallback
          const extension = file.name.split('.').pop()?.toLowerCase() || '';
          const videoExtensions = ['mp4', 'avi', 'mov', 'wmv', 'flv', 'webm', 'mkv', '3gp', 'f4v', 'm4v', 'mpeg', 'mpg', 'ogv'];
          isVideo = videoExtensions.includes(extension);
        }

        const isLargeFile = file.size >= extractionThresholdBytes;

        if (autoExtractEnabled && isVideo && isLargeFile) {
          // Large video file - extract audio
          videosToExtract.push(file);
        } else {
          // Regular file or small video - upload as-is
          filesToUpload.push(file);
        }
      });

      // If there are large videos to extract, show bulk confirmation modal
      if (videosToExtract.length > 0 && audioExtractionSettings?.show_modal !== false) {
        // Store files for modal
        bulkVideosToExtract = videosToExtract;
        bulkRegularFiles = filesToUpload;
        showBulkAudioExtractionModal = true;
        // Don't close upload modal or dispatch uploadComplete yet - wait for user choice
        return;
      }

      // Add regular files to upload queue immediately
      if (filesToUpload.length > 0) {
        uploadsStore.addFiles(filesToUpload);
      }

      // Auto-extract if show_modal is disabled
      if (videosToExtract.length > 0) {
        startBulkExtraction(videosToExtract);
      }

      // Close modal and show success message
      dispatch('uploadComplete', { multiple: true, count: validFiles.length });

      const regularCount = filesToUpload.length;
      const extractCount = videosToExtract.length;

      if (regularCount > 0 && extractCount > 0) {
        toastStore.success($t('uploader.addedToQueue', { count: regularCount, extractCount: extractCount }));
      } else if (regularCount > 0) {
        toastStore.success($t('uploader.addedToQueueOnly', { count: regularCount }));
      } else if (extractCount > 0) {
        toastStore.success($t('uploader.extractingAudioOnly', { count: extractCount }));
      }
    }
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
    const files = target.files;

    if (!files || files.length === 0) return;

    if (files.length === 1) {
      // Single file - use traditional modal upload
      handleFileSelect(files[0]);
    } else {
      // Multiple files - use background upload service
      handleMultipleFiles(Array.from(files));
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

    // Use background upload service for consistency with URLs and multiple files
    try {
      // Get effective speaker parameters based on user preferences
      const effectiveSettings = getEffectiveSpeakerSettings();
      const speakerParams = {
        minSpeakers: effectiveSettings.minSpeakers,
        maxSpeakers: effectiveSettings.maxSpeakers,
        numSpeakers: effectiveSettings.numSpeakers,
      };

      const uploadId = uploadsStore.addFile(file, speakerParams);

      // Clear form and close modal
      file = null;
      minSpeakers = null;
      maxSpeakers = null;
      numSpeakers = null;
      showAdvancedSettings = false;
      userHasManuallyToggledSettings = false; // Reset for next upload
      if (fileInput) fileInput.value = '';
      dispatch('uploadComplete', { uploadId, isFile: true });

      // Show success toast
      toastStore.success($t('uploader.fileAddedToQueue'));

      return;
    } catch (error) {
      console.error('Error adding file to upload queue:', error);
      toastStore.error($t('uploader.failedToAddFileToQueue'));
      return;
    }

    // Legacy direct upload code (kept for reference but not used)
    /*
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

      statusMessage = $t('uploader.preparing');

      // Calculate file hash before upload
      let fileHash = null;
      try {
        statusMessage = $t('uploader.calculatingHashImohash');
        fileHash = await calculateFileHash(file);
        // Strip the 0x prefix for display and database consistency
        const displayHash = fileHash.startsWith('0x') ? fileHash.substring(2) : fileHash;
        statusMessage = $t('uploader.hashCalculated', { hash: displayHash.substring(0, 8) });
        // Remove 0x prefix for backend compatibility
        if (fileHash.startsWith('0x')) {
          fileHash = fileHash.substring(2);
        }
      } catch (err) {
        // If hash calculation fails, show a warning but continue with upload
        statusMessage = $t('uploader.hashWarning');
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
          statusMessage = $t('uploader.duplicateUsing', { fileId: duplicateFileId });
          uploading = false;
          isDuplicateFile = true;

          // Show notification message that this is a duplicate file
          error = $t('uploader.duplicateError');

          // Note: We don't dispatch uploadComplete event here anymore
          // We'll wait for user to acknowledge the message

          return;
        }

        statusMessage = $t('uploader.uploadPrepared', { fileId: currentFileId });
      } catch (err) {
        error = $t('uploader.prepareFailed');
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
              statusMessage = $t('uploader.progress', { loaded: loadedMB, total: totalMB, speed, remaining: timeRemaining });
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
      if (responseData && responseData.uuid) {
        currentFileId = responseData.uuid;
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
        error = $t('uploader.timeout');
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
          error = $t('uploader.fileTooLarge', { size: fileSizeGB });
        } else if (response.status === 401) {
          error = $t('uploader.sessionExpired');
        } else {
          error = response.data?.detail ||
                 response.data?.message ||
                 $t('uploader.serverError', { status: response.status, text: response.statusText || $t('common.unknownError') });
        }
      } else if (err && typeof err === 'object' && 'request' in err) {
        // Request was made but no response received
        error = $t('uploader.noResponse');
      } else {
        // Something else went wrong
        error = (err as Error)?.message || $t('uploader.unknownError');
      }

      // If we have a file and it's large, suggest using a different upload method
      if (file && file.size > 2 * 1024 * 1024 * 1024) { // > 2GB
        error += '\n\n' + $t('uploader.largeFileTip');
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
    */
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

  let mediaUsername: string = '';
  let mediaPassword: string = '';

  let currentAuthConfig: ProtectedMediaAuthConfig | null = null;

  // Derived flag: show username/password fields only for providers
  // that explicitly declare auth_type === 'user_password'.
  $: showProtectedMediaAuth = (() => {
    try {
      const url = new URL(mediaUrl);
      currentAuthConfig = getAuthConfigForHost(url.hostname);
      return currentAuthConfig?.auth_type === 'user_password';
    } catch {
      currentAuthConfig = null;
      return false;
    }
  })();

  // Reset URL processing state
  function resetUrlState() {
    mediaUrl = '';
    mediaUsername = '';
    mediaPassword = '';
    processingUrl = false;
    // URL state reset (no inline messages)
    currentFileId = null;
  }

  // Cancel or clear URL processing
  function cancelUrlProcessing() {
    if (processingUrl) {
      // If actively processing, reset state and notify user
      processingUrl = false;
      toastStore.info($t('uploader.urlProcessingCancelled'));
    }
    // Clear the URL field
    resetUrlState();
  }

  // Switch tabs with recording protection
  function switchTab(tab: 'file' | 'url' | 'record') {
    if (tab === activeTab) return;

    // Allow switching tabs freely - recording continues in background
    activeTab = tab;

    if (tab === 'file') {
      resetUrlState();
    } else if (tab === 'url') {
      resetUploadState();
    } else if (tab === 'record') {
      resetUploadState();
      resetUrlState();
    }
  }


  // Validate media URL - accepts any HTTP/HTTPS URL
  function isValidMediaUrl(url: string): boolean {
    return MEDIA_URL_REGEX.test(url.trim());
  }

  // Paste URL from clipboard - optimized for single-click experience
  async function pasteFromClipboard() {
    try {
      // Check if clipboard API is available
      if (!navigator.clipboard?.readText) {
        fallbackToKeyboardPaste();
        return;
      }

      // Check secure context
      if (!window.isSecureContext) {
        toastStore.info($t('uploader.clipboardRequiresHttps'));
        fallbackToKeyboardPaste();
        return;
      }

      // Attempt direct clipboard read
      const text = await navigator.clipboard.readText();

      if (text && text.trim()) {
        mediaUrl = text.trim();
        // Validation passed
        toastStore.success($t('uploader.pastedFromClipboard'));
      } else {
        toastStore.info($t('uploader.clipboardEmpty'));
        fallbackToKeyboardPaste();
      }

    } catch (error: unknown) {
      // Clipboard read failed - handle gracefully with fallback

      // Handle permission denial gracefully
      if ((error as Error).name === 'NotAllowedError') {
        // Don't show error, just provide seamless fallback
        fallbackToKeyboardPaste();
      } else {
        toastStore.info($t('uploader.useCtrlV'));
        fallbackToKeyboardPaste();
      }
    }
  }

  // Seamless fallback that focuses input for keyboard paste
  function fallbackToKeyboardPaste() {
    const input = document.getElementById('media-url') as HTMLInputElement;
    if (input) {
      input.focus();
      input.select(); // Select any existing text for easy replacement

      // Brief visual feedback that the button worked and input is ready
      setTimeout(() => {
        if (document.activeElement === input) {
          toastStore.info($t('uploader.readyToPaste'));
        }
      }, 100);
    }
  }

  // Process Media URL (YouTube, Vimeo, Twitter/X, TikTok, and 1800+ more)
  async function processMediaUrl() {
    if (!mediaUrl.trim()) {
      toastStore.error($t('uploader.enterMediaUrl'));
      return;
    }

    if (!isValidMediaUrl(mediaUrl)) {
      toastStore.error($t('uploader.invalidMediaUrl'));
      return;
    }

    // Prevent multiple submissions
    if (processingUrl) {
      return;
    }

    processingUrl = true;

    try {
      // Build request payload
      const payload: any = {
        url: mediaUrl.trim()
      };

      // Only send credentials if user explicitly provided them
      if (mediaUsername || mediaPassword) {
        payload.media_username = mediaUsername || undefined;
        payload.media_password = mediaPassword || undefined;
      }

      // Call the API endpoint directly for immediate processing
      const response = await axiosInstance.post('/files/process-url', payload);

      // Get the response data
      const responseData = response.data;

      // Clear form immediately after successful submission
      mediaUrl = '';
      mediaUsername = '';
      mediaPassword = '';

      // Check if this is a playlist or single video response
      if (responseData.type === 'playlist') {
        // Playlist processing started
        dispatch('uploadComplete', { isUrl: true, multiple: true });

        // Show success toast for playlist
        toastStore.success(responseData.message || $t('uploader.playlistProcessingStarted'));
      } else {
        // Single video response (MediaFile object)
        const mediaFile = responseData;

        // Dispatch success event to close modal
        dispatch('uploadComplete', { fileId: mediaFile.uuid, isUrl: true });

        // Show success toast with more descriptive message
        toastStore.success($t('uploader.mediaVideoAdded', { title: mediaFile.title || 'video' }));
      }

    } catch (error: unknown) {
      // Media URL processing error - show user-friendly messages via toast only
      // Errors include platform-specific messages from yt-dlp
      const axiosError = error as any;

      // Handle different types of errors
      if (axiosError.response?.status === 409) {
        // Duplicate video
        toastStore.warning(axiosError.response.data.detail || $t('uploader.duplicateMediaVideo'));
      } else if (axiosError.response?.status === 400) {
        // Bad request (invalid URL, unsupported platform, etc.)
        // The backend returns the actual yt-dlp error message for platform-specific issues
        toastStore.error(axiosError.response.data.detail || $t('uploader.invalidMediaUrl'));
      } else {
        // Other errors
        toastStore.error($t('uploader.failedToProcessUrl'));
      }
    } finally {
      processingUrl = false;
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

    return { speed: '0.0', timeRemaining: $t('uploader.calculating') };
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
      // File hash calculation failed - re-throw for proper error handling
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
      {$t('uploader.uploadFile')}
    </button>
    <button
      class="tab-button {activeTab === 'url' ? 'active' : ''}"
      on:click={() => switchTab('url')}
      disabled={!$isOnline}
      title={$isOnline ? $t('uploader.mediaUrlTooltipOnline') : $t('uploader.mediaUrlTooltipOffline')}
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path>
        <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path>
      </svg>
      {$t('uploader.mediaUrl')}
    </button>
    <button
      class="tab-button {activeTab === 'record' ? 'active' : ''}"
      on:click={() => switchTab('record')}
      disabled={!recordingSupported}
      title={recordingSupported ? $t('uploader.recordAudioTooltipSupported') : $t('uploader.recordAudioTooltipUnsupported')}
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 1a4 4 0 0 0-4 4v7a4 4 0 0 0 8 0V5a4 4 0 0 0-4-4z"></path>
        <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
        <line x1="12" y1="19" x2="12" y2="23"></line>
        <line x1="8" y1="23" x2="16" y2="23"></line>
      </svg>
      {$t('uploader.recordAudio')}
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
        <strong>{$t('uploader.duplicateDetected')}</strong>
        <p>{$t('uploader.duplicateMessage')}</p>
        <div class="message-actions">
          <button class="btn-acknowledge" on:click|stopPropagation={acknowledgeDuplicate}>
            {$t('uploader.useExistingFile')}
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
              {$t('uploader.continueAnyway')}
            </button>
          {/if}
        </div>
      </div>
    </div>
  {/if}

  <!-- File Upload Tab -->
  {#if activeTab === 'file'}
    <div class="file-upload-container">
    {#if !file}
    <div
      id="drop-zone"
      class="drop-zone {drag ? 'active' : ''}"
      on:click={openFileDialog}
      on:keydown={(e) => e.key === 'Enter' && openFileDialog()}
      role="button"
      tabindex="0"
      title={$t('uploader.dropZoneTooltip')}
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
        <polyline points="17 8 12 3 7 8"></polyline>
        <line x1="12" y1="3" x2="12" y2="15"></line>
      </svg>
      <div class="upload-text">
        <span>{$t('uploader.dragDropFiles')}</span>
        <span class="or-text">{$t('uploader.orClickToBrowse')}</span>
        <span class="multi-file-hint">{$t('uploader.multipleFilesSupported')}</span>
      </div>
      <input
        type="file"
        accept="audio/*,video/*"
        multiple
        bind:this={fileInput}
        on:change={handleFileInputChange}
        style="display: none;"
      >
    </div>

    <div class="supported-formats">
      <p>{$t('uploader.supportedFormats')}</p>
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

      <!-- Advanced Settings Panel -->
      <div class="advanced-settings-panel">
        <!-- Show settings info based on user preferences -->
        {#if transcriptionSettings && !userHasManuallyToggledSettings}
          {#if transcriptionSettings.speaker_prompt_behavior === 'use_defaults'}
            <div class="settings-info-note">
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="12" y1="16" x2="12" y2="12"></line>
                <line x1="12" y1="8" x2="12.01" y2="8"></line>
              </svg>
              <span>{$t('uploader.usingSystemDefaults')}{#if transcriptionSystemDefaults} (min: {transcriptionSystemDefaults.min_speakers}, max: {transcriptionSystemDefaults.max_speakers}){/if}</span>
              <button type="button" class="settings-override-link" on:click={toggleAdvancedSettings}>{$t('uploader.customize')}</button>
            </div>
          {:else if transcriptionSettings.speaker_prompt_behavior === 'use_custom'}
            <div class="settings-info-note">
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="12" y1="16" x2="12" y2="12"></line>
                <line x1="12" y1="8" x2="12.01" y2="8"></line>
              </svg>
              <span>{$t('uploader.usingSavedSettings')} (min: {transcriptionSettings.min_speakers}, max: {transcriptionSettings.max_speakers})</span>
              <button type="button" class="settings-override-link" on:click={toggleAdvancedSettings}>{$t('uploader.customize')}</button>
            </div>
          {/if}
        {/if}

        <!-- Toggle button for Advanced Settings -->
        {#if !transcriptionSettings || transcriptionSettings.speaker_prompt_behavior === 'always_prompt' || userHasManuallyToggledSettings || showAdvancedSettings}
          <button
            type="button"
            class="advanced-settings-toggle"
            on:click={toggleAdvancedSettings}
            title={$t('uploader.advancedSettingsTooltip')}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="3"></circle>
              <path d="M12 1v6M12 17v6M4.22 4.22l4.24 4.24M15.54 15.54l4.24 4.24M1 12h6M17 12h6M4.22 19.78l4.24-4.24M15.54 8.46l4.24-4.24"></path>
            </svg>
            {$t('uploader.advancedSettings')}
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="chevron {showAdvancedSettings ? 'open' : ''}">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </button>
        {/if}

        {#if showAdvancedSettings}
          <div class="advanced-settings-content">
            <div class="settings-help-text">
              <p>{$t('uploader.settingsHelpText')}</p>
            </div>

            <div class="settings-row">
              <div class="setting-field">
                <label for="min-speakers">
                  {$t('uploader.minSpeakers')}
                  <span class="setting-hint">{$t('uploader.minSpeakersHint')}</span>
                </label>
                <input
                  id="min-speakers"
                  type="number"
                  min="1"
                  placeholder={transcriptionSystemDefaults ? `${$t('uploader.default')}: ${transcriptionSystemDefaults.min_speakers}` : $t('uploader.usesDefault')}
                  bind:value={minSpeakers}
                  disabled={numSpeakers !== null}
                />
              </div>

              <div class="setting-field">
                <label for="max-speakers">
                  {$t('uploader.maxSpeakers')}
                  <span class="setting-hint">{$t('uploader.maxSpeakersHint')}</span>
                </label>
                <input
                  id="max-speakers"
                  type="number"
                  min="1"
                  placeholder={transcriptionSystemDefaults ? `${$t('uploader.default')}: ${transcriptionSystemDefaults.max_speakers}` : $t('uploader.usesDefault')}
                  bind:value={maxSpeakers}
                  disabled={numSpeakers !== null}
                />
              </div>
            </div>

            <div class="setting-field">
              <label for="num-speakers">
                {$t('uploader.fixedSpeakerCount')}
                <span class="setting-hint">{$t('uploader.fixedSpeakerCountHint')}</span>
              </label>
              <input
                id="num-speakers"
                type="number"
                min="1"
                placeholder={$t('uploader.usesDefault')}
                bind:value={numSpeakers}
              />
            </div>

            {#if minSpeakers !== null && maxSpeakers !== null && minSpeakers > maxSpeakers}
              <div class="validation-error">
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <circle cx="12" cy="12" r="10"></circle>
                  <line x1="12" y1="8" x2="12" y2="12"></line>
                  <line x1="12" y1="16" x2="12.01" y2="16"></line>
                </svg>
                {$t('uploader.minMaxValidationError')}
              </div>
            {/if}
          </div>
        {/if}
      </div>

      <div class="file-actions">
        <button
          type="button"
          class="cancel-button"
          on:click={cancelUpload}
          disabled={isCancelling}
          title={isCancelling ? $t('uploader.cancelling') : $t('uploader.cancelTooltip')}
        >
          {isCancelling ? $t('uploader.cancelling') : $t('common.cancel')}
        </button>
        <button
          class="upload-button"
          on:click={uploadFile}
          disabled={uploading || (minSpeakers !== null && maxSpeakers !== null && minSpeakers > maxSpeakers)}
          title={$t('uploader.uploadTooltip')}
        >
          {uploading ? $t('uploader.uploading') : $t('uploader.upload')}
        </button>
      </div>
      </div>

      {#if uploading}
        <div class="progress-container">
          <div class="progress-header">
            <span class="progress-text">{progress}%</span>
            {#if estimatedTimeRemaining && estimatedTimeRemaining !== 'Calculating...'}
              <span class="time-remaining">{estimatedTimeRemaining} {$t('uploader.remaining')}</span>
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
    </div>
  {:else if activeTab === 'url'}
    <!-- YouTube URL Tab -->
    <div class="url-input-container">
      {#if !$isOnline}
        <div class="message error-message">
          <div class="message-icon">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="15" y1="9" x2="9" y2="15"></line>
              <line x1="9" y1="9" x2="15" y2="15"></line>
            </svg>
          </div>
          <div class="message-content">
            <strong>{$t('uploader.noInternet')}</strong><br />
            {$t('uploader.mediaNeedsInternet')}
          </div>
        </div>
      {/if}
      <div class="url-input-section">
        <label for="media-url" class="url-label">
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path>
            <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path>
          </svg>
          {$t('uploader.mediaUrl')}
        </label>
        <div class="url-input-wrapper">
          <input
            id="media-url"
            type="url"
            placeholder={$t('uploader.mediaUrlPlaceholder')}
            class="url-input"
            bind:value={mediaUrl}
            disabled={processingUrl || !$isOnline}
          />
          <button
            type="button"
            class="paste-button"
            on:click={pasteFromClipboard}
            disabled={processingUrl || !$isOnline}
            title={$t('uploader.pasteTooltip')}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect width="8" height="4" x="8" y="2" rx="1" ry="1"/>
              <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>
              <path d="M12 11h4"/>
              <path d="M12 16h4"/>
              <path d="M8 11h.01"/>
              <path d="M8 16h.01"/>
            </svg>
          </button>
        </div>
        {#if showProtectedMediaAuth}
          <div class="protected-media-auth">
            <div class="protected-media-header">{$t('uploader.protectedMediaCredentialsTitle')}</div>
            <div class="protected-media-fields">
              <div class="protected-media-field">
                <label for="media-username">{$t('uploader.protectedMediaUsernameLabel')}</label>
                <input
                  id="media-username"
                  type="text"
                  class="protected-input"
                  bind:value={mediaUsername}
                  autocomplete="username"
                  disabled={processingUrl || !$isOnline}
                />
              </div>
              <div class="protected-media-field">
                <label for="media-password">{$t('uploader.protectedMediaPasswordLabel')}</label>
                <input
                  id="media-password"
                  type="password"
                  class="protected-input"
                  bind:value={mediaPassword}
                  autocomplete="current-password"
                  disabled={processingUrl || !$isOnline}
                />
              </div>
            </div>
            <p class="protected-media-hint">{$t('uploader.protectedMediaHint')}</p>
          </div>
        {/if}

        <div class="url-actions">
          <button
            type="button"
            class="cancel-url-button"
            on:click={cancelUrlProcessing}
            disabled={isCancelling}
            title={isCancelling ? $t('uploader.cancelling') : (processingUrl ? $t('uploader.cancelProcessing') : $t('uploader.clearUrl'))}
          >
            {isCancelling ? $t('uploader.cancelling') : (processingUrl ? $t('common.cancel') : $t('uploader.clear'))}
          </button>
          <button
            class="process-url-button"
            on:click={processMediaUrl}
            disabled={processingUrl || !mediaUrl.trim() || !$isOnline}
            title={$isOnline ? $t('uploader.processMediaTooltip') : $t('uploader.internetRequired')}
          >
            {processingUrl ? $t('uploader.processing') : $t('uploader.processVideo')}
          </button>
        </div>
      </div>

      <div class="url-info">
        <p class="url-description">
          {$t('uploader.mediaUrlDescription')}
        </p>
        <p class="url-recommendation">
          {$t('uploader.recommendedPlatforms')}
        </p>
        <details class="supported-platforms-details">
          <summary class="supported-platforms-summary">
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="info-icon">
              <circle cx="12" cy="12" r="10"></circle>
              <path d="M12 16v-4"></path>
              <path d="M12 8h.01"></path>
            </svg>
            {$t('uploader.supportedPlatforms')}
          </summary>
          <p class="supported-platforms-list">{$t('uploader.supportedPlatformsList')}</p>
          <p class="platform-limitations">{$t('uploader.platformLimitations')}</p>
        </details>
      </div>
    </div>
  {:else}
    <!-- Recording Tab -->
    <div class="recording-input-container">
      {#if !recordingSupported}
        <div class="message error-message">
          <div class="message-icon">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="8" x2="12" y2="12"></line>
              <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
          </div>
          <div class="message-content">
            {$t('uploader.recordingNotSupported')}
          </div>
        </div>
      {:else}
        <div class="recording-input-section">
          {#if audioDevices.length > 0}
            <div class="device-selector-centered">
              <label for="audio-device-select" class="device-label">
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M12 1a4 4 0 0 0-4 4v7a4 4 0 0 0 8 0V5a4 4 0 0 0-4-4z"></path>
                  <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
                  <line x1="12" y1="19" x2="12" y2="23"></line>
                  <line x1="8" y1="23" x2="16" y2="23"></line>
                </svg>
                {$t('uploader.microphoneDevice')}
              </label>
              <select
                id="audio-device-select"
                class="device-select"
                value={selectedDeviceId}
                on:change={handleDeviceChange}
                disabled={$isRecording}
                title={$t('uploader.selectMicrophoneTooltip')}
              >
                {#each audioDevices as device}
                  <option value={device.deviceId}>
                    {device.label || `${$t('uploader.microphone')} ${audioDevices.indexOf(device) + 1}`}
                  </option>
                {/each}
              </select>
            </div>
          {/if}

          <div class="recording-controls-main">
            {#if !$isRecording && !recordedBlob}
              <button
                class="recording-button primary-button"
                on:click={startRecording}
                title={$t('uploader.startRecordingTooltip', { max: Math.floor(maxRecordingDuration / 60) })}
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M12 1a4 4 0 0 0-4 4v7a4 4 0 0 0 8 0V5a4 4 0 0 0-4-4z"></path>
                  <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
                  <line x1="12" y1="19" x2="12" y2="23"></line>
                  <line x1="8" y1="23" x2="16" y2="23"></line>
                </svg>
                {$t('uploader.startRecording')}
              </button>
            {:else if $isRecording}
              <div class="recording-active-compact">
                <div class="recording-status-row">
                  <div class="recording-indicator-compact">
                    <div class="recording-dot {isPaused ? 'paused' : 'recording'}"></div>
                    <span class="recording-status-text">
                      {isPaused ? $t('uploader.paused') : $t('uploader.recording')}
                    </span>
                    <span class="recording-duration-compact">{formatDuration($recordingDuration)}</span>
                  </div>
                </div>

                <div class="audio-visualizer-compact">
                  <div class="audio-level-meter-horizontal">
                    {#each Array(20) as _, i}
                      <div
                        class="audio-level-bar"
                        class:active="{($audioLevel / 100) * 20 > i}"
                        class:low="{i < 12}"
                        class:medium="{i >= 12 && i < 16}"
                        class:high="{i >= 16}"
                      ></div>
                    {/each}
                  </div>
                </div>

                <div class="recording-controls-row-compact">
                  <button
                    class="control-button-compact pause-button"
                    on:click={togglePauseRecording}
                    title={isPaused ? $t('uploader.resumeRecording') : $t('uploader.pauseRecording')}
                  >
                    {#if isPaused}
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polygon points="5 3 19 12 5 21 5 3"></polygon>
                      </svg>
                    {:else}
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <rect x="6" y="4" width="4" height="16"></rect>
                        <rect x="14" y="4" width="4" height="16"></rect>
                      </svg>
                    {/if}
                  </button>

                  <button
                    class="control-button-compact stop-button"
                    on:click={stopRecording}
                    title={$t('uploader.stopRecording')}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                    </svg>
                  </button>
                </div>
              </div>
            {:else if recordedBlob}
              <div class="recording-complete-compact">
                <div class="recording-info-compact">
                  <div class="recording-details-compact">
                    <span class="recording-title-compact">{$t('uploader.recordingComplete')}</span>
                    <span class="recording-meta-compact">{formatDuration($recordingDuration)} • {(recordedBlob.size / 1024 / 1024).toFixed(1)} MB</span>
                  </div>
                </div>

                <div class="recording-actions-vertical">
                  <button
                    class="control-button-compact upload-recording-button primary-action"
                    on:click={uploadRecordedAudio}
                    disabled={uploading}
                    title={$t('uploader.uploadRecordingTooltip')}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                      <polyline points="17 8 12 3 7 8"></polyline>
                      <line x1="12" y1="3" x2="12" y2="15"></line>
                    </svg>
                    {uploading ? $t('uploader.uploading') : $t('uploader.upload')}
                  </button>

                  <div class="action-separator"></div>

                  <button
                    class="control-button-compact clear-button secondary-action"
                    on:click={clearRecording}
                    title={$t('uploader.clearRecordingTooltip')}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <polyline points="3 6 5 6 21 6"></polyline>
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                    </svg>
                    {$t('uploader.startOver')}
                  </button>
                </div>
              </div>
            {/if}
          </div>

          {#if uploading}
            <div class="progress-container">
              <div class="progress-header">
                <span class="progress-text">{progress}%</span>
                {#if estimatedTimeRemaining && estimatedTimeRemaining !== $t('uploader.calculating')}
                  <span class="time-remaining">{estimatedTimeRemaining} {$t('uploader.remaining')}</span>
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

        </div>

        <div class="recording-settings-section">
          <div class="settings-summary-centered">
            {$t('uploader.recordingSettingsSummary', { max: Math.floor(maxRecordingDuration / 60), quality: recordingQuality, autoStop: autoStopEnabled ? $t('uploader.on') : $t('uploader.off') })}
          </div>
          <div class="settings-link-centered">
            <button
              type="button"
              class="change-settings-link"
              on:click={() => settingsModalStore.open('recording')}
              title={$t('uploader.changeSettingsTooltip')}
            >
              {$t('uploader.changeSettings')}
            </button>
          </div>
        </div>
      {/if}
    </div>
  {/if}
</div>

<!-- Background Recording Indicator -->
{#if $hasActiveRecording && activeTab !== 'record'}
  <div class="background-recording-indicator" title={$t('uploader.recordingInProgress', { seconds: Math.floor((Date.now() - ($recordingStartTime || 0)) / 1000) })}>
    <div class="recording-pulse"></div>
    <span class="recording-indicator-text">{$t('uploader.recording')}...</span>
    <button class="return-to-recording" on:click={() => switchTab('record')} title={$t('uploader.returnToRecording')}>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M12 1a4 4 0 0 0-4 4v7a4 4 0 0 0 8 0V5a4 4 0 0 0-4-4z"></path>
        <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
        <line x1="12" y1="19" x2="12" y2="23"></line>
        <line x1="8" y1="23" x2="16" y2="23"></line>
      </svg>
    </button>
  </div>
{/if}

<!-- Recording Warning Confirmation Modal -->
<ConfirmationModal
  bind:isOpen={showRecordingWarningModal}
  title={$t('uploader.recordingInProgressTitle')}
  message={$t('uploader.recordingWarningMessage')}
  confirmText={$t('uploader.discardRecording')}
  cancelText={$t('uploader.keepRecording')}
  confirmButtonClass="modal-warning-button"
  cancelButtonClass="modal-primary-button"
  on:confirm={handleRecordingWarningConfirm}
  on:cancel={handleRecordingWarningCancel}
/>

<!-- Audio Extraction Modal -->
<AudioExtractionModal
  bind:isOpen={showAudioExtractionModal}
  file={videoFileForExtraction}
  on:extractionStarted={handleAudioExtractionStarted}
  on:confirm={handleAudioExtractionConfirm}
  on:uploadFull={handleAudioExtractionUploadFull}
  on:cancel={handleAudioExtractionCancel}
/>

<!-- Bulk Audio Extraction Modal -->
<BulkAudioExtractionModal
  bind:isOpen={showBulkAudioExtractionModal}
  videoFiles={bulkVideosToExtract}
  regularFiles={bulkRegularFiles}
  on:confirmExtraction={handleBulkExtractionConfirm}
  on:uploadAllFull={handleBulkUploadAllFull}
  on:cancel={handleBulkExtractionCancel}
/>

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
    justify-content: center;
    gap: 0.5rem;
    border-bottom: 1px solid var(--border-color);
    margin-bottom: 1rem;
    padding: 0;
    width: 100%;
    position: relative;
  }

  .tab-navigation::before {
    content: '';
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    height: 1px;
    background-color: var(--border-color);
    z-index: 0;
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
    z-index: 1;
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

  .multi-file-hint {
    color: var(--primary-color);
    font-size: 0.8em;
    font-weight: 500;
    margin-top: 4px;
  }

  .supported-formats {
    text-align: center;
  }

  .supported-formats p {
    margin: 0;
    font-size: 0.875rem;
    color: var(--text-secondary);
  }

  /* Supported platforms collapsible section */
  .supported-platforms-details {
    margin-top: 0.75rem;
    text-align: center;
  }

  .supported-platforms-summary {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    cursor: pointer;
    font-size: 0.8rem;
    color: var(--primary-color);
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    transition: background-color 0.2s ease;
  }

  .supported-platforms-summary:hover {
    background-color: var(--hover-color);
  }

  .supported-platforms-summary .info-icon {
    flex-shrink: 0;
  }

  .supported-platforms-list {
    margin: 0.5rem 0 0;
    padding: 0.75rem;
    font-size: 0.75rem;
    color: var(--text-secondary);
    background-color: var(--surface-alt);
    border-radius: 6px;
    line-height: 1.5;
    text-align: left;
  }

  :global(.dark) .supported-platforms-list {
    background-color: var(--surface-color);
  }

  .url-recommendation {
    margin: 0.5rem 0 0;
    font-size: 0.75rem;
    color: var(--success-color, #10b981);
    font-weight: 500;
    text-align: center;
  }

  .platform-limitations {
    margin: 0.5rem 0 0;
    padding: 0.5rem 0.75rem;
    font-size: 0.7rem;
    color: var(--warning-color, #f59e0b);
    background-color: rgba(245, 158, 11, 0.1);
    border-radius: 4px;
    border-left: 3px solid var(--warning-color, #f59e0b);
    text-align: left;
  }

  :global(.dark) .platform-limitations {
    background-color: rgba(245, 158, 11, 0.15);
  }

  .selected-file {
    padding: 1rem;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    background-color: var(--surface-color);
    display: flex;
    flex-direction: column;
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

  /* Advanced Settings Panel */
  .advanced-settings-panel {
    margin-bottom: 1rem;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    background-color: var(--surface-color);
    overflow: hidden;
  }

  /* Settings info note (shown when using defaults or custom settings) */
  .settings-info-note {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1rem;
    font-size: 0.85rem;
    color: var(--text-secondary);
    background-color: var(--info-background, rgba(59, 130, 246, 0.05));
    border-bottom: 1px solid var(--border-color);
  }

  :global(.dark) .settings-info-note {
    background-color: rgba(59, 130, 246, 0.1);
  }

  .settings-info-note svg {
    flex-shrink: 0;
    color: var(--info-color, #3b82f6);
  }

  .settings-info-note span {
    flex: 1;
  }

  .settings-override-link {
    background: none;
    border: none;
    padding: 0;
    color: var(--primary-color, #3b82f6);
    font-size: 0.85rem;
    font-weight: 500;
    cursor: pointer;
    text-decoration: underline;
    text-underline-offset: 2px;
  }

  .settings-override-link:hover {
    color: var(--primary-color-dark, #2563eb);
  }

  .advanced-settings-toggle {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1rem;
    background: none;
    border: none;
    cursor: pointer;
    color: var(--text-secondary);
    font-size: 0.9rem;
    font-weight: 500;
    transition: all 0.2s ease;
    text-align: left;
  }

  .advanced-settings-toggle:hover {
    color: var(--text-primary);
    background-color: var(--hover-color, rgba(0, 0, 0, 0.02));
  }

  :global(.dark) .advanced-settings-toggle:hover {
    background-color: rgba(255, 255, 255, 0.05);
  }

  .advanced-settings-toggle .chevron {
    margin-left: auto;
    transition: transform 0.2s ease;
  }

  .advanced-settings-toggle .chevron.open {
    transform: rotate(180deg);
  }

  .advanced-settings-content {
    padding: 1rem;
    border-top: 1px solid var(--border-color);
    background-color: var(--card-background);
    animation: slideDown 0.2s ease;
  }

  @keyframes slideDown {
    from {
      opacity: 0;
      transform: translateY(-10px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .settings-help-text {
    margin-bottom: 1rem;
  }

  .settings-help-text p {
    margin: 0;
    font-size: 0.85rem;
    color: var(--text-secondary);
  }

  .settings-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1rem;
    margin-bottom: 1rem;
  }

  .setting-field {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .setting-field label {
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--text-primary);
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .setting-hint {
    font-size: 0.75rem;
    font-weight: 400;
    color: var(--text-secondary);
  }

  .setting-field input {
    padding: 0.5rem;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    background-color: var(--input-background, var(--card-background));
    color: var(--text-primary);
    font-size: 0.9rem;
    transition: all 0.2s ease;
  }

  .setting-field input:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .setting-field input:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    background-color: var(--disabled-background, #f5f5f5);
  }

  :global(.dark) .setting-field input:disabled {
    background-color: rgba(255, 255, 255, 0.05);
  }

  .setting-field input::placeholder {
    color: var(--text-light);
  }

  .validation-error {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem;
    background-color: rgba(239, 68, 68, 0.1);
    border: 1px solid rgba(239, 68, 68, 0.3);
    border-radius: 6px;
    color: #dc2626;
    font-size: 0.85rem;
    margin-top: 0.5rem;
  }

  :global(.dark) .validation-error {
    background-color: rgba(239, 68, 68, 0.15);
    border-color: rgba(239, 68, 68, 0.4);
    color: #f87171;
  }

  .validation-error svg {
    flex-shrink: 0;
  }

  .file-actions {
    display: flex;
    gap: 0.5rem;
    justify-content: flex-end;
  }

  .cancel-button {
    background-color: var(--card-background);
    color: var(--text-color);
    border: 1px solid var(--border-color);
    padding: 0.6rem 1.2rem;
    border-radius: 10px;
    font-size: 0.95rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    box-shadow: var(--card-shadow);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    min-width: 120px;
    opacity: 1;
  }

  .cancel-button:hover:not(:disabled) {
    background: var(--button-hover);
    border-color: var(--border-color);
    transform: translateY(-1px);
    box-shadow: var(--card-shadow);
  }

  .cancel-button:active {
    transform: translateY(0);
    box-shadow: var(--card-shadow);
  }

  .upload-button {
    background-color: var(--primary-color);
    color: white;
    border: none;
    padding: 0.6rem 1.2rem;
    border-radius: 10px;
    font-size: 0.95rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    min-width: 120px;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }

  .upload-button:hover:not(:disabled) {
    background-color: #2563eb;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }

  .upload-button:active {
    transform: translateY(0);
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }

  .upload-button:disabled,
  .cancel-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
    transform: none;
    box-shadow: none;
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
    background-color: #3b82f6;
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-weight: 500;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
    transition: all 0.2s ease;
  }

  .btn-acknowledge:hover {
    background-color: #2563eb;
    transform: translateY(-1px);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }

  /* File Upload Container */
  .file-upload-container {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    padding: 0.5rem 0; /* Consistent padding across all tabs */
  }

  /* URL Input Styles */
  .url-input-container {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
    padding: 0.5rem 0; /* Consistent padding across all tabs */
  }

  .url-input-section {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .protected-media-auth {
    border-radius: 8px;
    padding: 0.75rem 0.75rem 0.5rem 0.75rem;
    background-color: var(--surface-color);
    border: 1px dashed var(--border-color);
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .protected-media-header {
    font-size: 0.9rem;
    font-weight: 600;
    color: var(--text-primary);
  }

  .protected-media-fields {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 0.5rem 1rem;
  }

  .protected-media-field {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .protected-media-field label {
    font-size: 0.8rem;
    color: var(--text-secondary);
  }

  .protected-input {
    width: 100%;
    padding: 0.4rem 0.6rem;
    border-radius: 6px;
    border: 1px solid var(--border-color);
    background-color: var(--surface-color);
    color: var(--text-primary);
    font-size: 0.9rem;
  }

  .protected-input:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .protected-media-hint {
    font-size: 0.75rem;
    color: var(--text-secondary);
    margin: 0;
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

  .url-input-wrapper {
    position: relative;
    display: flex;
    align-items: center;
  }

  .url-input {
    width: 100%;
    padding: 0.75rem;
    padding-right: 3rem; /* Make space for paste button */
    border: 2px solid var(--border-color);
    border-radius: 8px;
    font-size: 1rem;
    background-color: var(--surface-color);
    color: var(--text-primary);
    transition: border-color 0.2s ease;
  }

  .paste-button {
    position: absolute;
    right: 8px;
    background: transparent;
    border: none;
    color: var(--text-secondary);
    cursor: pointer;
    padding: 6px;
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
    z-index: 1;
  }

  .paste-button:hover:not(:disabled) {
    background: var(--button-hover);
    color: var(--primary-color);
    transform: scale(1.05);
  }

  .paste-button:active {
    transform: scale(0.95);
  }

  .paste-button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
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
    background-color: var(--card-background);
    color: var(--text-color);
    border: 1px solid var(--border-color);
    padding: 0.6rem 1.2rem;
    border-radius: 10px;
    font-size: 0.95rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    box-shadow: var(--card-shadow);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    min-width: 120px;
    opacity: 1;
  }

  .cancel-url-button:hover:not(:disabled) {
    background: var(--button-hover);
    border-color: var(--border-color);
    transform: translateY(-1px);
    box-shadow: var(--card-shadow);
  }

  .cancel-url-button:active {
    transform: translateY(0);
    box-shadow: var(--card-shadow);
  }

  .cancel-url-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
    transform: none;
    box-shadow: none;
  }

  .process-url-button {
    background-color: #3b82f6;
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
    background-color: #2563eb;
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

  :global(.dark) .paste-button {
    color: var(--text-secondary);
  }

  :global(.dark) .paste-button:hover:not(:disabled) {
    background: var(--button-hover);
    color: var(--primary-color);
  }

  :global(.dark) .url-info {
    background-color: var(--surface-color);
    border-color: var(--border-color);
  }

  /* Recording Tab Styles */

  .device-selector-centered {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
    padding-bottom: 1.5rem;
  }

  .device-label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.95rem;
    font-weight: 600;
    color: var(--text-primary);
  }

  .device-select {
    width: 100%;
    padding: 0.75rem;
    border: 2px solid var(--border-color);
    border-radius: 8px;
    font-size: 1rem;
    background-color: var(--surface-color);
    color: var(--text-primary);
    transition: border-color 0.2s ease;
  }

  .device-select:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .device-select:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }




  .clear-button:hover {
    background-color: #6b7280;
    border-color: #6b7280;
  }

  .upload-recording-button {
    background-color: var(--primary-color);
    border-color: var(--primary-color);
    color: white;
  }

  .upload-recording-button:hover {
    background-color: #2563eb;
    border-color: #2563eb;
  }

  .upload-recording-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }


  /* Tab button disabled state */
  .tab-button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    color: var(--text-secondary);
  }

  .tab-button:disabled:hover {
    background-color: transparent;
    color: var(--text-secondary);
    transform: none;
  }

  /* Dark mode adjustments */
  :global(.dark) .device-select {
    background-color: var(--surface-color);
    border-color: var(--border-color);
    color: var(--text-primary);
  }

  :global(.dark) .device-select:focus {
    border-color: var(--primary-color);
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.2);
  }


  .device-label {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    font-size: 0.95rem;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 0.5rem;
    text-align: center;
  }

  .device-select {
    width: 100%;
    max-width: 250px;
    padding: 0.75rem;
    border: 2px solid var(--border-color);
    border-radius: 8px;
    font-size: 1rem;
    background-color: var(--background-color);
    color: var(--text-primary);
    transition: border-color 0.2s ease;
    text-align: center;
  }

  .device-select:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .device-select:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .recording-controls-main {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1rem;
    padding: 2rem 1rem;
    border: 2px solid var(--border-color);
    border-radius: 12px;
    background-color: var(--surface-color);
    min-height: 180px;
    justify-content: center;
    transition: all 0.2s ease;
  }

  .recording-button {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1.5rem;
    border-radius: 8px;
    font-size: 1rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s ease;
    border: 2px solid transparent;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }

  .recording-button.primary-button {
    background-color: #dc2626;
    color: white;
    border-color: #dc2626;
  }

  .recording-button.primary-button:hover {
    background-color: #b91c1c;
    border-color: #b91c1c;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(220, 38, 38, 0.25);
  }

  .recording-button.primary-button:active {
    transform: translateY(0);
    box-shadow: 0 2px 4px rgba(220, 38, 38, 0.2);
  }

  .recording-active-compact {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    width: 100%;
    transition: all 0.2s ease;
  }

  .recording-status-row {
    display: flex;
    justify-content: center;
    width: 100%;
  }

  .recording-indicator-compact {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .recording-status-text {
    font-weight: 600;
    color: var(--text-primary);
    font-size: 0.95rem;
  }

  .recording-duration-compact {
    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
    font-size: 1rem;
    font-weight: 700;
    color: var(--primary-color);
    background-color: rgba(59, 130, 246, 0.1);
    padding: 0.25rem 0.75rem;
    border-radius: 4px;
    margin-left: 0.5rem;
  }

  .audio-visualizer-compact {
    width: 100%;
    margin: 0.25rem 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0;
    min-height: 35px; /* Reduced for uniform bar heights */
  }

  .audio-level-meter-horizontal {
    display: flex;
    gap: 3px;
    align-items: center;
    height: 35px;
    padding: 0 10px;
    width: 50%;
    margin: 0 auto;
    justify-content: center;
  }

  .audio-level-bar {
    width: 12px;
    height: 25px;
    border-radius: 3px;
    background-color: var(--border-color);
    opacity: 0.3;
    transition: all 0.1s ease-out;
  }

  .audio-level-bar.active.low {
    background-color: #10b981;
    opacity: 1;
    height: 25px;
  }

  .audio-level-bar.active.medium {
    background-color: #f59e0b;
    opacity: 1;
    height: 25px;
  }

  .audio-level-bar.active.high {
    background-color: #dc2626;
    opacity: 1;
    height: 25px;
  }


  .recording-controls-row-compact {
    display: flex;
    gap: 0.75rem;
    justify-content: center;
  }

  .control-button-compact {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.25rem;
    padding: 0.5rem 0.75rem;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    background-color: transparent;
    color: var(--text-color);
    cursor: pointer;
    transition: all 0.2s ease;
    font-size: 0.85rem;
    font-weight: 500;
  }

  .control-button-compact:hover:not(:disabled) {
    background-color: var(--primary-color);
    border-color: var(--primary-color);
    color: white;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }

  .control-button-compact:active:not(:disabled) {
    transform: translateY(0);
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }

  .control-button-compact.pause-button:hover:not(:disabled) {
    background-color: #f59e0b;
    border-color: #f59e0b;
    box-shadow: 0 4px 8px rgba(245, 158, 11, 0.25);
  }

  .control-button-compact.stop-button:hover:not(:disabled) {
    background-color: #dc2626;
    border-color: #dc2626;
    box-shadow: 0 4px 8px rgba(220, 38, 38, 0.25);
  }

  .recording-complete-compact {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    width: 100%;
    align-items: center;
    transition: all 0.2s ease;
  }

  .recording-info-compact {
    display: flex;
    align-items: center;
    padding: 0.75rem 1rem;
    background-color: rgba(16, 185, 129, 0.1);
    border: 1px solid #10b981;
    border-radius: 8px;
    width: 100%;
  }

  .recording-details-compact {
    flex: 1;
    text-align: center;
  }

  .recording-title-compact {
    display: block;
    font-size: 1rem;
    font-weight: 600;
    margin-bottom: 0.25rem;
    color: var(--text-primary);
  }

  .recording-meta-compact {
    display: block;
    color: var(--text-secondary);
    font-size: 0.85rem;
  }

  .recording-actions-vertical {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    align-items: center;
    width: 100%;
  }

  .action-separator {
    height: 1px;
    background-color: var(--border-color);
    width: 60%;
    margin: 0.25rem 0;
    opacity: 0.5;
  }

  .control-button-compact.primary-action {
    background-color: var(--primary-color);
    border-color: var(--primary-color);
    color: white;
    font-weight: 600;
    min-width: 120px;
  }

  .control-button-compact.primary-action:hover:not(:disabled) {
    background-color: #2563eb;
    border-color: #2563eb;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }

  .control-button-compact.secondary-action {
    background-color: transparent;
    border-color: var(--border-color);
    color: var(--text-secondary);
    font-size: 0.85rem;
    opacity: 0.8;
    min-width: 100px;
  }

  .control-button-compact.secondary-action:hover {
    background-color: var(--error-color);
    border-color: var(--error-color);
    color: white;
    opacity: 1;
  }

  .control-button-compact.clear-button {
    border-color: var(--error-color);
    color: var(--error-color);
  }

  .control-button-compact.clear-button:hover:not(:disabled) {
    background-color: var(--error-color);
    border-color: var(--error-color);
    color: white;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(239, 68, 68, 0.25);
  }

  .control-button-compact.upload-recording-button {
    background-color: var(--primary-color);
    border-color: var(--primary-color);
    color: white;
    width: auto;
    gap: 0.5rem;
  }

  .control-button-compact.upload-recording-button:hover:not(:disabled) {
    background-color: #2563eb;
    border-color: #2563eb;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }

  .control-button-compact.upload-recording-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
    transform: none;
    box-shadow: none;
  }

  /* Recording info section styling - compact version - rules moved above */

  .recording-settings-section {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.25rem;
    margin-top: 0.5rem;
    width: 100%;
  }

  .settings-summary-centered {
    background-color: var(--background-color);
    border: 1px solid var(--border-light);
    border-radius: 8px;
    padding: 0.35rem 0.6rem;
    font-size: 0.85rem;
    color: var(--text-secondary);
    text-align: center;
    width: fit-content;
    margin: 0 auto;
  }

  .settings-link-centered {
    display: flex;
    justify-content: center;
    width: 100%;
  }


  .change-settings-link {
    color: var(--primary-color);
    text-decoration: none;
    font-size: 0.85rem;
    font-weight: 500;
    white-space: nowrap;
    background: none;
    border: none;
    padding: 0;
    cursor: pointer;
    font-family: inherit;
  }

  .change-settings-link:hover {
    text-decoration: underline;
  }

  /* Dark mode adjustments for recording components */
  :global(.dark) .device-select {
    background-color: var(--background-color);
    border-color: var(--border-color);
    color: var(--text-primary);
  }

  :global(.dark) .device-select:focus {
    border-color: var(--primary-color);
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.2);
  }

  :global(.dark) .recording-controls-main {
    background-color: var(--surface-color);
    border-color: var(--border-color);
  }

  :global(.dark) .control-button-compact {
    background-color: transparent;
    border-color: var(--border-color);
    color: var(--text-color);
  }

  :global(.dark) .control-button-compact svg {
    color: var(--text-color);
  }

  :global(.dark) .control-button-compact.clear-button {
    border-color: var(--error-color);
    color: var(--error-color);
  }

  :global(.dark) .control-button-compact.upload-recording-button {
    background-color: var(--primary-color);
    border-color: var(--primary-color);
    color: white;
  }

  :global(.dark) .recording-info-compact {
    background-color: rgba(16, 185, 129, 0.15);
  }

  /* Background Recording Indicator */
  .background-recording-indicator {
    position: fixed;
    top: 1rem;
    right: 1rem;
    background-color: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 0.75rem 1rem;
    display: flex;
    align-items: center;
    gap: 0.75rem;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    z-index: 1000;
    font-size: 0.9rem;
    color: var(--text-primary);
    backdrop-filter: blur(8px);
  }

  .recording-pulse {
    width: 12px;
    height: 12px;
    background-color: #dc2626;
    border-radius: 50%;
    animation: pulse-recording 1.5s infinite;
  }

  @keyframes pulse-recording {
    0% {
      opacity: 1;
      transform: scale(1);
    }
    50% {
      opacity: 0.7;
      transform: scale(1.2);
    }
    100% {
      opacity: 1;
      transform: scale(1);
    }
  }

  .recording-indicator-text {
    font-weight: 500;
    color: var(--text-primary);
  }

  .return-to-recording {
    background: none;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    padding: 0.25rem;
    cursor: pointer;
    color: var(--text-secondary);
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
  }

  .return-to-recording:hover {
    background-color: var(--hover-color, rgba(59, 130, 246, 0.1));
    border-color: var(--primary-color);
    color: var(--primary-color);
  }

  :global(.dark) .background-recording-indicator {
    background-color: var(--surface-color);
    border-color: var(--border-color);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  }
</style>
