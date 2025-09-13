<script lang="ts">
  export let file: any = null;
  export let currentProcessingStep: string = '';
  
  let isExpanded = false;
  
  // Helper function to determine if text should be truncated
  function shouldTruncate(text: string): boolean {
    if (!text) return false;
    
    // Lowered threshold to ~80 characters to test (roughly 1.5 lines)
    return text.length > 80;
  }
  
  function toggleExpanded() {
    isExpanded = !isExpanded;
  }

</script>

<div class="file-header-main">
  <div class="file-title">
    <h1>{file?.filename || 'Unknown File'}</h1>
  </div>

  <!-- Processing Status Display -->
  {#if file?.status === 'error' && file?.error_message}
    <div class="status-message error">
      <p><strong>Processing Status:</strong> {file.error_message}</p>
    </div>
  {/if}

  {#if file?.status === 'processing' || file?.status === 'pending'}
    <div class="processing-info">
      <div class="processing-header">
        <div class="processing-icon">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"></circle>
            <polyline points="12 6 12 12 16 14"></polyline>
          </svg>
        </div>
        <div class="processing-status">
          <span class="processing-label">Processing in Progress</span>
          <span class="processing-step-text">{#if currentProcessingStep}{currentProcessingStep}{:else}Processing file...{/if}</span>
        </div>
        <span class="progress-percentage">{file.progress || 0}%</span>
      </div>
      
      <div class="progress-bar">
        <div class="progress-bar-inner" style="width: {file.progress || 0}%;"></div>
      </div>
      
      <div class="processing-stages">
        <div class="stage {(file.progress || 0) >= 5 ? 'active' : ''} {(file.progress || 0) >= 25 ? 'completed' : ''}">
          <span class="stage-dot"></span>
          <span class="stage-label">Setup</span>
        </div>
        <div class="stage {(file.progress || 0) >= 25 ? 'active' : ''} {(file.progress || 0) >= 65 ? 'completed' : ''}">
          <span class="stage-dot"></span>
          <span class="stage-label">Transcription</span>
        </div>
        <div class="stage {(file.progress || 0) >= 65 ? 'active' : ''} {(file.progress || 0) >= 85 ? 'completed' : ''}">
          <span class="stage-dot"></span>
          <span class="stage-label">Analysis</span>
        </div>
        <div class="stage {(file.progress || 0) >= 85 ? 'active' : ''} {(file.progress || 0) >= 100 ? 'completed' : ''}">
          <span class="stage-dot"></span>
          <span class="stage-label">Finalization</span>
        </div>
      </div>
    </div>
  {/if}


  {#if file?.description}
    <div class="file-summary">
      
      {#if shouldTruncate(file.description)}
        {#if isExpanded}
          <p class="summary-text">
            {file.description}
            <span class="expand-link" on:click={toggleExpanded} on:keydown={(e) => e.key === 'Enter' && toggleExpanded()} tabindex="0" role="button"> See less</span>
          </p>
        {:else}
          <div class="truncated-wrapper">
            <p class="summary-text truncated">{file.description}</p>
            <span class="expand-link" on:click={toggleExpanded} on:keydown={(e) => e.key === 'Enter' && toggleExpanded()} tabindex="0" role="button">See more</span>
          </div>
        {/if}
      {:else}
        <p class="summary-text">
          {file.description}
        </p>
      {/if}
    </div>
  {/if}
</div>

<style>
  .file-header-main {
    margin-bottom: 24px;
  }

  .file-title h1 {
    margin: 0 0 16px 0;
    font-size: 28px;
    font-weight: 700;
    color: var(--text-primary);
    line-height: 1.2;
    word-break: break-word;
  }

  .status-message {
    margin: 16px 0;
    padding: 12px 16px;
    border-radius: 8px;
    border-left: 4px solid;
  }

  .status-message.error {
    background: var(--error-light);
    border-color: var(--error-color);
    color: var(--error-dark);
  }

  .status-message p {
    margin: 0;
    font-size: 14px;
    font-weight: 500;
  }

  .processing-info {
    margin: 16px 0;
    padding: 20px;
    background: var(--info-light);
    border: 1px solid var(--info-color);
    border-radius: 12px;
  }

  .processing-header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 16px;
  }

  .processing-icon {
    color: var(--primary-color);
    animation: spin 2s linear infinite;
    flex-shrink: 0;
  }

  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }

  .processing-status {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .processing-label {
    font-size: 16px;
    font-weight: 600;
    color: var(--info-dark);
    line-height: 1.2;
  }

  .processing-step-text {
    font-size: 14px;
    font-weight: 500;
    color: var(--text-secondary);
    font-style: italic;
    line-height: 1.2;
  }

  .progress-percentage {
    font-size: 14px;
    font-weight: 700;
    color: var(--primary-color);
    background: rgba(var(--primary-color-rgb), 0.1);
    padding: 4px 8px;
    border-radius: 4px;
    flex-shrink: 0;
  }

  .progress-bar {
    width: 100%;
    height: 8px;
    background: var(--surface-color);
    border-radius: 4px;
    overflow: hidden;
    border: 1px solid var(--border-color);
  }

  .progress-bar-inner {
    height: 100%;
    background: linear-gradient(90deg, var(--primary-color), rgba(var(--primary-color-rgb), 0.8));
    border-radius: 4px;
    transition: width 0.3s ease;
    animation: progress-shimmer 1.5s infinite;
  }

  @keyframes progress-shimmer {
    0% {
      background-position: -200px 0;
    }
    100% {
      background-position: calc(200px + 100%) 0;
    }
  }

  .processing-stages {
    display: flex;
    justify-content: space-between;
    margin-top: 16px;
    padding-top: 16px;
    border-top: 1px solid var(--border-color);
  }

  .stage {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    flex: 1;
    position: relative;
  }

  .stage:not(:last-child)::after {
    content: '';
    position: absolute;
    top: 8px;
    left: calc(50% + 12px);
    right: calc(-50% + 12px);
    height: 2px;
    background: var(--border-color);
    z-index: 1;
  }

  .stage.active:not(:last-child)::after {
    background: var(--primary-color);
  }

  .stage-dot {
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--border-color);
    border: 2px solid var(--surface-color);
    position: relative;
    z-index: 2;
    transition: all 0.3s ease;
  }

  .stage.active .stage-dot {
    background: var(--primary-color);
    animation: pulse 1.5s infinite;
  }

  .stage.completed .stage-dot {
    background: var(--success-color);
    animation: none;
  }

  @keyframes pulse {
    0%, 100% {
      transform: scale(1);
      opacity: 1;
    }
    50% {
      transform: scale(1.1);
      opacity: 0.8;
    }
  }

  .stage-label {
    font-size: 12px;
    font-weight: 500;
    color: var(--text-secondary);
    text-align: center;
  }

  .stage.active .stage-label {
    color: var(--primary-color);
    font-weight: 600;
  }

  .stage.completed .stage-label {
    color: var(--success-color);
  }

  .file-summary {
    margin: 16px 0;
  }

  .summary-text {
    margin: 0;
    font-size: 16px;
    color: var(--text-secondary);
    line-height: 1.5;
    transition: max-height 0.3s ease-in-out;
    overflow: hidden;
  }
  
  .truncated-wrapper {
    position: relative;
  }
  
  .summary-text.truncated {
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    margin-bottom: 0;
    padding-right: 5rem;
  }
  
  .truncated-wrapper .expand-link {
    position: absolute;
    bottom: 0;
    right: 0;
    background: var(--bg-primary);
    padding-left: 0.5em;
    margin-left: 0.3em;
  }
  
  .expand-link {
    color: var(--primary-color);
    cursor: pointer;
    font-weight: 500;
    text-decoration: none;
    white-space: nowrap;
    transition: color 0.2s ease;
  }
  
  .expand-link:hover {
    color: var(--primary-color-dark, #2563eb);
    text-decoration: underline;
  }
  
  .expand-link:focus {
    outline: 2px solid var(--primary-color);
    outline-offset: 2px;
    border-radius: 2px;
  }


  @media (max-width: 768px) {
    .file-title h1 {
      font-size: 24px;
    }

    .summary-text {
      font-size: 14px;
    }
    
    .expand-link {
      font-size: 0.9em;
    }

  }
</style>