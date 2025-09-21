<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  
  const dispatch = createEventDispatcher();

  function exportTranscript(format: string) {
    dispatch('export', { format });
  }
</script>

<div class="export-dropdown">
  <button 
    class="export-transcript-button"
    title="Export transcript in various formats including text, JSON, CSV, SRT, and WebVTT"
  >
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
      <polyline points="7 10 12 15 17 10"></polyline>
      <line x1="12" y1="15" x2="12" y2="3"></line>
    </svg>
    Export
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <rect x="4" y="4" width="16" height="16" rx="2" ry="2"></rect>
      <line x1="9" y1="9" x2="15" y2="9"></line>
      <line x1="9" y1="13" x2="15" y2="13"></line>
      <line x1="9" y1="17" x2="11" y2="17"></line>
    </svg>
  </button>
  <div class="export-dropdown-content">
    <button 
      on:click={() => exportTranscript('txt')}
      title="Export transcript as plain text file"
    >Plain Text (.txt)</button>
    <button 
      on:click={() => exportTranscript('json')}
      title="Export transcript as JSON file with timestamps and speaker information"
    >JSON Format (.json)</button>
    <button 
      on:click={() => exportTranscript('csv')}
      title="Export transcript as CSV file for spreadsheet applications"
    >CSV Format (.csv)</button>
    <button 
      on:click={() => exportTranscript('srt')}
      title="Export transcript as SRT subtitle file for video players"
    >SubRip Subtitles (.srt)</button>
    <button 
      on:click={() => exportTranscript('vtt')}
      title="Export transcript as WebVTT subtitle file for web video players"
    >WebVTT Subtitles (.vtt)</button>
  </div>
</div>

<style>
  .export-dropdown {
    position: relative;
    display: inline-block;
  }

  .export-transcript-button {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 16px;
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    color: var(--text-primary);
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .export-transcript-button:hover {
    background: var(--hover-bg);
    border-color: var(--primary-color);
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
  }

  .export-dropdown:hover .export-dropdown-content {
    display: block;
  }

  .export-dropdown-content {
    display: none;
    position: absolute;
    top: 100%;
    left: 0;
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    z-index: 100;
    min-width: 200px;
  }

  .export-dropdown-content button {
    display: block;
    width: 100%;
    padding: 10px 16px;
    background: none;
    border: none;
    text-align: left;
    color: var(--text-primary);
    font-size: 14px;
    cursor: pointer;
    transition: background-color 0.2s ease;
  }

  .export-dropdown-content button:hover {
    background: var(--surface-hover);
  }

  .export-dropdown-content button:first-child {
    border-radius: 6px 6px 0 0;
  }

  .export-dropdown-content button:last-child {
    border-radius: 0 0 6px 6px;
  }
</style>