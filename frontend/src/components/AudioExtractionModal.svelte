<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { fade } from 'svelte/transition';
  import { audioExtractionService } from '$lib/services/audioExtractionService';
  import type { ExtractedAudio } from '$lib/types/audioExtraction';
  import { formatFileSize, calculateCompressionRatio, estimateAudioSize } from '$lib/utils/metadataMapper';
  import { t } from '$stores/locale';

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

  function handleBackdropClick(event: MouseEvent) {
    // Prevent dismissal by clicking outside - user must use X button or choose an option
    event.stopPropagation();
  }

  function handleKeydown(event: KeyboardEvent) {
    // Prevent dismissal with Escape key - user must use X button or choose an option
    if (event.key === 'Escape') {
      event.preventDefault();
    }
  }
</script>

{#if isOpen && file}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div
    class="modal-backdrop"
    transition:fade={{ duration: 200 }}
    on:click={handleBackdropClick}
    on:keydown={handleKeydown}
    tabindex="-1"
    role="dialog"
    aria-modal="true"
    aria-labelledby="extraction-modal-title"
  >
    <div class="modal-container" transition:fade={{ duration: 200, delay: 100 }}>
      <div class="modal-content">
        <!-- Header -->
        <div class="modal-header">
          <h2 id="extraction-modal-title" class="modal-title">
            {$t('extraction.largeVideoDetected')}
          </h2>
          <button
            class="modal-close-button"
            on:click={handleCancel}
            aria-label={$t('extraction.closeDialog')}
            title={$t('extraction.closeAndClear')}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>

        <!-- Body -->
        <div class="modal-body">
          <!-- Initial prompt -->
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
        </div>

        <!-- Footer -->
        <div class="modal-footer">
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
        </div>
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: var(--modal-backdrop, rgba(0, 0, 0, 0.5));
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    padding: 1rem;
  }

  .modal-container {
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

  .modal-content {
    display: flex;
    flex-direction: column;
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

  .modal-close-button {
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
  }

  .modal-close-button:hover {
    color: var(--text-color);
    background: var(--button-hover);
  }

  .modal-body {
    padding: 1.5rem;
    min-height: 200px;
  }

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

  /* Footer */
  .modal-footer {
    display: flex;
    gap: 0.75rem;
    padding: 1rem 1.5rem 1.5rem;
    justify-content: flex-end;
    border-top: 1px solid var(--border-color);
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
    box-shadow: var(--card-shadow);
  }

  .secondary-button:hover {
    background: var(--button-hover);
    transform: translateY(-1px);
  }

  .primary-button {
    background: #3b82f6;
    color: white;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }

  .primary-button:hover {
    background: #2563eb;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.3);
  }

  /* Dark mode adjustments */
  :global([data-theme='dark']) .modal-backdrop {
    background: var(--modal-backdrop, rgba(0, 0, 0, 0.7));
  }

  :global([data-theme='dark']) .modal-container {
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3), 0 10px 10px -5px rgba(0, 0, 0, 0.2);
  }

  /* Responsive design */
  @media (max-width: 480px) {
    .modal-container {
      margin: 1rem;
      max-width: none;
    }

    .modal-footer {
      flex-direction: column-reverse;
    }

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
    .modal-container {
      animation: none;
    }

    .modal-button {
      transition: none;
    }
  }
</style>
