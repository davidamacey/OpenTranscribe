<script lang="ts">
  import { downloadStore } from '$stores/downloads';
  import { toastStore } from '$stores/toast';
  import axiosInstance from '$lib/axios';
  import { t } from '$stores/locale';

  export let downloadUrl: string = '';
  export let filename: string = 'download';
  export let fileId: string = '';
  export let isVideo: boolean = false;
  export let hasSubtitles: boolean = false;

  let downloadState = $downloadStore;

  $: downloadState = $downloadStore;
  $: currentDownload = downloadState[fileId];
  $: isDownloading = currentDownload && ['preparing', 'processing', 'downloading'].includes(currentDownload.status);

  async function handleVideoDownload() {
    if (!fileId) {
      toastStore.error($t('download.fileIdNotAvailable'));
      return;
    }

    // Start download tracking
    const canStart = downloadStore.startDownload(fileId, filename);
    if (!canStart) return;

    try {
      // Get JWT token from localStorage
      const token = localStorage.getItem('token');

      if (!token) {
        downloadStore.updateStatus(fileId, 'error', undefined, $t('download.noAuthToken'));
        return;
      }

      downloadStore.updateStatus(fileId, 'processing');

      // Build download URL with token
      const downloadWithTokenUrl = `/api/files/${fileId}/download-with-token?token=${encodeURIComponent(token)}&include_speakers=true`;

      // Start the download
      const link = document.createElement('a');
      link.href = downloadWithTokenUrl;
      link.download = `${getBaseFilename()}_with_subtitles.mp4`;
      link.style.display = 'none';
      document.body.appendChild(link);

      downloadStore.updateStatus(fileId, 'downloading');

      // Trigger download
      link.click();

      // Clean up
      document.body.removeChild(link);

      // Mark as completed after a short delay
      setTimeout(() => {
        downloadStore.updateStatus(fileId, 'completed');
      }, 2000);

    } catch (error) {
      console.error('Download error:', error);
      downloadStore.updateStatus(fileId, 'error', undefined, error instanceof Error ? error.message : $t('download.failed'));
    }
  }

  function getBaseFilename(): string {
    // Remove extension from filename
    return filename.includes('.') ? filename.substring(0, filename.lastIndexOf('.')) : filename;
  }

  function handleDownload() {
    if (isVideo && hasSubtitles) {
      handleVideoDownload();
    } else {
      // Original download behavior for non-video files or videos without subtitles
      if (downloadUrl) {
        window.open(downloadUrl, '_blank');
      }
    }
  }
</script>

{#if downloadUrl || (isVideo && hasSubtitles)}
  <button
    class="download-button"
    class:downloading={isDownloading}
    class:processing={currentDownload?.status === 'processing'}
    disabled={isDownloading}
    on:click={handleDownload}
    title={isDownloading ? $t('download.inProgress') : (isVideo ? $t('download.downloadVideoTooltip') : $t('download.downloadFileTooltip'))}
  >
    {#if isDownloading}
      {#if currentDownload?.status === 'preparing'}
        <svg class="spinner" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 12a9 9 0 11-6.219-8.56"/>
        </svg>
        {$t('download.preparing')}
      {:else if currentDownload?.status === 'processing'}
        <svg class="spinner" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 12a9 9 0 11-6.219-8.56"/>
        </svg>
        {$t('download.processing')}
      {:else if currentDownload?.status === 'downloading'}
        <svg class="spinner" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 12a9 9 0 11-6.219-8.56"/>
        </svg>
        {$t('download.downloading')}
      {/if}
    {:else}
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
        <polyline points="7 10 12 15 17 10"></polyline>
        <line x1="12" y1="15" x2="12" y2="3"></line>
      </svg>
      {$t('download.button')}
      {#if isVideo && hasSubtitles}
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"></rect>
          <line x1="7" y1="2" x2="7" y2="22"></line>
          <line x1="17" y1="2" x2="17" y2="22"></line>
          <line x1="2" y1="12" x2="22" y2="12"></line>
          <line x1="2" y1="7" x2="7" y2="7"></line>
          <line x1="2" y1="17" x2="7" y2="17"></line>
          <line x1="17" y1="17" x2="22" y2="17"></line>
          <line x1="17" y1="7" x2="22" y2="7"></line>
        </svg>
      {/if}
    {/if}
  </button>
{/if}

<style>
  .download-button {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 16px;
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    color: var(--text-primary);
    text-decoration: none;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .download-button:hover:not(:disabled) {
    background: var(--surface-hover);
    border-color: var(--border-hover);
    text-decoration: none;
  }

  .download-button:disabled {
    opacity: 0.7;
    cursor: not-allowed;
  }

  .download-button.downloading {
    background: var(--primary-color);
    color: white;
    border-color: var(--primary-color);
  }

  .download-button.processing {
    background: var(--warning-color, #f59e0b);
    color: white;
    border-color: var(--warning-color, #f59e0b);
  }

  .spinner {
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    from {
      transform: rotate(0deg);
    }
    to {
      transform: rotate(360deg);
    }
  }
</style>
