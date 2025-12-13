<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { t } from '$stores/locale';

  export let isEditingTranscript: boolean = false;

  const dispatch = createEventDispatcher();

  function toggleTranscriptEditor() {
    isEditingTranscript = !isEditingTranscript;
    dispatch('toggle', { isEditingTranscript });
  }
</script>

<button class="edit-transcript-button" on:click={toggleTranscriptEditor}>
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M12 20h9"></path>
    <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path>
  </svg>
  {isEditingTranscript ? $t('transcript.cancelEdit') : $t('transcript.editTranscript')}
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <rect x="4" y="4" width="16" height="16" rx="2" ry="2"></rect>
    <line x1="9" y1="9" x2="15" y2="9"></line>
    <line x1="9" y1="13" x2="15" y2="13"></line>
    <line x1="9" y1="17" x2="11" y2="17"></line>
  </svg>
</button>

<style>
  .edit-transcript-button {
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

  .edit-transcript-button:hover {
    background: var(--surface-hover);
    border-color: var(--border-hover);
  }
</style>
