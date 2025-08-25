<script lang="ts">
  export let file: any = null;

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

  {#if file?.status === 'processing'}
    <div class="processing-info">
      <h5>Transcription Progress</h5>
      <p>Processing file... Progress: {file.progress || 0}%</p>
      <div class="progress-bar">
        <div class="progress-bar-inner" style="width: {file.progress || 0}%;"></div>
      </div>
    </div>
  {/if}


  {#if file?.description}
    <div class="file-summary">
      <p>{file.description}</p>
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
    padding: 16px;
    background: var(--info-light);
    border: 1px solid var(--info-color);
    border-radius: 8px;
  }

  .processing-info p {
    margin: 0 0 12px 0;
    font-size: 14px;
    font-weight: 500;
    color: var(--info-dark);
  }

  .processing-info h5 {
    margin: 0 0 8px 0;
    font-size: 14px;
    font-weight: 600;
    color: var(--info-dark);
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
    background: var(--primary-color);
    border-radius: 4px;
    transition: width 0.3s ease;
  }

  .file-summary {
    margin: 16px 0;
  }

  .file-summary p {
    margin: 0;
    font-size: 16px;
    color: var(--text-secondary);
    line-height: 1.5;
  }


  @media (max-width: 768px) {
    .file-title h1 {
      font-size: 24px;
    }

    .file-summary p {
      font-size: 14px;
    }

  }
</style>