<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { fade } from 'svelte/transition';
  import { t } from '$stores/locale';

  export let isOpen = false;
  export let title = '';
  export let message = '';
  export let confirmText = '';
  export let cancelText = '';
  export let confirmButtonClass = 'confirm-button';
  export let cancelButtonClass = 'cancel-button';

  // Apply defaults from translations if not provided
  $: title = title || $t('modal.confirmAction');
  $: message = message || $t('modal.confirmMessage');
  $: confirmText = confirmText || $t('modal.confirm');
  $: cancelText = cancelText || $t('modal.cancel');

  const dispatch = createEventDispatcher();

  function handleConfirm() {
    dispatch('confirm');
    isOpen = false;
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
    dispatch('close');
    isOpen = false;
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      handleClose();
    } else if (event.key === 'Enter') {
      handleConfirm();
    }
  }
</script>

{#if isOpen}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div
    class="modal-backdrop"
    transition:fade={{ duration: 200 }}
    on:click={handleBackdropClick}
    on:keydown={handleKeydown}
    tabindex="-1"
    role="dialog"
    aria-modal="true"
    aria-labelledby="modal-title"
    aria-describedby="modal-message"
  >
    <div class="modal-container" transition:fade={{ duration: 200, delay: 100 }}>
      <div class="modal-content">
        <div class="modal-header">
          <h2 id="modal-title" class="modal-title">{title}</h2>
          <button
            class="modal-close-button"
            on:click={handleClose}
            aria-label={$t('modal.closeDialog')}
            title={$t('modal.closeDialog')}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>

        <div class="modal-body">
          <p id="modal-message" class="modal-message">{message}</p>
        </div>

        <div class="modal-footer">
          {#if cancelText}
            <button
              class="modal-button {cancelButtonClass}"
              on:click={handleCancel}
              type="button"
            >
              {cancelText}
            </button>
          {/if}
          <button
            class="modal-button {confirmButtonClass}"
            on:click={handleConfirm}
            type="button"
          >
            {confirmText}
          </button>
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
    z-index: 1200;  /* Higher than SettingsModal (1100) to appear on top */
    padding: 1rem;
  }

  .modal-container {
    background: var(--background-color);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    max-width: 500px;
    width: 100%;
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
  }

  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1.5rem;
    border-bottom: 1px solid var(--border-color);
  }

  .modal-title {
    margin: 0;
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--text-color);
    line-height: 1.4;
  }

  .modal-close-button {
    background: none;
    border: none;
    cursor: pointer;
    padding: 0.5rem;
    color: var(--text-secondary);
    transition: color 0.2s ease;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .modal-close-button:hover {
    color: var(--text-color);
    background: var(--button-hover);
  }

  .modal-body {
    padding: 1.5rem;
  }

  .modal-message {
    margin: 0;
    color: var(--text-secondary);
    line-height: 1.5;
    font-size: 0.95rem;
  }

  .modal-footer {
    display: flex;
    gap: 0.75rem;
    padding: 1rem 1.5rem 2rem;
    justify-content: flex-end;
    border-top: 1px solid var(--border-color);
    margin-top: 0.5rem;
  }

  .modal-button {
    padding: 0.6rem 1.2rem;
    border: none;
    border-radius: 10px;
    font-size: 0.95rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    min-width: 120px;
  }

  .cancel-button {
    background: var(--card-background);
    color: var(--text-color);
    border: 1px solid var(--border-color);
    padding: 0.6rem 1.2rem;
    border-radius: 10px;
    font-size: 0.95rem;
    font-weight: 500;
    transition: all 0.2s ease;
    cursor: pointer;
    box-shadow: var(--card-shadow);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    min-width: 120px;
    /* Ensure high contrast */
    opacity: 1;
  }

  .cancel-button:hover {
    background: var(--primary-color);
    color: white;
    border-color: var(--primary-color);
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }

  .cancel-button:active {
    transform: translateY(0);
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }

  .confirm-button {
    background: #3b82f6;
    color: white;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }

  .confirm-button:hover {
    background: #2563eb;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.3);
  }

  .confirm-button:active {
    transform: translateY(0);
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
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

  :global([data-theme='dark']) .modal-close-button:hover {
    background: var(--button-hover, rgba(255, 255, 255, 0.1));
  }

  :global([data-theme='dark']) .cancel-button:hover {
    background: #3b82f6;
    color: white;
    border-color: #3b82f6;
  }

  :global([data-theme='dark']) .modal-footer {
    border-top-color: var(--border-color);
  }

  /* Responsive design */
  @media (max-width: 480px) {
    .modal-container {
      margin: 1rem;
      max-width: none;
    }

    .modal-footer {
      flex-direction: column-reverse;
    }

    .modal-button {
      width: 100%;
    }
  }

  /* Focus styles for accessibility */
  .modal-button:focus {
    outline: 2px solid #3b82f6;
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
  }
</style>
