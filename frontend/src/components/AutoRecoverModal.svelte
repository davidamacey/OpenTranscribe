<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { fade } from 'svelte/transition';

  export let isOpen = false;
  export let stuckFiles = [];

  const dispatch = createEventDispatcher();

  let isProcessing = false;

  $: categorizedFiles = {
    pending: stuckFiles.filter(f => f.status === 'pending'),
    processing: stuckFiles.filter(f => f.status === 'processing'),
    error: stuckFiles.filter(f => f.status === 'error'),
    orphaned: stuckFiles.filter(f => f.status === 'orphaned')
  };

  $: statusDescriptions = {
    pending: "Files that are waiting to start processing",
    processing: "Files that appear stuck during processing",
    error: "Files that failed and can be retried",
    orphaned: "Files in an inconsistent state that need recovery"
  };

  function handleConfirm() {
    isProcessing = true;
    dispatch('confirm');
  }

  function handleCancel() {
    dispatch('cancel');
    isOpen = false;
  }

  function handleBackdropClick(event: MouseEvent) {
    if (event.target === event.currentTarget) {
      handleClose();
    }
  }

  function handleClose() {
    if (isProcessing) {
      // Cancel the ongoing recovery
      isProcessing = false;
    }
    dispatch('close');
    isOpen = false;
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      handleClose();
    } else if (event.key === 'Enter' && !isProcessing) {
      handleConfirm();
    }
  }

  function formatTime(timestamp: string) {
    if (!timestamp) return 'Unknown';
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / (1000 * 60));
    
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins} minute${diffMins === 1 ? '' : 's'} ago`;
    if (diffMins < 1440) return `${Math.floor(diffMins / 60)} hour${Math.floor(diffMins / 60) === 1 ? '' : 's'} ago`;
    return `${Math.floor(diffMins / 1440)} day${Math.floor(diffMins / 1440) === 1 ? '' : 's'} ago`;
  }
</script>

{#if isOpen}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div 
    class="modal-backdrop" 
    transition:fade={{ duration: 200 }}
    on:click={handleBackdropClick}
    on:keydown={handleKeydown}
    tabindex="0"
    role="dialog"
    aria-modal="true"
    aria-labelledby="modal-title"
    aria-describedby="modal-description"
  >
    <div class="modal-container" transition:fade={{ duration: 200, delay: 100 }}>
      <div class="modal-content">
        <div class="modal-header">
          <div class="header-content">
            <div class="icon-container">
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="recovery-icon">
                <path d="M23 4v6h-6"></path>
                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
              </svg>
            </div>
            <div>
              <h2 id="modal-title" class="modal-title">Auto-Recovery Required</h2>
              <p class="modal-subtitle">
                {stuckFiles.length} file{stuckFiles.length === 1 ? '' : 's'} require recovery assistance
              </p>
            </div>
          </div>
          <button 
            class="modal-close-button" 
            on:click={handleClose}
            aria-label="Close dialog"
            title={isProcessing ? "Cancel recovery" : "Close dialog"}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>
        
        <div class="modal-body">
          <div id="modal-description" class="description">
            <p>The following files have been detected as requiring recovery. Auto-recovery will attempt to restart processing for each file automatically.</p>
          </div>

          <div class="file-categories">
            {#each Object.entries(categorizedFiles) as [status, files]}
              {#if files.length > 0}
                <div class="category-section">
                  <div class="category-header">
                    <div class="status-badge status-{status}">
                      <span class="status-dot"></span>
                      {status.charAt(0).toUpperCase() + status.slice(1)}
                    </div>
                    <span class="file-count">{files.length} file{files.length === 1 ? '' : 's'}</span>
                  </div>
                  <p class="category-description">{statusDescriptions[status]}</p>
                  
                  <div class="file-list">
                    {#each files.slice(0, 3) as file}
                      <div class="file-item">
                        <div class="file-info">
                          <span class="file-name" title={file.filename}>{file.filename}</span>
                          <span class="file-time">
                            {#if status === 'pending'}
                              Uploaded {formatTime(file.task_started_at || file.upload_time)}
                            {:else if status === 'processing'}
                              Stuck since {formatTime(file.task_last_update)}
                            {:else if status === 'error'}
                              Failed {formatTime(file.task_last_update)}
                            {:else}
                              Last seen {formatTime(file.task_last_update)}
                            {/if}
                          </span>
                        </div>
                      </div>
                    {/each}
                    {#if files.length > 3}
                      <div class="more-files">
                        +{files.length - 3} more file{files.length - 3 === 1 ? '' : 's'}
                      </div>
                    {/if}
                  </div>
                </div>
              {/if}
            {/each}
          </div>

          <div class="recovery-actions">
            <div class="actions-header">
              <h4>Auto-Recovery Process</h4>
              <span class="info-note">The following actions will be performed automatically:</span>
            </div>
            <div class="action-item">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="9,11 12,14 22,4"></polyline>
                <path d="m21,12v7a2,2 0,0 1,-2,2H5a2,2 0,0 1,-2,-2V5a2,2 0,0 1,2,-2h11"></path>
              </svg>
              <span>Reset stuck files to pending status</span>
            </div>
            <div class="action-item">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 12a9 9 0 11-6.219-8.56"></path>
              </svg>
              <span>Restart processing automatically</span>
            </div>
            <div class="action-item">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"></path>
              </svg>
              <span>Preserve file data and metadata</span>
            </div>
          </div>
        </div>
        
        <div class="modal-footer">
          {#if !isProcessing}
            <button 
              class="modal-button cancel-button" 
              on:click={handleCancel}
              type="button"
            >
              Cancel
            </button>
            <button 
              class="modal-button confirm-button" 
              on:click={handleConfirm}
              type="button"
              autofocus
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M23 4v6h-6"></path>
                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
              </svg>
              Start Auto-Recovery
            </button>
          {:else}
            <div class="processing-state">
              <div class="spinner"></div>
              <span>Recovering files...</span>
            </div>
            <button 
              class="modal-button cancel-button-processing" 
              on:click={handleCancel}
              type="button"
              title="Cancel recovery and close modal"
            >
              Cancel Recovery
            </button>
          {/if}
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
    max-width: 600px;
    width: 100%;
    max-height: 90vh;
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
    height: 100%;
  }

  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    padding: 1.5rem;
    border-bottom: 1px solid var(--border-color);
    background: linear-gradient(135deg, var(--primary-color), var(--primary-hover, #2563eb));
    color: white;
  }

  .header-content {
    display: flex;
    align-items: center;
    gap: 1rem;
  }

  .icon-container {
    padding: 0.75rem;
    background: rgba(255, 255, 255, 0.15);
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .recovery-icon {
    color: white;
  }

  .modal-title {
    margin: 0;
    font-size: 1.375rem;
    font-weight: 600;
    line-height: 1.3;
  }

  .modal-subtitle {
    margin: 0.25rem 0 0 0;
    opacity: 0.9;
    font-size: 0.9rem;
  }

  .modal-close-button {
    background: rgba(255, 255, 255, 0.15);
    border: none;
    cursor: pointer;
    padding: 0.5rem;
    color: white;
    transition: background-color 0.2s ease;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .modal-close-button:hover {
    background: rgba(255, 255, 255, 0.25);
  }

  .modal-body {
    padding: 1.5rem;
    overflow-y: auto;
    flex: 1;
  }

  .description {
    margin-bottom: 1.5rem;
  }

  .description p {
    margin: 0;
    color: var(--text-secondary);
    line-height: 1.5;
    font-size: 0.95rem;
  }

  .file-categories {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
    margin-bottom: 1.5rem;
  }

  .category-section {
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 1rem;
    background: var(--surface-color);
  }

  .category-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.5rem;
  }

  .status-badge {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.375rem 0.75rem;
    border-radius: 6px;
    font-size: 0.875rem;
    font-weight: 500;
  }

  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
  }

  .status-pending {
    background: rgba(59, 130, 246, 0.1);
    color: #2563eb;
    border: 1px solid rgba(59, 130, 246, 0.2);
  }

  .status-pending .status-dot {
    background: #2563eb;
  }

  .status-processing {
    background: rgba(245, 158, 11, 0.1);
    color: #d97706;
    border: 1px solid rgba(245, 158, 11, 0.2);
  }

  .status-processing .status-dot {
    background: #d97706;
  }

  .status-error {
    background: rgba(239, 68, 68, 0.1);
    color: #dc2626;
    border: 1px solid rgba(239, 68, 68, 0.2);
  }

  .status-error .status-dot {
    background: #dc2626;
  }

  .status-orphaned {
    background: rgba(107, 114, 128, 0.1);
    color: #6b7280;
    border: 1px solid rgba(107, 114, 128, 0.2);
  }

  .status-orphaned .status-dot {
    background: #6b7280;
  }

  .file-count {
    color: var(--text-secondary);
    font-size: 0.875rem;
  }

  .category-description {
    margin: 0 0 0.75rem 0;
    color: var(--text-secondary);
    font-size: 0.875rem;
    line-height: 1.4;
  }

  .file-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .file-item {
    padding: 0.5rem;
    background: var(--background-color);
    border-radius: 6px;
    border: 1px solid var(--border-color);
  }

  .file-info {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .file-name {
    font-weight: 500;
    color: var(--text-color);
    font-size: 0.875rem;
    display: -webkit-box;
    -webkit-line-clamp: 1;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .file-time {
    color: var(--text-secondary);
    font-size: 0.8rem;
  }

  .more-files {
    padding: 0.375rem 0.5rem;
    color: var(--text-secondary);
    font-size: 0.8rem;
    text-align: center;
    background: var(--background-color);
    border-radius: 6px;
    border: 1px dashed var(--border-color);
  }

  .recovery-actions {
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 1rem;
  }

  .actions-header {
    margin-bottom: 0.75rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border-color);
  }

  .actions-header h4 {
    margin: 0 0 0.25rem 0;
    font-size: 0.95rem;
    font-weight: 600;
    color: var(--text-color);
  }

  .info-note {
    font-size: 0.8rem;
    color: var(--text-secondary);
    font-style: italic;
  }

  .action-item {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.5rem 0;
    color: var(--text-secondary);
    font-size: 0.875rem;
  }

  .action-item svg {
    color: var(--primary-color);
    flex-shrink: 0;
  }

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

  .cancel-button {
    background: var(--surface-color);
    color: var(--text-color);
    border: 1px solid var(--border-color);
  }

  .cancel-button:hover {
    background: var(--primary-color);
    color: white;
    border-color: var(--primary-color);
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }

  .confirm-button {
    background: var(--primary-color);
    color: white;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }

  .confirm-button:hover {
    background: var(--primary-hover, #2563eb);
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.3);
  }

  .processing-state {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    color: var(--text-secondary);
    font-size: 0.95rem;
    padding: 0.5rem 0;
    flex: 1;
  }

  .cancel-button-processing {
    background: var(--surface-color);
    color: var(--text-color);
    border: 1px solid var(--border-color);
  }

  .cancel-button-processing:hover {
    background: #ef4444;
    color: white;
    border-color: #ef4444;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(239, 68, 68, 0.25);
  }

  .spinner {
    width: 16px;
    height: 16px;
    border: 2px solid var(--border-color);
    border-top: 2px solid var(--primary-color);
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }

  /* Dark mode adjustments */
  :global([data-theme='dark']) .modal-backdrop {
    background: var(--modal-backdrop, rgba(0, 0, 0, 0.7));
  }

  :global([data-theme='dark']) .modal-container {
    background: var(--background-color);
    border-color: var(--border-color);
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3), 0 10px 10px -5px rgba(0, 0, 0, 0.2);
  }

  /* Responsive design */
  @media (max-width: 640px) {
    .modal-container {
      margin: 1rem;
      max-width: none;
      max-height: 95vh;
    }

    .modal-header {
      padding: 1rem;
    }

    .header-content {
      gap: 0.75rem;
    }

    .modal-title {
      font-size: 1.25rem;
    }

    .modal-body {
      padding: 1rem;
    }

    .modal-footer {
      flex-direction: column-reverse;
      padding: 1rem;
    }

    .modal-button {
      width: 100%;
    }
  }

  /* Focus styles for accessibility */
  .modal-button:focus {
    outline: 2px solid var(--primary-color);
    outline-offset: 2px;
  }

  .cancel-button:focus {
    outline: 2px solid var(--text-color);
    outline-offset: 2px;
  }

  /* Reduced motion support */
  @media (prefers-reduced-motion: reduce) {
    .modal-container {
      animation: none;
    }

    .modal-button {
      transition: none;
    }

    .spinner {
      animation: none;
    }
  }
</style>