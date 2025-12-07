<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { getSpeakerColor } from '$lib/utils/speakerColors';

  export let segment: any;
  export let speakers: any[] = [];
  export let isOpen: boolean = false;

  const dispatch = createEventDispatcher();
  let dropdownElement: HTMLDivElement;

  // Close dropdown when clicking outside
  function handleClickOutside(event: MouseEvent) {
    if (dropdownElement && !dropdownElement.contains(event.target as Node)) {
      isOpen = false;
    }
  }

  onMount(() => {
    if (isOpen) {
      document.addEventListener('click', handleClickOutside);
    }
    return () => {
      document.removeEventListener('click', handleClickOutside);
    };
  });

  $: if (isOpen) {
    document.addEventListener('click', handleClickOutside);
  } else {
    document.removeEventListener('click', handleClickOutside);
  }

  function handleSpeakerSelect(speakerUuid: string | null) {
    dispatch('change', {
      segmentUuid: segment.uuid || segment.id,
      speakerUuid
    });
    isOpen = false;
  }

  function isCurrentSpeaker(speakerUuid: string): boolean {
    if (!segment.speaker) return false;
    return segment.speaker.uuid === speakerUuid || segment.speaker.id === speakerUuid;
  }

  function toggleDropdown(event: Event) {
    event.stopPropagation();
    isOpen = !isOpen;
  }
</script>

<div class="speaker-dropdown-container" bind:this={dropdownElement}>
  <button
    class="speaker-trigger"
    on:click={toggleDropdown}
    title="Click to change speaker"
  >
    <div
      class="segment-speaker"
      style="background-color: {getSpeakerColor(segment.speaker?.name || segment.speaker_label || 'Unknown').bg}; border-color: {getSpeakerColor(segment.speaker?.name || segment.speaker_label || 'Unknown').border}; --speaker-light: {getSpeakerColor(segment.speaker?.name || segment.speaker_label || 'Unknown').textLight}; --speaker-dark: {getSpeakerColor(segment.speaker?.name || segment.speaker_label || 'Unknown').textDark};"
    >
      {segment.speaker?.display_name || segment.speaker?.name || segment.speaker_label || 'Unknown'}
    </div>
    <svg
      class="dropdown-arrow"
      class:open={isOpen}
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
    >
      <polyline points="6 9 12 15 18 9"></polyline>
    </svg>
  </button>

  {#if isOpen}
    <div class="dropdown-menu">
      <div class="dropdown-header">Assign speaker:</div>

      <!-- No Speaker option -->
      <button
        class="dropdown-item"
        class:selected={!segment.speaker}
        on:click={() => handleSpeakerSelect(null)}
      >
        <div class="speaker-option">
          <div class="speaker-color-indicator no-speaker"></div>
          <span>No Speaker</span>
        </div>
        {#if !segment.speaker}
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="20 6 9 17 4 12"></polyline>
          </svg>
        {/if}
      </button>

      <div class="dropdown-divider"></div>

      <!-- Speaker options -->
      {#each speakers as speaker}
        <button
          class="dropdown-item"
          class:selected={isCurrentSpeaker(speaker.uuid)}
          on:click={() => handleSpeakerSelect(speaker.uuid)}
        >
          <div class="speaker-option">
            <div
              class="speaker-color-indicator"
              style="background-color: {getSpeakerColor(speaker.name).bg}; border-color: {getSpeakerColor(speaker.name).border};"
            ></div>
            <span>{speaker.display_name || speaker.name}</span>
          </div>
          {#if isCurrentSpeaker(speaker.uuid)}
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
          {/if}
        </button>
      {/each}
    </div>
  {/if}
</div>

<style>
  .speaker-dropdown-container {
    position: relative;
    display: inline-block;
  }

  .speaker-trigger {
    display: flex;
    align-items: center;
    gap: 4px;
    background: none;
    border: none;
    cursor: pointer;
    padding: 0;
  }

  .segment-speaker {
    font-size: 12px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 12px;
    white-space: nowrap;
    min-width: fit-content;
    max-width: 150px;
    overflow: hidden;
    text-overflow: ellipsis;
    border: 1px solid;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    transition: all 0.2s ease;
    color: var(--speaker-light);
  }

  :global([data-theme='dark']) .segment-speaker {
    color: var(--speaker-dark);
  }

  .dropdown-arrow {
    color: var(--text-secondary);
    transition: transform 0.2s ease;
    flex-shrink: 0;
  }

  .dropdown-arrow.open {
    transform: rotate(180deg);
  }

  .speaker-trigger:hover .segment-speaker {
    opacity: 0.8;
  }

  .dropdown-menu {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    z-index: 1000;
    min-width: 200px;
    max-height: 300px;
    overflow-y: auto;
    padding: 4px;
  }

  .dropdown-header {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    color: var(--text-secondary);
    padding: 8px 12px 4px 12px;
    letter-spacing: 0.5px;
  }

  .dropdown-divider {
    height: 1px;
    background: var(--border-light);
    margin: 4px 0;
  }

  .dropdown-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    padding: 8px 12px;
    background: none;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s ease;
    color: var(--text-primary);
    font-size: 14px;
    text-align: left;
  }

  .dropdown-item:hover {
    background: var(--surface-hover);
  }

  .dropdown-item.selected {
    background: rgba(59, 130, 246, 0.1);
  }

  .speaker-option {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
    min-width: 0;
  }

  .speaker-option span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .speaker-color-indicator {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    border: 1px solid;
    flex-shrink: 0;
  }

  .speaker-color-indicator.no-speaker {
    background: var(--border-color);
    border-color: var(--border-hover);
  }

  /* Scrollbar styling */
  .dropdown-menu::-webkit-scrollbar {
    width: 6px;
  }

  .dropdown-menu::-webkit-scrollbar-track {
    background: var(--background-secondary);
    border-radius: 3px;
  }

  .dropdown-menu::-webkit-scrollbar-thumb {
    background: var(--border-color);
    border-radius: 3px;
  }

  .dropdown-menu::-webkit-scrollbar-thumb:hover {
    background: var(--text-secondary);
  }
</style>
