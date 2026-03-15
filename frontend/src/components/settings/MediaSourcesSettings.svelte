<script lang="ts">
  import { onMount } from 'svelte';
  import { t } from '$stores/locale';
  import { toastStore } from '$stores/toast';
  import Spinner from '../ui/Spinner.svelte';
  import {
    getMediaSources,
    addMediaSource,
    updateMediaSource,
    deleteMediaSource,
    toggleMediaSourceShare,
    type MediaSource,
    type MediaSourceUpdate
  } from '$lib/api/mediaSourcesApi';

  let loading = true;
  let sources: MediaSource[] = [];
  let sharedSources: MediaSource[] = [];
  let saving = false;

  // Add form state
  let showAddForm = false;
  let newHostname = '';
  let newLabel = '';
  let newUsername = '';
  let newPassword = '';
  let newVerifySsl = true;
  let newProviderType = 'mediacms';

  // Edit state
  let editingUuid: string | null = null;
  let editHostname = '';
  let editLabel = '';
  let editUsername = '';
  let editPassword = '';
  let editVerifySsl = true;

  // Delete confirmation
  let deletingUuid: string | null = null;

  onMount(async () => {
    await loadSources();
  });

  async function loadSources() {
    loading = true;
    try {
      const resp = await getMediaSources();
      sources = resp.sources || [];
      sharedSources = resp.shared_sources || [];
    } catch (err) {
      console.error('Failed to load media sources:', err);
      toastStore.error($t('settings.mediaSources.loadFailed'));
    } finally {
      loading = false;
    }
  }

  function resetAddForm() {
    newHostname = '';
    newLabel = '';
    newUsername = '';
    newPassword = '';
    newVerifySsl = true;
    newProviderType = 'mediacms';
    showAddForm = false;
  }

  async function handleAdd() {
    if (!newHostname.trim()) return;
    saving = true;
    try {
      const created = await addMediaSource({
        hostname: newHostname.trim().toLowerCase(),
        provider_type: newProviderType,
        username: newUsername,
        password: newPassword,
        verify_ssl: newVerifySsl,
        label: newLabel.trim(),
      });
      sources = [...sources, created];
      resetAddForm();
      toastStore.success($t('settings.mediaSources.addSuccess'));
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      toastStore.error(detail || $t('settings.mediaSources.addFailed'));
    } finally {
      saving = false;
    }
  }

  function startEdit(source: MediaSource) {
    showAddForm = false;
    deletingUuid = null;
    editingUuid = source.uuid;
    editHostname = source.hostname;
    editLabel = source.label;
    editUsername = source.username || '';
    editPassword = '';
    editVerifySsl = source.verify_ssl;
  }

  function cancelEdit() {
    editingUuid = null;
  }

  async function handleUpdate() {
    if (!editingUuid || !editHostname.trim()) return;
    saving = true;
    try {
      const updateData: MediaSourceUpdate = {
        hostname: editHostname.trim().toLowerCase(),
        label: editLabel.trim(),
        username: editUsername,
        verify_ssl: editVerifySsl,
      };
      // Only send password if user typed something new
      if (editPassword) {
        updateData.password = editPassword;
      }
      const updated = await updateMediaSource(editingUuid, updateData);
      sources = sources.map(s => s.uuid === editingUuid ? updated : s);
      editingUuid = null;
      toastStore.success($t('settings.mediaSources.updateSuccess'));
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      toastStore.error(detail || $t('settings.mediaSources.updateFailed'));
    } finally {
      saving = false;
    }
  }

  async function handleDelete(uuid: string) {
    saving = true;
    try {
      await deleteMediaSource(uuid);
      sources = sources.filter(s => s.uuid !== uuid);
      deletingUuid = null;
      toastStore.success($t('settings.mediaSources.deleteSuccess'));
    } catch (err) {
      toastStore.error($t('settings.mediaSources.deleteFailed'));
    } finally {
      saving = false;
    }
  }

  async function handleShareToggle(source: MediaSource) {
    if (saving) return;
    saving = true;
    const newShared = !source.is_shared;
    // Optimistic update
    sources = sources.map(s => s.uuid === source.uuid ? { ...s, is_shared: newShared } : s);
    try {
      const updated = await toggleMediaSourceShare(source.uuid, newShared);
      sources = sources.map(s => s.uuid === source.uuid ? updated : s);
      toastStore.success(newShared
        ? $t('settings.mediaSources.shareEnabled')
        : $t('settings.mediaSources.shareDisabled'));
    } catch {
      // Rollback
      sources = sources.map(s => s.uuid === source.uuid ? { ...s, is_shared: !newShared } : s);
      toastStore.error($t('settings.mediaSources.shareFailed'));
    } finally {
      saving = false;
    }
  }
