<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { mergeSpeakers } from '$lib/api/speakers';
  import { toastStore } from '$stores/toast';
  import { getSpeakerColor } from '$lib/utils/speakerColors';
  import type { Speaker } from '$lib/types/speaker';

  export let speakers: Speaker[] = [];

  const dispatch = createEventDispatcher();

  // Track selected speakers
  let selectedSpeakers = new Set<string>();
  let showTargetDialog = false;
  let targetSpeaker: Speaker | null = null;
  let merging = false;

  // Reactive: Get list of selected speaker objects
  $: selectedSpeakerList = speakers.filter(s => selectedSpeakers.has(s.uuid));

  // Reactive: Enable merge button only when 2+ speakers selected
  $: canMerge = selectedSpeakers.size >= 2;

  // Reactive: Get segment count for each speaker
  function getSegmentCount(speaker: Speaker): number {
    return speaker.segment_count || 0;
  }

  // Toggle speaker selection
  function toggleSpeaker(speakerUuid: string) {
    if (selectedSpeakers.has(speakerUuid)) {
      selectedSpeakers.delete(speakerUuid);
    } else {
      selectedSpeakers.add(speakerUuid);
    }
    selectedSpeakers = new Set(selectedSpeakers); // Trigger reactivity
  }

  // Open target selection dialog
  function openTargetDialog() {
    if (!canMerge) return;
    showTargetDialog = true;
    targetSpeaker = null;
  }

  // Close target selection dialog
  function closeTargetDialog() {
    showTargetDialog = false;
    targetSpeaker = null;
  }

  // Perform the merge operation
  async function performMerge() {
    if (!targetSpeaker || selectedSpeakers.size < 2) {
      toastStore.error('Please select a target speaker');
      return;
    }

    merging = true;

    // Get source speakers (all selected except target)
    const sourceSpeakers = selectedSpeakerList.filter(s => s.uuid !== targetSpeaker.uuid);

    // Track successful and failed merges
    const successfulMerges: Speaker[] = [];
    const failedMerges: { speaker: Speaker; error: string }[] = [];

    // Merge each source speaker into target
    for (const sourceSpeaker of sourceSpeakers) {
      try {
        await mergeSpeakers(sourceSpeaker.uuid, targetSpeaker.uuid);
        successfulMerges.push(sourceSpeaker);
      } catch (error: any) {
        const errorMessage = error.response?.data?.detail || error.message || 'Unknown error';
        failedMerges.push({ speaker: sourceSpeaker, error: errorMessage });
        console.error(`Error merging speaker ${sourceSpeaker.display_name || sourceSpeaker.name}:`, error);
      }
    }

    // Show appropriate message based on results
    if (failedMerges.length === 0) {
      // All merges succeeded
      toastStore.success(
        `Successfully merged ${successfulMerges.length} speaker${successfulMerges.length > 1 ? 's' : ''} into ${targetSpeaker.display_name || targetSpeaker.name}`
      );
    } else if (successfulMerges.length === 0) {
      // All merges failed
      const failedNames = failedMerges.map(f => f.speaker.display_name || f.speaker.name).join(', ');
      toastStore.error(`Merge failed for all speakers: ${failedNames}. Error: ${failedMerges[0].error}`);
    } else {
      // Partial success - some merged, some failed
      const successNames = successfulMerges.map(s => s.display_name || s.name).join(', ');
      const failedNames = failedMerges.map(f => f.speaker.display_name || f.speaker.name).join(', ');
      toastStore.warning(
        `Partial merge: Successfully merged ${successNames}. Failed to merge: ${failedNames}.`
      );
    }

    // Reset selection
    selectedSpeakers.clear();
    selectedSpeakers = new Set(selectedSpeakers);
    closeTargetDialog();

    // Dispatch merged event to parent if any merges succeeded
    if (successfulMerges.length > 0) {
      dispatch('merged');
    }

    merging = false;
  }

  // Clear all selections
  function clearSelection() {
    selectedSpeakers.clear();
    selectedSpeakers = new Set(selectedSpeakers);
  }
