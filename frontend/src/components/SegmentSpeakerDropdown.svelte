<script lang="ts">
  import { createEventDispatcher, onMount, onDestroy } from 'svelte';
  import { getSpeakerColor } from '$lib/utils/speakerColors';
  import type { Speaker, Segment } from '$lib/types/speaker';
  import { t } from '$stores/locale';
  import { translateSpeakerLabel } from '$lib/i18n';
  import axiosInstance from '$lib/axios';

  export let segment: Segment;
  export let speakers: Speaker[] = [];
  export let mediaFileUuid: string = '';

  const dispatch = createEventDispatcher();
  let triggerButton: HTMLButtonElement;
  let portalContainer: HTMLDivElement | null = null;
  let isOpen = false;
  let isCreatingSpeaker = false;

  // Compute the next speaker name (e.g., SPEAKER_03 if SPEAKER_00, SPEAKER_01, SPEAKER_02 exist)
  function getNextSpeakerName(): string {
    let maxNumber = -1;
    for (const speaker of speakers) {
      const match = speaker.name?.match(/^SPEAKER_(\d+)$/);
      if (match) {
        const num = parseInt(match[1], 10);
        if (num > maxNumber) maxNumber = num;
      }
    }
    const nextNum = maxNumber + 1;
    return `SPEAKER_${nextNum.toString().padStart(2, '0')}`;
  }

  async function handleCreateNewSpeaker() {
    if (!mediaFileUuid || isCreatingSpeaker) return;

    isCreatingSpeaker = true;
    const newSpeakerName = getNextSpeakerName();

    try {
      const response = await axiosInstance.post(`/speakers/?media_file_uuid=${mediaFileUuid}`, {
        name: newSpeakerName
      });

      const newSpeaker = response.data;

      // Dispatch event to notify parent that a new speaker was created
      dispatch('speakerCreated', { speaker: newSpeaker });

      // Auto-select the new speaker for this segment
      dispatch('change', {
        segmentUuid: segment.uuid,
        speakerUuid: newSpeaker.uuid
      });

      closeDropdown();
    } catch (error) {
      console.error('Failed to create new speaker:', error);
    } finally {
      isCreatingSpeaker = false;
    }
  }

  // Create portal container on mount
  onMount(() => {
    portalContainer = document.createElement('div');
    portalContainer.className = 'speaker-dropdown-portal';
    document.body.appendChild(portalContainer);
  });

  // Cleanup on destroy
  onDestroy(() => {
    if (portalContainer) {
      document.body.removeChild(portalContainer);
      portalContainer = null;
    }
    document.removeEventListener('click', handleGlobalClick, true);
    window.removeEventListener('scroll', closeDropdown, true);
    window.removeEventListener('resize', closeDropdown);
  });

  function closeDropdown() {
    if (isOpen) {
      isOpen = false;
      renderPortal();
    }
  }

  function handleGlobalClick(event: MouseEvent) {
    const target = event.target as Node;
    if (triggerButton?.contains(target)) return;
    if (portalContainer?.contains(target)) return;
    closeDropdown();
  }

  function toggleDropdown(event: MouseEvent) {
    event.preventDefault();
    event.stopPropagation();

    isOpen = !isOpen;

    if (isOpen) {
      document.addEventListener('click', handleGlobalClick, true);
      window.addEventListener('scroll', closeDropdown, true);
      window.addEventListener('resize', closeDropdown);
    } else {
      document.removeEventListener('click', handleGlobalClick, true);
      window.removeEventListener('scroll', closeDropdown, true);
      window.removeEventListener('resize', closeDropdown);
    }

    renderPortal();
  }

  function handleSpeakerSelect(speakerUuid: string | null) {
    dispatch('change', {
      segmentUuid: segment.uuid,
      speakerUuid
    });
    closeDropdown();
  }

  function isCurrentSpeaker(speakerUuid: string): boolean {
    if (!segment.speaker) return false;
    return segment.speaker.uuid === speakerUuid;
  }

  function getMenuPosition(): { top: number; left: number } {
    if (!triggerButton) return { top: 0, left: 0 };

    const rect = triggerButton.getBoundingClientRect();
    const menuHeight = 300;
    const viewportHeight = window.innerHeight;

    let top: number;
    if (rect.bottom + menuHeight + 4 > viewportHeight) {
      top = Math.max(4, rect.top - menuHeight - 4);
    } else {
      top = rect.bottom + 4;
    }

    return { top, left: rect.left };
  }

  function renderPortal() {
    if (!portalContainer) return;

    if (!isOpen) {
      portalContainer.innerHTML = '';
      return;
    }

    const pos = getMenuPosition();
    const currentSpeakerUuid = segment.speaker?.uuid;

    // Build menu HTML
    let menuHtml = `
      <div class="dropdown-menu" style="top: ${pos.top}px; left: ${pos.left}px;">
        <div class="dropdown-header">${$t('speaker.assignSpeaker')}</div>
        <button class="dropdown-item ${!segment.speaker ? 'selected' : ''}" data-speaker-uuid="">
          <div class="speaker-option">
            <div class="speaker-color-indicator no-speaker"></div>
            <span>${$t('speaker.noSpeaker')}</span>
          </div>
          ${!segment.speaker ? '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>' : ''}
        </button>
        <div class="dropdown-divider"></div>
    `;

    for (const speaker of speakers) {
      const isSelected = speaker.uuid === currentSpeakerUuid;
      const color = getSpeakerColor(speaker.name);
      menuHtml += `
        <button class="dropdown-item ${isSelected ? 'selected' : ''}" data-speaker-uuid="${speaker.uuid}">
          <div class="speaker-option">
            <div class="speaker-color-indicator" style="background-color: ${color.bg}; border-color: ${color.border};"></div>
            <span>${translateSpeakerLabel(speaker.display_name || speaker.name)}</span>
          </div>
          ${isSelected ? '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>' : ''}
        </button>
      `;
    }

    // Add "Create New Speaker" button if mediaFileUuid is available
    if (mediaFileUuid) {
      const nextSpeakerName = getNextSpeakerName();
      menuHtml += `
        <div class="dropdown-divider"></div>
        <button class="dropdown-item create-speaker-btn" data-action="create-speaker">
          <div class="speaker-option">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="12" y1="5" x2="12" y2="19"></line>
              <line x1="5" y1="12" x2="19" y2="12"></line>
            </svg>
            <span>${$t('speaker.createNew')} ${nextSpeakerName}</span>
          </div>
        </button>
      `;
    }

    menuHtml += '</div>';
    portalContainer.innerHTML = menuHtml;

    // Add click handlers
    const buttons = portalContainer.querySelectorAll('.dropdown-item');
    buttons.forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const action = (btn as HTMLElement).dataset.action;
        if (action === 'create-speaker') {
          handleCreateNewSpeaker();
          return;
        }
        const uuid = (btn as HTMLElement).dataset.speakerUuid;
        handleSpeakerSelect(uuid === '' ? null : uuid || null);
      });
    });
  }
