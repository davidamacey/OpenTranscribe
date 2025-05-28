<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  
  export let videoUrl: string = '';
  export let file: any = null;
  export let isPlayerBuffering: boolean = false;
  export let loadProgress: number = 0;
  export let errorMessage: string = '';

  const dispatch = createEventDispatcher();

  function handleRetry() {
    dispatch('retry');
  }
</script>

<div class="video-player-container" class:loading={isPlayerBuffering}>
  {#if videoUrl}
    <video id="player" playsinline controls>
      <source src={videoUrl} type="video/mp4" />
      <!-- Captions disabled to avoid CORS issues -->
      Your browser does not support the video element.
    </video>
    
    {#if isPlayerBuffering}
      <div class="buffer-indicator">
        <div class="spinner"></div>
        <div class="buffer-text">Loading video... {Math.round(loadProgress)}%</div>
      </div>
    {/if}
    
    {#if errorMessage}
      <p class="error-message">{errorMessage}</p>
      <button 
      class="retry-button" 
      on:click={handleRetry}
      title="Retry loading the video file"
    >Retry Loading Video</button>
    {/if}
  {:else if file && file.status === 'completed'}
    <div class="no-preview">Video preview not available. You can try downloading the file.</div>
  {:else if file && file.status !== 'processing'}
    <div class="no-preview">Video processing or not available.</div>
  {/if}
</div>

<style>
  .video-player-container {
    position: relative;
    width: 100%;
    border-radius: 8px;
    overflow: hidden;
    background: var(--surface-color);
    border: 1px solid var(--border-color);
  }

  .video-player-container.loading {
    opacity: 0.7;
  }

  video {
    width: 100%;
    height: auto;
    display: block;
    background: #000;
  }

  .buffer-indicator {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    background: rgba(0, 0, 0, 0.8);
    color: white;
    padding: 16px;
    border-radius: 8px;
  }

  .spinner {
    width: 24px;
    height: 24px;
    border: 2px solid transparent;
    border-top: 2px solid currentColor;
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }

  .buffer-text {
    font-size: 14px;
    font-weight: 500;
  }

  .no-preview {
    padding: 40px 20px;
    text-align: center;
    color: var(--text-secondary);
    background: var(--surface-color);
    border-radius: 8px;
  }

  .error-message {
    color: var(--error-color);
    margin: 8px 0;
    font-size: 14px;
  }

  .retry-button {
    background: var(--primary-color);
    color: white;
    border: none;
    padding: 8px 16px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 14px;
  }

  .retry-button:hover {
    background: var(--primary-hover);
  }
</style>