<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { fade } from 'svelte/transition';
  import type { Group } from '$lib/types/groups';
  import { GroupsApi } from '$lib/api/groups';
  import { toastStore } from '$stores/toast';
  import { t } from '$stores/locale';

  export let isOpen = false;

  const dispatch = createEventDispatcher<{
    created: Group;
    close: void;
  }>();

  let name = '';
  let description = '';
  let isCreating = false;

  function resetForm() {
    name = '';
    description = '';
    isCreating = false;
  }

  function handleClose() {
    resetForm();
    isOpen = false;
    dispatch('close');
  }

  function handleBackdropClick(event: MouseEvent) {
    if (event.target === event.currentTarget) {
      handleClose();
    }
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      handleClose();
    }
  }

  async function handleSubmit() {
    if (!name.trim()) return;
    isCreating = true;

    try {
      const group = await GroupsApi.createGroup({
        name: name.trim(),
        description: description.trim() || undefined,
      });

      toastStore.success($t('groups.toast.groupCreated'));
      dispatch('created', group);
      handleClose();
    } catch (err: any) {
      const message = err?.response?.data?.detail || $t('groups.toast.createGroupFailed');
      toastStore.error(message);
    } finally {
      isCreating = false;
    }
  }
</script>

{#if isOpen}
  <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
  <div
    class="modal-backdrop"
    transition:fade={{ duration: 200 }}
    on:click={handleBackdropClick}
    on:keydown={handleKeydown}
    tabindex="-1"
    role="dialog"
    aria-modal="true"
    aria-labelledby="create-group-title"
  >
    <div class="modal-container" transition:fade={{ duration: 200, delay: 100 }}>
      <div class="modal-content">
        <div class="modal-header">
          <h2 id="create-group-title" class="modal-title">{$t('groups.createGroup')}</h2>
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

        <form on:submit|preventDefault={handleSubmit}>
          <div class="modal-body">
            <div class="form-group">
              <label for="group-name">{$t('groups.groupName')}</label>
              <input
                type="text"
                id="group-name"
                class="form-control"
                bind:value={name}
                maxlength="255"
                placeholder={$t('groups.groupNamePlaceholder')}
                required
              />
            </div>

            <div class="form-group">
              <label for="group-description">{$t('groups.description')}</label>
              <textarea
                id="group-description"
                class="form-control form-textarea"
                bind:value={description}
                rows="3"
                placeholder={$t('groups.descriptionPlaceholder')}
              ></textarea>
            </div>
          </div>

          <div class="modal-footer">
            <button
              type="button"
              class="modal-button cancel-button"
              on:click={handleClose}
            >
              {$t('modal.cancel')}
            </button>
            <button
              type="submit"
              class="modal-button confirm-button"
              disabled={!name.trim() || isCreating}
            >
              {isCreating ? $t('groups.creating') : $t('groups.createGroup')}
            </button>
          </div>
        </form>
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
    z-index: 1200;
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
    font-size: 1.125rem;
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
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .form-group {
    display: flex;
    flex-direction: column;
    gap: 0.375rem;
  }

  .form-group label {
    font-weight: 500;
    color: var(--text-color);
    font-size: 0.8125rem;
  }

  .form-control {
    padding: 0.5rem 0.625rem;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    background-color: var(--surface-color);
    color: var(--text-color);
    font-size: 0.8125rem;
    transition: border-color 0.15s, box-shadow 0.15s;
  }

  .form-control:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 3px var(--primary-light);
  }

  .form-control::placeholder {
    color: var(--text-secondary);
    opacity: 0.7;
  }

  .form-textarea {
    resize: vertical;
    min-height: 60px;
    font-family: inherit;
  }

  .modal-footer {
    display: flex;
    gap: 0.75rem;
    padding: 1rem 1.5rem 1.5rem;
    justify-content: flex-end;
    border-top: 1px solid var(--border-color);
  }

  .modal-button {
    padding: 0.5rem 1.25rem;
    border: none;
    border-radius: 8px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
  }

  .cancel-button {
    background: var(--card-background);
    color: var(--text-color);
    border: 1px solid var(--border-color);
  }

  .cancel-button:hover {
    background: var(--background-color);
  }

  .confirm-button {
    background: var(--primary-color);
    color: white;
  }

  .confirm-button:hover:not(:disabled) {
    background: var(--primary-hover);
  }

  .confirm-button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  :global([data-theme='dark']) .modal-backdrop {
    background: var(--modal-backdrop, rgba(0, 0, 0, 0.7));
  }

  :global([data-theme='dark']) .modal-container {
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3), 0 10px 10px -5px rgba(0, 0, 0, 0.2);
  }

  @media (prefers-reduced-motion: reduce) {
    .modal-container {
      animation: none;
    }
  }
</style>