</script>

{#if loading}
  <div class="loading-state">
    <Spinner size="small" />
    {$t('settings.mediaSources.loading')}
  </div>
{:else}
  <div class="media-sources">
    <!-- Own Sources -->
    {#if sources.length > 0}
      {#each sources as source (source.uuid)}
        <div class="source-card" class:editing={editingUuid === source.uuid}>
          {#if editingUuid === source.uuid}
            <!-- Edit Mode -->
            <form class="source-form" on:submit|preventDefault={handleUpdate}>
              <div class="form-row">
                <div class="form-field">
                  <label for="edit-hostname">{$t('settings.mediaSources.hostname')}</label>
                  <input id="edit-hostname" type="text" bind:value={editHostname} class="form-input" placeholder="media.example.com" />
                </div>
                <div class="form-field">
                  <label for="edit-label">{$t('settings.mediaSources.label')}</label>
                  <input id="edit-label" type="text" bind:value={editLabel} class="form-input" placeholder={$t('settings.mediaSources.labelPlaceholder')} />
                </div>
              </div>
              <div class="form-row">
                <div class="form-field">
                  <label for="edit-username">{$t('settings.mediaSources.username')}</label>
                  <input id="edit-username" type="text" bind:value={editUsername} class="form-input" autocomplete="off" />
                </div>
                <div class="form-field">
                  <label for="edit-password">{$t('settings.mediaSources.password')}</label>
                  <input id="edit-password" type="password" bind:value={editPassword} class="form-input" autocomplete="new-password"
                    placeholder={source.has_credentials ? '••••••••' : ''} />
                </div>
              </div>
              <div class="form-row">
                <label class="toggle-row-inline">
                  <input type="checkbox" bind:checked={editVerifySsl} />
                  <span>{$t('settings.mediaSources.verifySsl')}</span>
                </label>
              </div>
              <div class="form-actions-inline">
                <button type="button" class="btn btn-sm btn-secondary" on:click={cancelEdit} disabled={saving}>{$t('common.cancel')}</button>
                <button type="submit" class="btn btn-sm btn-primary" disabled={saving || !editHostname.trim()}>
                  {saving ? $t('common.saving') : $t('common.save')}
                </button>
              </div>
            </form>
          {:else}
            <!-- View Mode -->
            <div class="source-header">
              <div class="source-info">
                <div class="source-hostname">
                  <span class="hostname-badge">{source.provider_type}</span>
                  {source.hostname}
                  {#if source.is_shared}
                    <span class="shared-badge">{$t('settings.mediaSources.shared')}</span>
                  {/if}
                </div>
                {#if source.label}
                  <div class="source-label">{source.label}</div>
                {/if}
              </div>
              <div class="source-meta">
                {#if source.has_credentials}
                  <span class="meta-badge creds">{$t('settings.mediaSources.credentialsStored')}</span>
                {:else}
                  <span class="meta-badge no-creds">{$t('settings.mediaSources.noCreds')}</span>
                {/if}
                {#if !source.verify_ssl}
                  <span class="meta-badge ssl-off">{$t('settings.mediaSources.sslOff')}</span>
                {/if}
              </div>
            </div>
            <div class="source-actions">
              <button class="btn btn-sm btn-ghost" on:click={() => startEdit(source)} disabled={saving}>
                {$t('common.edit')}
              </button>
              {#if deletingUuid === source.uuid}
                <span class="delete-confirm">
                  {$t('settings.mediaSources.confirmDelete')}
                  <button class="btn btn-sm btn-danger" on:click={() => handleDelete(source.uuid)} disabled={saving}>
                    {$t('common.yes')}
                  </button>
                  <button class="btn btn-sm btn-ghost" on:click={() => deletingUuid = null}>
                    {$t('common.no')}
                  </button>
                </span>
              {:else}
                <button class="btn btn-sm btn-ghost btn-danger-text" on:click={() => deletingUuid = source.uuid} disabled={saving}>
                  {$t('common.delete')}
                </button>
              {/if}
              <div class="share-toggle">
                <label class="toggle-row-inline share-label">
                  <input type="checkbox" checked={source.is_shared}
                    on:change={() => handleShareToggle(source)} disabled={saving} />
                  <span>{$t('settings.mediaSources.shareGlobally')}</span>
                </label>
              </div>
            </div>
          {/if}
        </div>
      {/each}
    {/if}

    <!-- Shared by Others -->
    {#if sharedSources.length > 0}
      <div class="shared-section-header">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10" />
          <line x1="2" y1="12" x2="22" y2="12" />
          <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
        </svg>
        <span>{$t('settings.mediaSources.sharedByOthers')}</span>
      </div>

      {#each sharedSources as source (source.uuid)}
        <div class="source-card shared">
          <div class="source-header">
            <div class="source-info">
              <div class="source-hostname">
                <span class="hostname-badge">{source.provider_type}</span>
                {source.hostname}
                {#if source.owner_role === 'admin' || source.owner_role === 'super_admin'}
                  <span class="admin-badge">{$t('settings.sharing.adminBadge')}</span>
                {/if}
              </div>
              {#if source.label}
                <div class="source-label">{source.label}</div>
              {/if}
              {#if source.owner_name}
                <div class="shared-by">{$t('settings.mediaSources.sharedBy')} {source.owner_name}</div>
              {/if}
            </div>
            <div class="source-meta">
              {#if source.has_credentials}
                <span class="meta-badge creds">{$t('settings.mediaSources.credentialsStored')}</span>
              {:else}
                <span class="meta-badge no-creds">{$t('settings.mediaSources.noCreds')}</span>
              {/if}
              {#if !source.verify_ssl}
                <span class="meta-badge ssl-off">{$t('settings.mediaSources.sslOff')}</span>
              {/if}
            </div>
          </div>
        </div>
      {/each}
    {/if}

    <!-- Empty state -->
    {#if sources.length === 0 && sharedSources.length === 0 && !showAddForm}
      <div class="empty-state">
        <div class="empty-icon">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101" />
            <path d="M10.172 13.828a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.102 1.101" />
          </svg>
        </div>
        <p class="empty-text">{$t('settings.mediaSources.noSources')}</p>
        <p class="empty-hint">{$t('settings.mediaSources.noSourcesHint')}</p>
      </div>
    {/if}

    <!-- Add Form -->
    {#if showAddForm}
      <form class="source-card add-card" on:submit|preventDefault={handleAdd}>
        <div class="source-form">
          <div class="form-row">
            <div class="form-field">
              <label for="new-hostname">{$t('settings.mediaSources.hostname')}</label>
              <input id="new-hostname" type="text" bind:value={newHostname} class="form-input" placeholder="media.example.com" />
            </div>
            <div class="form-field">
              <label for="new-label">{$t('settings.mediaSources.label')}</label>
              <input id="new-label" type="text" bind:value={newLabel} class="form-input" placeholder={$t('settings.mediaSources.labelPlaceholder')} />
            </div>
          </div>
          <div class="form-row">
            <div class="form-field">
              <label for="new-username">{$t('settings.mediaSources.username')}</label>
              <input id="new-username" type="text" bind:value={newUsername} class="form-input" autocomplete="off" />
            </div>
            <div class="form-field">
              <label for="new-password">{$t('settings.mediaSources.password')}</label>
              <input id="new-password" type="password" bind:value={newPassword} class="form-input" autocomplete="new-password" />
            </div>
          </div>
          <div class="form-row">
            <div class="form-field">
              <label for="new-provider">{$t('settings.mediaSources.providerType')}</label>
              <select id="new-provider" bind:value={newProviderType} class="form-select">
                <option value="mediacms">MediaCMS</option>
              </select>
            </div>
            <label class="toggle-row-inline">
              <input type="checkbox" bind:checked={newVerifySsl} />
              <span>{$t('settings.mediaSources.verifySsl')}</span>
            </label>
          </div>
          <div class="form-actions-inline">
            <button type="button" class="btn btn-sm btn-secondary" on:click={resetAddForm} disabled={saving}>{$t('common.cancel')}</button>
            <button type="submit" class="btn btn-sm btn-primary" disabled={saving || !newHostname.trim()}>
              {saving ? $t('settings.mediaSources.adding') : $t('settings.mediaSources.addSource')}
            </button>
          </div>
        </div>
      </form>
    {/if}

    <!-- Add Button -->
    {#if !showAddForm}
      <button class="btn btn-add" on:click={() => { showAddForm = true; editingUuid = null; deletingUuid = null; }}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="12" y1="5" x2="12" y2="19" />
          <line x1="5" y1="12" x2="19" y2="12" />
        </svg>
        {$t('settings.mediaSources.addSource')}
      </button>
    {/if}

    <p class="section-hint">{$t('settings.mediaSources.hint')}</p>
  </div>
{/if}

<style>
  .loading-state {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 1rem 0;
    color: var(--text-secondary, #6b7280);
  }

  .media-sources {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 2rem 1rem;
    color: var(--text-secondary, #6b7280);
    text-align: center;
  }

  .empty-icon {
    opacity: 0.4;
    margin-bottom: 0.5rem;
  }

  .empty-text {
    font-size: 0.9rem;
    font-weight: 500;
    margin: 0;
    color: var(--text-color);
  }

  .empty-hint {
    font-size: 0.8rem;
    margin: 0.25rem 0 0;
  }

  .source-card {
    border: 1px solid var(--border-color, #e5e7eb);
    border-radius: 0.5rem;
    padding: 0.75rem 1rem;
    background: var(--card-background, var(--input-background));
    transition: border-color 0.15s;
  }

  .source-card:hover:not(.editing):not(.add-card) {
    border-color: var(--primary-color, #3b82f6);
  }

  .source-card.editing,
  .source-card.add-card {
    border-color: var(--primary-color, #3b82f6);
    border-width: 2px;
    padding: calc(0.75rem - 1px) calc(1rem - 1px);
  }

  .source-card.shared {
    border-left: 3px solid var(--info-color, #3b82f6);
    background: rgba(59, 130, 246, 0.04);
  }

  :global([data-theme='dark']) .source-card.shared {
    background: rgba(96, 165, 250, 0.06);
  }

  .shared-section-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.8rem;
    font-weight: 600;
    color: var(--text-secondary, #6b7280);
    text-transform: uppercase;
    letter-spacing: 0.03em;
    margin-top: 0.5rem;
  }

  .source-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 0.75rem;
  }

  .source-info {
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
    min-width: 0;
  }

  .source-hostname {
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--text-color);
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
  }

  .hostname-badge {
    font-size: 0.65rem;
    text-transform: uppercase;
    font-weight: 600;
    background: var(--primary-color, #3b82f6);
    color: white;
    padding: 0.1rem 0.35rem;
    border-radius: 0.25rem;
    letter-spacing: 0.02em;
    flex-shrink: 0;
  }

  .shared-badge {
    font-size: 0.6rem;
    text-transform: uppercase;
    font-weight: 600;
    background: rgba(34, 197, 94, 0.15);
    color: #16a34a;
    padding: 0.1rem 0.35rem;
    border-radius: 0.25rem;
    letter-spacing: 0.02em;
  }

  :global([data-theme='dark']) .shared-badge {
    background: rgba(34, 197, 94, 0.2);
    color: #4ade80;
  }

  .admin-badge {
    font-size: 0.6rem;
    text-transform: uppercase;
    font-weight: 600;
    background: rgba(99, 102, 241, 0.12);
    color: #6366f1;
    padding: 0.1rem 0.35rem;
    border-radius: 0.25rem;
    letter-spacing: 0.02em;
  }

  :global([data-theme='dark']) .admin-badge {
    background: rgba(99, 102, 241, 0.2);
    color: #818cf8;
  }

  .source-label {
    font-size: 0.75rem;
    color: var(--text-secondary, #6b7280);
  }

  .shared-by {
    font-size: 0.7rem;
    color: var(--text-secondary, #6b7280);
    font-style: italic;
  }

  .source-meta {
    display: flex;
    gap: 0.375rem;
    flex-shrink: 0;
  }

  .meta-badge {
    font-size: 0.65rem;
    padding: 0.15rem 0.4rem;
    border-radius: 0.25rem;
    font-weight: 500;
    white-space: nowrap;
  }

  .meta-badge.creds {
    background: rgba(34, 197, 94, 0.15);
    color: #16a34a;
  }

  .meta-badge.no-creds {
    background: rgba(234, 179, 8, 0.15);
    color: #ca8a04;
  }

  .meta-badge.ssl-off {
    background: rgba(239, 68, 68, 0.15);
    color: #dc2626;
  }

  .source-actions {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    margin-top: 0.5rem;
    padding-top: 0.5rem;
    border-top: 1px solid var(--border-color, #e5e7eb);
    flex-wrap: wrap;
  }

  .share-toggle {
    margin-left: auto;
  }

  .share-label {
    font-size: 0.75rem;
  }

  .delete-confirm {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    font-size: 0.75rem;
    color: var(--text-secondary);
  }

  .source-form {
    display: flex;
    flex-direction: column;
    gap: 0.625rem;
  }

  .form-row {
    display: flex;
    gap: 0.75rem;
    align-items: flex-end;
  }

  .form-field {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .form-field label {
    font-size: 0.75rem;
    font-weight: 500;
    color: var(--text-secondary, #6b7280);
  }

  .form-input,
  .form-select {
    padding: 0.375rem 0.5rem;
    border: 1px solid var(--input-border);
    border-radius: 0.375rem;
    background: var(--input-background);
    color: var(--text-color);
    font-size: 0.8rem;
  }

  .form-input:focus,
  .form-select:focus {
    outline: none;
    border-color: var(--primary-color, #3b82f6);
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.15);
  }

  .toggle-row-inline {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.8rem;
    color: var(--text-color);
    cursor: pointer;
  }

  .toggle-row-inline input[type="checkbox"] {
    width: 1rem;
    height: 1rem;
    accent-color: var(--primary-color, #3b82f6);
  }

  .form-actions-inline {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
    padding-top: 0.25rem;
  }

  .btn {
    padding: 0.375rem 0.75rem;
    border-radius: 0.375rem;
    font-size: 0.8rem;
    font-weight: 500;
    cursor: pointer;
    border: 1px solid transparent;
    transition: all 0.15s;
  }

  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-sm {
    padding: 0.25rem 0.5rem;
    font-size: 0.75rem;
  }

  .btn-primary {
    background: var(--primary-color, #3b82f6);
    color: white;
  }

  .btn-primary:hover:not(:disabled) {
    filter: brightness(1.1);
  }

  .btn-secondary {
    background: transparent;
    color: var(--text-secondary);
    border-color: var(--border-color, #d1d5db);
  }

  .btn-secondary:hover:not(:disabled) {
    background: var(--hover-color);
  }

  .btn-ghost {
    background: transparent;
    color: var(--text-secondary);
    border: none;
  }

  .btn-ghost:hover:not(:disabled) {
    background: var(--hover-color);
    color: var(--text-color);
  }

  .btn-danger-text {
    color: #dc2626;
  }

  .btn-danger-text:hover:not(:disabled) {
    background: rgba(239, 68, 68, 0.1);
    color: #dc2626;
  }

  .btn-danger {
    background: #dc2626;
    color: white;
  }

  .btn-add {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.375rem;
    width: 100%;
    padding: 0.5rem;
    border: 2px dashed var(--border-color, #d1d5db);
    border-radius: 0.5rem;
    background: transparent;
    color: var(--text-secondary, #6b7280);
    font-size: 0.8rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
  }

  .btn-add:hover {
    border-color: var(--primary-color, #3b82f6);
    color: var(--primary-color, #3b82f6);
    background: rgba(59, 130, 246, 0.05);
  }

  .section-hint {
    font-size: 0.7rem;
    color: var(--text-secondary, #6b7280);
    margin: 0.25rem 0 0;
    line-height: 1.4;
  }
</style>
