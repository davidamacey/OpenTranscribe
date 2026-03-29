<script lang="ts">
  import { t } from '$stores/locale';
  import { createEventDispatcher } from 'svelte';
  import { fade, scale } from 'svelte/transition';
  import { clickOutside } from '$lib/actions/clickOutside';

  export let sortBy: string = 'upload_time';
  export let sortOrder: 'asc' | 'desc' = 'desc';

  const dispatch = createEventDispatcher<{
    change: { sortBy: string; sortOrder: 'asc' | 'desc' };
  }>();

  let isOpen = false;

  const sortOptions = [
    { value: 'upload_time', label: 'gallery.sort.uploadDate' },
    { value: 'completed_at', label: 'gallery.sort.completedDate' },
    { value: 'filename', label: 'gallery.sort.filename' },
    { value: 'duration', label: 'gallery.sort.duration' },
    { value: 'file_size', label: 'gallery.sort.fileSize' },
  ];

  $: currentOption = sortOptions.find(opt => opt.value === sortBy) || sortOptions[0];

  function toggleDropdown() {
    isOpen = !isOpen;
  }

  function selectSort(value: string) {
    if (value === sortBy) {
      // Toggle direction if same field
      const newOrder = sortOrder === 'asc' ? 'desc' : 'asc';
      sortOrder = newOrder;
      dispatch('change', { sortBy, sortOrder: newOrder });
    } else {
      // Select new field with appropriate default direction
      sortBy = value;
      // Filename defaults to asc (A-Z), others default to desc (newest/longest first)
      const newOrder = value === 'filename' ? 'asc' : 'desc';
      sortOrder = newOrder;
      dispatch('change', { sortBy: value, sortOrder: newOrder });
    }
    isOpen = false;
  }

  function handleClickOutside() {
    isOpen = false;
  }
</script>

<div class="sort-dropdown" use:clickOutside on:click_outside={handleClickOutside}>
  <button
    type="button"
    class="sort-button"
    on:click={toggleDropdown}
    aria-label={$t('gallery.sort.label')}
    aria-expanded={isOpen}
  >
    <!-- Sort icon -->
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
    >
      <path d="m3 16 4 4 4-4" />
      <path d="M7 20V4" />
      <path d="m21 8-4-4-4 4" />
      <path d="M17 4v16" />
    </svg>

    <span class="sort-label">{$t(currentOption.label)}</span>

    <!-- Direction arrow -->
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
      class="direction-arrow"
      class:asc={sortOrder === 'asc'}
    >
      <polyline points="18 15 12 9 6 15"></polyline>
    </svg>
  </button>

  {#if isOpen}
    <div class="dropdown-menu" transition:scale={{ duration: 150, start: 0.95 }}>
      {#each sortOptions as option}
        <button
          type="button"
          class="dropdown-item"
          class:active={option.value === sortBy}
          on:click={() => selectSort(option.value)}
        >
          <span class="option-label">{$t(option.label)}</span>
          {#if option.value === sortBy}
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              class="option-arrow"
              class:asc={sortOrder === 'asc'}
            >
              <polyline points="18 15 12 9 6 15"></polyline>
            </svg>
          {/if}
        </button>
      {/each}
    </div>
  {/if}
</div>

<style>
  .sort-dropdown {
    position: relative;
    display: inline-block;
  }

  .sort-button {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.375rem 0.75rem;
    height: 30px;
    box-sizing: border-box;
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 10px;
    font-size: 0.8125rem;
    font-weight: 500;
    color: var(--text-secondary);
    cursor: pointer;
    transition: all 0.2s ease;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
    backdrop-filter: blur(8px);
    user-select: none;
  }

  :global([data-theme='light']) .sort-button,
  :global(:not([data-theme='dark'])) .sort-button {
    background: rgba(255, 255, 255, 0.9);
    border-color: rgba(0, 0, 0, 0.08);
    color: #6b7280;
  }

  :global([data-theme='dark']) .sort-button {
    background: rgba(30, 41, 59, 0.95);
    border-color: rgba(255, 255, 255, 0.1);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
    color: #cbd5e1;
  }

  .sort-button:hover {
    border-color: var(--primary-color);
    color: var(--text-primary);
  }

  .sort-button:focus {
    outline: 2px solid var(--primary-color);
    outline-offset: 2px;
  }

  .sort-button svg {
    flex-shrink: 0;
  }

  .direction-arrow {
    transition: transform 0.2s ease;
  }

  .direction-arrow.asc {
    transform: rotate(180deg);
  }

  .dropdown-menu {
    position: absolute;
    top: calc(100% + 0.5rem);
    left: 0;
    min-width: 200px;
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
    padding: 0.5rem;
    z-index: 50;
    backdrop-filter: blur(12px);
  }

  :global([data-theme='light']) .dropdown-menu,
  :global(:not([data-theme='dark'])) .dropdown-menu {
    background: rgba(255, 255, 255, 0.95);
    border-color: rgba(0, 0, 0, 0.1);
  }

  :global([data-theme='dark']) .dropdown-menu {
    background: rgba(30, 41, 59, 0.95);
    border-color: rgba(255, 255, 255, 0.15);
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
  }

  .dropdown-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    padding: 0.625rem 0.75rem;
    background: transparent;
    border: none;
    border-radius: 8px;
    font-size: 0.875rem;
    color: var(--text-secondary);
    cursor: pointer;
    transition: all 0.15s ease;
    text-align: left;
  }

  :global([data-theme='light']) .dropdown-item,
  :global(:not([data-theme='dark'])) .dropdown-item {
    color: #6b7280;
  }

  :global([data-theme='dark']) .dropdown-item {
    color: #cbd5e1;
  }

  .dropdown-item:hover {
    background: var(--hover-bg);
    color: var(--text-primary);
  }

  :global([data-theme='light']) .dropdown-item:hover,
  :global(:not([data-theme='dark'])) .dropdown-item:hover {
    background: rgba(0, 0, 0, 0.05);
    color: #1f2937;
  }

  :global([data-theme='dark']) .dropdown-item:hover {
    background: rgba(255, 255, 255, 0.1);
    color: #f9fafb;
  }

  .dropdown-item.active {
    color: var(--primary-color);
    font-weight: 600;
  }

  .option-label {
    flex: 1;
  }

  .option-arrow {
    flex-shrink: 0;
    margin-left: 0.5rem;
    transition: transform 0.2s ease;
  }

  .option-arrow.asc {
    transform: rotate(180deg);
  }

  /* Hide sort label on tablet and below to save space */
  @media (max-width: 1200px) {
    .sort-label {
      display: none;
    }
  }

  @media (max-width: 768px) {
    .sort-button {
      font-size: 0.8125rem;
      padding: 0.4rem 0.75rem;
    }

    .dropdown-menu {
      min-width: 180px;
    }
  }
</style>