</script>

<svelte:head>
  <style>
    .speaker-dropdown-portal .dropdown-menu {
      position: fixed;
      background: var(--surface-color, #1e293b);
      border: 1px solid var(--border-color, #334155);
      border-radius: 8px;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
      z-index: 10000;
      min-width: 200px;
      max-height: 300px;
      overflow-y: auto;
      padding: 4px;
    }

    .speaker-dropdown-portal .dropdown-header {
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      color: var(--text-secondary, #94a3b8);
      padding: 8px 12px 4px 12px;
      letter-spacing: 0.5px;
    }

    .speaker-dropdown-portal .dropdown-divider {
      height: 1px;
      background: var(--border-light, #475569);
      margin: 4px 0;
    }

    .speaker-dropdown-portal .dropdown-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      width: 100%;
      padding: 8px 12px;
      background: none;
      border: none;
      border-radius: 6px;
      cursor: pointer;
      transition: background-color 0.15s ease;
      color: var(--text-primary, #f1f5f9);
      font-size: 14px;
      text-align: left;
    }

    .speaker-dropdown-portal .dropdown-item:hover {
      background: var(--surface-hover, #334155);
    }

    .speaker-dropdown-portal .dropdown-item.selected {
      background: rgba(59, 130, 246, 0.15);
    }

    .speaker-dropdown-portal .speaker-option {
      display: flex;
      align-items: center;
      gap: 8px;
      flex: 1;
      min-width: 0;
    }

    .speaker-dropdown-portal .speaker-option span {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .speaker-dropdown-portal .speaker-color-indicator {
      width: 12px;
      height: 12px;
      border-radius: 50%;
      border: 1px solid;
      flex-shrink: 0;
    }

    .speaker-dropdown-portal .speaker-color-indicator.no-speaker {
      background: var(--border-color, #475569);
      border-color: var(--border-hover, #64748b);
    }

    .speaker-dropdown-portal .create-speaker-btn {
      color: var(--primary-color, #3b82f6);
    }

    .speaker-dropdown-portal .create-speaker-btn:hover {
      background: rgba(59, 130, 246, 0.1);
    }

    .speaker-dropdown-portal .create-speaker-btn svg {
      color: var(--primary-color, #3b82f6);
      margin-right: 4px;
    }

    .speaker-dropdown-portal .dropdown-menu::-webkit-scrollbar {
      width: 6px;
    }

    .speaker-dropdown-portal .dropdown-menu::-webkit-scrollbar-track {
      background: var(--background-secondary, #0f172a);
      border-radius: 3px;
    }

    .speaker-dropdown-portal .dropdown-menu::-webkit-scrollbar-thumb {
      background: var(--border-color, #475569);
      border-radius: 3px;
    }
  </style>
</svelte:head>

<div class="speaker-dropdown-container">
  <button
    class="speaker-trigger"
    bind:this={triggerButton}
    on:click={toggleDropdown}
    title={$t('speaker.clickToChangeSpeaker')}
  >
    <div
      class="segment-speaker"
      style="background-color: {getSpeakerColor(segment.speaker?.name || segment.speaker_label || 'Unknown').bg}; border-color: {getSpeakerColor(segment.speaker?.name || segment.speaker_label || 'Unknown').border}; --speaker-light: {getSpeakerColor(segment.speaker?.name || segment.speaker_label || 'Unknown').textLight}; --speaker-dark: {getSpeakerColor(segment.speaker?.name || segment.speaker_label || 'Unknown').textDark};"
    >
      {translateSpeakerLabel(segment.speaker?.display_name || segment.speaker?.name || segment.speaker_label || $t('common.unknown'))}
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
</style>
