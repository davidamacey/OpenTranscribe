<script lang="ts">
  import { slide, fade } from 'svelte/transition';
  import { formatDuration } from '$lib/utils/formatting';
  import { authStore } from '$stores/auth';
  
  export let file: any = null;
  export let showMetadata: boolean = false;

  function formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  function toggleMetadata() {
    showMetadata = !showMetadata;
  }

</script>

<div class="metadata-dropdown-section">
  <button class="section-header" on:click={toggleMetadata} on:keydown={e => e.key === 'Enter' && toggleMetadata()} aria-expanded={showMetadata}>
    <h4 class="section-heading">File Details</h4>
    <span class="dropdown-toggle" aria-hidden="true">
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="transform: rotate({showMetadata ? '180deg' : '0deg'})">
        <polyline points="6 9 12 15 18 9"></polyline>
      </svg>
    </span>
  </button>
  
  {#if showMetadata}
  <div class="section-content" transition:slide={{ duration: 200 }}>
    <div class="metadata-panel">
      <div class="metadata-grid four-columns">
        <div class="metadata-item">
          <span class="metadata-label">Uploaded by:</span>
          <span class="metadata-value">{$authStore?.user?.email || 'Unknown user'}</span>
        </div>
        
        <div class="metadata-item">
          <span class="metadata-label">Upload date:</span>
          <span class="metadata-value">{file && 'upload_time' in file && file.upload_time ? new Date(file.upload_time).toLocaleDateString() : 'Unknown'}</span>
        </div>
        
        <div class="metadata-item">
          <span class="metadata-label">Media type:</span>
          <span class="metadata-value">{file && 'content_type' in file ? file.content_type : 'Unknown'}</span>
        </div>
        
        <div class="metadata-item">
          <span class="metadata-label">Duration:</span>
          <span class="metadata-value">
            {#if file && 'duration' in file && file.duration}
              {formatDuration(file.duration)}
            {:else}
              Unknown
            {/if}
          </span>
        </div>
        
        <div class="metadata-item">
          <span class="metadata-label">File size:</span>
          <span class="metadata-value">
            {#if file && 'file_size' in file && file.file_size}
              {formatFileSize(file.file_size)}
            {:else}
              Unknown
            {/if}
          </span>
        </div>
        
        <div class="metadata-item">
          <span class="metadata-label">Transcript status:</span>
          <span class="metadata-value">
            <span class="status-completed">Completed <i class="fas fa-check-circle"></i></span>
          </span>
        </div>
        
        {#if file && 'language' in file && file.language}
          <div class="metadata-item">
            <span class="metadata-label">Language:</span>
            <span class="metadata-value">{file.language}</span>
          </div>
        {/if}
        
        <div class="metadata-item">
          <span class="metadata-label">Created date:</span>
          <span class="metadata-value">{file && 'created_date' in file && file.created_date ? new Date(file.created_date).toLocaleDateString() : 'Unknown'}</span>
        </div>
        
        <!-- Tech Specs -->
        <div class="metadata-item">
          <span class="metadata-label">Resolution:</span>
          <span class="metadata-value">
            {#if file && 'resolution_width' in file && 'resolution_height' in file && file.resolution_width && file.resolution_height}
              {file.resolution_width}×{file.resolution_height}
            {:else}
              N/A
            {/if}
          </span>
        </div>
        
        <div class="metadata-item">
          <span class="metadata-label">Frame rate:</span>
          <span class="metadata-value">
            {#if file && 'frame_rate' in file && file.frame_rate}
              {typeof file.frame_rate === 'number' ? file.frame_rate.toFixed(0) : file.frame_rate}fps
            {:else}
              N/A
            {/if}
          </span>
        </div>
        
        <!-- Audio Info -->
        <div class="metadata-item">
          <span class="metadata-label">Audio channels:</span>
          <span class="metadata-value">
            {#if file && 'audio_channels' in file && file.audio_channels}
              {file.audio_channels}ch
            {:else}
              N/A
            {/if}
          </span>
        </div>
        
        <div class="metadata-item">
          <span class="metadata-label">Sample rate:</span>
          <span class="metadata-value">
            {#if file && 'audio_sample_rate' in file && file.audio_sample_rate}
              {Math.round(file.audio_sample_rate/1000)}kHz
            {:else}
              N/A
            {/if}
          </span>
        </div>
      </div>
    </div>
  </div>
  {/if}
</div>

<style>
  .metadata-dropdown-section {
    margin-bottom: 20px;
  }

  .section-header {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 12px 16px;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .section-header:hover {
    background: var(--surface-hover);
    border-color: var(--border-hover);
  }

  .section-heading {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .dropdown-toggle svg {
    transition: transform 0.2s ease;
  }

  .section-content {
    border: 1px solid var(--border-color);
    border-top: none;
    border-radius: 0 0 8px 8px;
    background: var(--surface-color);
  }

  .metadata-panel {
    padding: 20px;
  }

  .metadata-grid {
    display: grid;
    gap: 16px;
    margin-bottom: 20px;
  }

  .metadata-grid.four-columns {
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  }

  .metadata-item {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .metadata-label {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .metadata-value {
    font-size: 14px;
    color: var(--text-primary);
    font-weight: 500;
  }

  .status-completed {
    color: var(--success-color);
    display: flex;
    align-items: center;
    gap: 4px;
  }

  @media (max-width: 768px) {
    .metadata-grid.four-columns {
      grid-template-columns: 1fr;
    }
  }
</style>