</script>

<div class="speaker-merge">
  <div class="merge-header">
    <h5>Merge Speakers</h5>
    <p class="help-text">Select 2 or more speakers to merge into one. All segments will be reassigned to the target speaker.</p>
  </div>

  <div class="speaker-grid">
    {#each speakers as speaker}
      <label class="speaker-card" class:selected={selectedSpeakers.has(speaker.uuid)}>
        <input
          type="checkbox"
          checked={selectedSpeakers.has(speaker.uuid)}
          on:change={() => toggleSpeaker(speaker.uuid)}
        />
        <div class="speaker-info">
          <span
            class="speaker-badge"
            style="background-color: {getSpeakerColor(speaker.name).bg}; border-color: {getSpeakerColor(speaker.name).border}; --speaker-light: {getSpeakerColor(speaker.name).textLight}; --speaker-dark: {getSpeakerColor(speaker.name).textDark};"
          >
            {speaker.display_name || speaker.name}
          </span>
          <span class="segment-count">{getSegmentCount(speaker)} segment{getSegmentCount(speaker) !== 1 ? 's' : ''}</span>
        </div>
      </label>
    {/each}
  </div>

  <div class="merge-actions">
    <button
      class="btn-secondary"
      on:click={clearSelection}
      disabled={selectedSpeakers.size === 0}
    >
      Clear Selection
    </button>
    <button
      class="btn-primary"
      on:click={openTargetDialog}
      disabled={!canMerge}
      title={canMerge ? 'Select target speaker and merge' : 'Select at least 2 speakers to merge'}
    >
      {#if selectedSpeakers.size === 0}
        Merge Selected (0)
      {:else if selectedSpeakers.size === 1}
        Merge Selected (1) - Need 1 more
      {:else}
        Merge Selected ({selectedSpeakers.size})
      {/if}
    </button>
  </div>

  {#if showTargetDialog}
    <div class="modal-overlay" on:click={closeTargetDialog} on:keydown={(e) => e.key === 'Escape' && closeTargetDialog()} role="presentation">
      <div class="modal-content" on:click|stopPropagation on:keydown|stopPropagation role="dialog" aria-modal="true" aria-labelledby="speaker-merge-modal-title" tabindex="-1">
        <div class="modal-header">
          <h4 id="speaker-merge-modal-title">Select Target Speaker</h4>
          <button class="close-button" on:click={closeTargetDialog} title="Close">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>

        <div class="modal-body">
          <p class="modal-description">
            Choose which speaker should be kept. All segments from the other {selectedSpeakers.size - 1} speaker{selectedSpeakers.size - 1 !== 1 ? 's' : ''} will be reassigned to this target speaker.
          </p>

          <div class="target-list">
            {#each selectedSpeakerList as speaker}
              <label class="target-option" class:selected={targetSpeaker?.uuid === speaker.uuid}>
                <input
                  type="radio"
                  name="target-speaker"
                  value={speaker.uuid}
                  on:change={() => targetSpeaker = speaker}
                />
                <div class="target-info">
                  <span
                    class="speaker-badge"
                    style="background-color: {getSpeakerColor(speaker.name).bg}; border-color: {getSpeakerColor(speaker.name).border}; --speaker-light: {getSpeakerColor(speaker.name).textLight}; --speaker-dark: {getSpeakerColor(speaker.name).textDark};"
                  >
                    {speaker.display_name || speaker.name}
                  </span>
                  <span class="segment-count">{getSegmentCount(speaker)} segments</span>
                </div>
              </label>
            {/each}
          </div>
        </div>

        <div class="modal-footer">
          <button class="btn-secondary" on:click={closeTargetDialog} disabled={merging}>
            Cancel
          </button>
          <button
            class="btn-primary btn-danger"
            on:click={performMerge}
            disabled={!targetSpeaker || merging}
          >
            {#if merging}
              <svg class="spinner" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 12a9 9 0 11-6.219-8.56"/>
              </svg>
              Merging...
            {:else}
              Merge {selectedSpeakers.size - 1} into Target
            {/if}
          </button>
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  .speaker-merge {
    margin-top: 1rem;
    padding: 1rem;
    background: var(--background-secondary);
    border: 1px solid var(--border-color);
    border-radius: 8px;
  }

  .merge-header h5 {
    margin: 0 0 0.5rem 0;
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .help-text {
    margin: 0 0 1rem 0;
    font-size: 12px;
    color: var(--text-secondary);
    line-height: 1.4;
  }

  .speaker-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 0.75rem;
    margin-bottom: 1rem;
  }

  .speaker-card {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.75rem;
    background: var(--surface-color);
    border: 2px solid var(--border-color);
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .speaker-card:hover {
    border-color: var(--primary-color);
    background: var(--surface-hover);
  }

  .speaker-card.selected {
    border-color: var(--primary-color);
    background: rgba(59, 130, 246, 0.1);
  }

  .speaker-card input[type="checkbox"] {
    cursor: pointer;
    width: 18px;
    height: 18px;
    accent-color: var(--primary-color);
  }

  .speaker-info {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    min-width: 0;
  }

  .speaker-badge {
    font-size: 11px;
    font-weight: 700;
    padding: 3px 8px;
    border-radius: 12px;
    border: 1px solid;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--speaker-light);
    display: inline-block;
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  :global([data-theme='dark']) .speaker-badge {
    color: var(--speaker-dark);
  }

  .segment-count {
    font-size: 11px;
    color: var(--text-secondary);
  }

  .merge-actions {
    display: flex;
    gap: 0.75rem;
    justify-content: flex-end;
  }

  .btn-primary,
  .btn-secondary {
    padding: 0.6rem 1.2rem;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    border: none;
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
  }

  .btn-primary {
    background: var(--primary-color);
    color: white;
  }

  .btn-primary:hover:not(:disabled) {
    background: var(--primary-hover);
    transform: translateY(-1px);
  }

  .btn-primary:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    transform: none;
  }

  .btn-secondary {
    background: #6b7280;
    color: white;
  }

  .btn-secondary:hover:not(:disabled) {
    background: #4b5563;
  }

  .btn-secondary:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-danger {
    background: #ef4444;
  }

  .btn-danger:hover:not(:disabled) {
    background: #dc2626;
  }

  /* Modal Styles */
  .modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }

  .modal-content {
    background: var(--surface-color);
    border-radius: 12px;
    box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
    max-width: 500px;
    width: 90%;
    max-height: 80vh;
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

  .modal-header h4 {
    margin: 0;
    font-size: 18px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .close-button {
    background: none;
    border: none;
    color: var(--text-secondary);
    cursor: pointer;
    padding: 0.25rem;
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
  }

  .close-button:hover {
    background: var(--surface-hover);
    color: var(--text-primary);
  }

  .modal-body {
    padding: 1.5rem;
    overflow-y: auto;
  }

  .modal-description {
    margin: 0 0 1rem 0;
    font-size: 14px;
    color: var(--text-secondary);
    line-height: 1.5;
  }

  .target-list {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .target-option {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.75rem;
    background: var(--background-secondary);
    border: 2px solid var(--border-color);
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .target-option:hover {
    border-color: var(--primary-color);
    background: var(--surface-hover);
  }

  .target-option.selected {
    border-color: var(--primary-color);
    background: rgba(59, 130, 246, 0.1);
  }

  .target-option input[type="radio"] {
    cursor: pointer;
    width: 18px;
    height: 18px;
    accent-color: var(--primary-color);
  }

  .target-info {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
  }

  .modal-footer {
    display: flex;
    justify-content: flex-end;
    gap: 0.75rem;
    padding: 1.5rem;
    border-top: 1px solid var(--border-color);
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

  @media (max-width: 768px) {
    .speaker-grid {
      grid-template-columns: 1fr;
    }

    .modal-content {
      width: 95%;
      max-height: 90vh;
    }

    .merge-actions {
      flex-direction: column;
    }
  }
</style>
