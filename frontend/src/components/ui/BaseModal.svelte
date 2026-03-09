<!--
  BaseModal.svelte — Shared modal wrapper component.

  Extracts common modal chrome (backdrop, container, header, close button,
  body, footer) that was duplicated across 6+ modal components.

  Usage:
    <BaseModal {isOpen} title="My Modal" onClose={handleClose}>
      <p>Modal body content</p>
      <svelte:fragment slot="footer">
        <button on:click={handleClose}>Cancel</button>
        <button on:click={handleSave}>Save</button>
      </svelte:fragment>
    </BaseModal>
-->
<script lang="ts">
  import { onDestroy } from 'svelte';

  export let isOpen = false;
  export let title = '';
  export let maxWidth = '600px';
  export let zIndex = 1000;
  export let onClose: () => void = () => {};

  // Lock body scroll when modal is open
  $: if (typeof document !== 'undefined') {
    document.body.style.overflow = isOpen ? 'hidden' : '';
  }

  onDestroy(() => {
    if (typeof document !== 'undefined') {
      document.body.style.overflow = '';
    }
  });

  function handleBackdropClick(event: MouseEvent) {
    if (event.target === event.currentTarget) onClose();
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') onClose();
  }
</script>

<svelte:window on:keydown={handleKeydown} />

{#if isOpen}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div class="modal-backdrop" style="z-index: {zIndex}" on:click={handleBackdropClick}>
    <div class="modal-container" style="max-width: {maxWidth}">
      <div class="modal-header">
        {#if $$slots.header}
          <div class="modal-header-content">
            <slot name="header" />
          </div>
        {:else}
          <h2>{title}</h2>
        {/if}
        <button class="modal-close-button" on:click={onClose} aria-label="Close modal">
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
      </div>
      <div class="modal-body">
        <slot />
      </div>
      {#if $$slots.footer}
        <div class="modal-footer">
          <slot name="footer" />
        </div>
      {/if}
    </div>
  </div>
{/if}

<style>
  .modal-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background-color: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    overscroll-behavior: contain;
  }

  .modal-container {
    background: var(--bg-primary, #ffffff);
    border: 1px solid var(--border-color, #e0e0e0);
    border-radius: 12px;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
    width: 90%;
    max-height: 90vh;
    display: flex;
    flex-direction: column;
    animation: slideIn 0.2s ease-out;
  }

  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1.5rem;
    border-bottom: 1px solid var(--border-color, #e0e0e0);
    flex-shrink: 0;
  }

  .modal-header h2 {
    margin: 0;
    font-size: 1.25rem;
    color: var(--text-primary, #1a1a1a);
  }

  .modal-header-content {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex: 1;
    min-width: 0;
    gap: 0.75rem;
  }

  .modal-close-button {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--text-secondary, #666);
    padding: 0.5rem;
    margin-left: 1rem;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: color 0.2s ease, background-color 0.2s ease;
    flex-shrink: 0;
  }

  .modal-close-button:hover {
    color: var(--text-color, var(--text-primary, #1a1a1a));
    background-color: var(--button-hover, var(--bg-hover, #f0f0f0));
  }

  .modal-body {
    padding: 1.5rem;
    overflow-y: auto;
    flex: 1;
    overscroll-behavior: contain;
  }

  .modal-footer {
    display: flex;
    gap: 0.75rem;
    padding: 1rem 1.5rem;
    justify-content: flex-end;
    border-top: 1px solid var(--border-color, #e0e0e0);
    flex-shrink: 0;
  }

  @keyframes slideIn {
    from {
      opacity: 0;
      transform: translateY(-10px) scale(0.98);
    }
    to {
      opacity: 1;
      transform: translateY(0) scale(1);
    }
  }
</style>
