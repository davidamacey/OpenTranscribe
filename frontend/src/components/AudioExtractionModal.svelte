<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { audioExtractionService } from '$lib/services/audioExtractionService';
  import type { ExtractedAudio } from '$lib/types/audioExtraction';
  import { formatFileSize, calculateCompressionRatio, estimateAudioSize } from '$lib/utils/metadataMapper';
  import { t } from '$stores/locale';
  import BaseModal from './ui/BaseModal.svelte';

  // Props
  export let isOpen = false;
  export let file: File | null = null;

  // State
  let estimatedAudioSize = 0;
  let compressionRatio = 0;

  // Keep a local copy of the file to prevent it from being cleared by parent
  let fileToExtract: File | null = null;

  const dispatch = createEventDispatcher<{
    extractionStarted: void;
    confirm: { extractedAudio: ExtractedAudio };
    cancel: void;
    uploadFull: void;
  }>();

  // Calculate estimates when file changes and save a local copy
  $: if (file) {
    fileToExtract = file; // Save local copy
    // Estimate based on typical video duration (use file size as rough proxy)
    // Assume ~1MB per minute for typical video
    const estimatedDuration = (file.size / (1024 * 1024)) * 60; // seconds
    estimatedAudioSize = estimateAudioSize(estimatedDuration, 32);
    compressionRatio = calculateCompressionRatio(file.size, estimatedAudioSize);
  }

  async function handleExtractAudio() {
    // Use local copy to ensure file reference isn't cleared by parent
    if (!fileToExtract) {
      console.error('No file available for extraction');
      return;
    }

    // Notify parent that extraction has started (so it can close upload modal)
    dispatch('extractionStarted');

    // Close modal immediately - extraction will run in background with notifications
    isOpen = false;

    // Start extraction in background using the local file copy
    try {
      const extractedAudio = await audioExtractionService.extractAudio(fileToExtract);

      // Dispatch success with extracted audio
      dispatch('confirm', { extractedAudio });
    } catch (error) {
      console.error('Audio extraction failed:', error);
      // Error will be shown in notification panel
    } finally {
      // Clear local copy after extraction completes
      fileToExtract = null;
    }
  }

  function handleUploadFull() {
    dispatch('uploadFull');
    isOpen = false;
  }

  function handleCancel() {
    // Close modal and clear file selection
    dispatch('cancel');
    isOpen = false;
  }
</script>

{#if file}
  <BaseModal isOpen={isOpen && !!file} title={$t('extraction.largeVideoDetected')} onClose={handleCancel} maxWidth="500px">
    <!-- Body content -->
    <div class="info-section">
      <div class="info-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M9 18V5l12-2v13"></path>
          <circle cx="6" cy="18" r="3"></circle>
          <circle cx="18" cy="16" r="3"></circle>
        </svg>
      </div>
      <p class="info-message">
        {$t('extraction.videoSizeMessage', { size: formatFileSize(file.size) })}
      </p>
    </div>

    <!-- Size comparison -->
    <div class="comparison-section">
      <div class="comparison-item">
        <div class="comparison-label">{$t('extraction.videoFile')}</div>
        <div class="comparison-value video">{formatFileSize(file.size)}</div>
      </div>
      <div class="comparison-arrow">→</div>
      <div class="comparison-item">
        <div class="comparison-label">{$t('extraction.audioOnly')}</div>
        <div class="comparison-value audio">{formatFileSize(estimatedAudioSize)}</div>
      </div>
    </div>

    <div class="savings-badge">
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="20 6 9 17 4 12"></polyline>
      </svg>
      <span>{$t('extraction.savingsBadge', { ratio: compressionRatio })}</span>
    </div>

    <div class="metadata-info">
      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"></circle>
        <line x1="12" y1="16" x2="12" y2="12"></line>
        <line x1="12" y1="8" x2="12.01" y2="8"></line>
      </svg>
      <span>{$t('extraction.metadataPreserved')}</span>
    </div>

    <svelte:fragment slot="footer">
      <button
        class="modal-button secondary-button"
        on:click={handleUploadFull}
        type="button"
      >
        {$t('extraction.uploadFullVideo')}
      </button>
      <button
        class="modal-button primary-button"
        on:click={handleExtractAudio}
        type="button"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M9 18V5l12-2v13"></path>
          <circle cx="6" cy="18" r="3"></circle>
          <circle cx="18" cy="16" r="3"></circle>
        </svg>
        {$t('extraction.extractAudio')}
      </button>
    </svelte:fragment>
  </BaseModal>
{/if}

<style>
  /* Info Section */
  .info-section {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    margin-bottom: 1.5rem;
  }

  .info-icon {
    color: var(--primary-color);
    margin-bottom: 1rem;
  }

  .info-message {
    margin: 0;
    color: var(--text-secondary);
    line-height: 1.6;
    font-size: 0.95rem;
  }

  /* Comparison Section */
  .comparison-section {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 1rem;
    margin: 1.5rem 0;
    padding: 1rem;
    background: var(--surface-color);
    border-radius: 8px;
    border: 1px solid var(--border-color);
  }

  .comparison-item {
    flex: 1;
    text-align: center;
  }

  .comparison-label {
    font-size: 0.75rem;
    color: var(--text-secondary);
    margin-bottom: 0.5rem;
    text-transform: uppercase;
    font-weight: 500;
  }

  .comparison-value {
    font-size: 1.25rem;
    font-weight: 600;
    padding: 0.5rem;
    border-radius: 6px;
  }

  .comparison-value.video {
    color: #ef4444;
    background: rgba(239, 68, 68, 0.1);
  }

  .comparison-value.audio {
    color: #10b981;
    background: rgba(16, 185, 129, 0.1);
  }

  .comparison-arrow {
    color: var(--text-secondary);
    font-size: 1.5rem;
  }

  .savings-badge {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    padding: 0.75rem 1rem;
    background: rgba(16, 185, 129, 0.1);
    border: 1px solid rgba(16, 185, 129, 0.2);
    border-radius: 8px;
    color: #10b981;
    font-weight: 500;
    font-size: 0.875rem;
    margin-bottom: 1rem;
  }

  .metadata-info {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    color: var(--text-secondary);
    font-size: 0.875rem;
  }

  .modal-button {
    padding: 0.6rem 1.2rem;
    border: none;
    border-radius: 10px;
    font-size: 0.95rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    min-width: 140px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
  }

  .secondary-button {
    background: var(--card-background);
    color: var(--text-color);
    border: 1px solid var(--border-color);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
  }

  .secondary-button:hover {
    background: var(--button-hover);
    transform: scale(1.02);
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.08);
  }

  .secondary-button:active {
    transform: scale(1);
  }

  .primary-button {
    background: #3b82f6;
    color: white;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }

  .primary-button:hover {
    background: #2563eb;
    transform: scale(1.02);
    box-shadow: 0 4px 8px rgba(var(--primary-color-rgb, 59, 130, 246), 0.3);
  }

  .primary-button:active {
    transform: scale(1);
  }

  /* Responsive design */
  @media (max-width: 480px) {
    .modal-button {
      width: 100%;
    }

    .comparison-section {
      flex-direction: column;
      gap: 0.5rem;
    }

    .comparison-arrow {
      transform: rotate(90deg);
    }
  }

  /* Reduced motion support */
  @media (prefers-reduced-motion: reduce) {
    .modal-button {
      transition: none;
    }
  }
</style>
