<script lang="ts">
  import { onMount } from 'svelte';
  import type { Group, GroupDetail } from '$lib/types/groups';
  import { GroupsApi } from '$lib/api/groups';
  import { groupsStore, myGroups, memberGroups } from '$stores/groups';
  import { toastStore } from '$stores/toast';
  import { t } from '$stores/locale';
  import GroupRoleBadge from './GroupRoleBadge.svelte';
  import GroupDetailPanel from './GroupDetailPanel.svelte';
  import GroupCreateModal from './GroupCreateModal.svelte';

  let selectedGroup: GroupDetail | null = null;
  let showCreateModal = false;
  let loadingDetail = false;

  onMount(async () => {
    await loadGroups();
  });

  async function loadGroups() {
    groupsStore.setLoading(true);
    try {
      const groups = await GroupsApi.fetchGroups();
      groupsStore.setGroups(groups);
    } catch (err: any) {
      const message = err?.response?.data?.detail || $t('groups.toast.loadGroupsFailed');
      groupsStore.setError(message);
      toastStore.error(message);
    }
  }

  async function openGroupDetail(group: Group) {
    loadingDetail = true;
    try {
      selectedGroup = await GroupsApi.fetchGroupDetail(group.uuid);
      groupsStore.setSelectedGroup(selectedGroup);
    } catch (err: any) {
      const message = err?.response?.data?.detail || $t('groups.toast.loadGroupFailed');
      toastStore.error(message);
    } finally {
      loadingDetail = false;
    }
  }

  function handleBack() {
    selectedGroup = null;
    groupsStore.setSelectedGroup(null);
    // Refresh list in case of changes
    loadGroups();
  }

  function handleGroupCreated(event: CustomEvent<Group>) {
    groupsStore.addGroup(event.detail);
    showCreateModal = false;
  }

  function handleGroupDeleted(event: CustomEvent<{ uuid: string }>) {
    groupsStore.removeGroup(event.detail.uuid);
    selectedGroup = null;
    groupsStore.setSelectedGroup(null);
  }

  function handleGroupUpdated() {
    // Refresh group list to reflect name/description changes
    loadGroups();
  }

  function handleLeft() {
    selectedGroup = null;
    groupsStore.setSelectedGroup(null);
    loadGroups();
  }

  function formatDate(dateStr: string): string {
    try {
      return new Date(dateStr).toLocaleDateString();
    } catch {
      return dateStr;
    }
  }
</script>

{#if selectedGroup}
  <GroupDetailPanel
    group={selectedGroup}
    on:back={handleBack}
    on:deleted={handleGroupDeleted}
    on:updated={handleGroupUpdated}
    on:left={handleLeft}
  />
{:else}
  <div class="groups-overview">
    <!-- Header with Create button -->
    <div class="overview-header">
      <button class="btn-create" on:click={() => (showCreateModal = true)}>
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="12" y1="5" x2="12" y2="19"></line>
          <line x1="5" y1="12" x2="19" y2="12"></line>
        </svg>
        {$t('groups.createGroup')}
      </button>
    </div>

    {#if $groupsStore.loading}
      <div class="loading-state">
        <div class="spinner"></div>
        <p>{$t('groups.loading')}</p>
      </div>
    {:else if $groupsStore.error}
      <div class="error-state">
        <p>{$groupsStore.error}</p>
        <button class="btn-retry" on:click={loadGroups}>{$t('groups.retry')}</button>
      </div>
    {:else if $groupsStore.groups.length === 0}
      <div class="empty-state">
        <svg class="empty-icon" xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
          <circle cx="9" cy="7" r="4"></circle>
          <path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
          <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
        </svg>
        <p class="empty-title">{$t('groups.emptyTitle')}</p>
        <p class="empty-description">{$t('groups.emptyDescription')}</p>
      </div>
    {:else}
      <!-- My Groups (Owned) -->
      {#if $myGroups.length > 0}
        <div class="groups-section">
          <h4 class="groups-section-title">{$t('groups.myGroups')}</h4>
          <div class="groups-grid">
            {#each $myGroups as group (group.uuid)}
              <button class="group-card" on:click={() => openGroupDetail(group)} disabled={loadingDetail}>
                <div class="card-header">
                  <span class="card-name">{group.name}</span>
                  <GroupRoleBadge role={group.my_role} />
                </div>
                {#if group.description}
                  <p class="card-description">{group.description}</p>
                {/if}
                <div class="card-meta">
                  <span class="card-members">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                      <circle cx="9" cy="7" r="4"></circle>
                    </svg>
                    {group.member_count}
                  </span>
                  <span class="card-date">{formatDate(group.created_at)}</span>
                </div>
              </button>
            {/each}
          </div>
        </div>
      {/if}

      <!-- Groups I'm a Member Of -->
      {#if $memberGroups.length > 0}
        <div class="groups-section">
          <h4 class="groups-section-title">{$t('groups.memberOf')}</h4>
          <div class="groups-grid">
            {#each $memberGroups as group (group.uuid)}
              <button class="group-card" on:click={() => openGroupDetail(group)} disabled={loadingDetail}>
                <div class="card-header">
                  <span class="card-name">{group.name}</span>
                  <GroupRoleBadge role={group.my_role} />
                </div>
                {#if group.description}
                  <p class="card-description">{group.description}</p>
                {/if}
                <div class="card-meta">
                  <span class="card-members">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                      <circle cx="9" cy="7" r="4"></circle>
                    </svg>
                    {group.member_count}
                  </span>
                  <span class="card-date">{$t('groups.owner')}: {group.owner.full_name || group.owner.email}</span>
                </div>
              </button>
            {/each}
          </div>
        </div>
      {/if}
    {/if}
  </div>

  <GroupCreateModal bind:isOpen={showCreateModal} on:created={handleGroupCreated} />
{/if}

<style>
  .groups-overview {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
  }

  .overview-header {
    display: flex;
    justify-content: flex-end;
  }

  .btn-create {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.5rem 1rem;
    background: var(--primary-color);
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 0.8125rem;
    font-weight: 500;
    cursor: pointer;
    transition: background-color 0.15s;
  }

  .btn-create:hover {
    background: var(--primary-hover);
  }

  .loading-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.75rem;
    padding: 2rem 0;
    color: var(--text-secondary);
    font-size: 0.8125rem;
  }

  .loading-state p {
    margin: 0;
  }

  .spinner {
    width: 24px;
    height: 24px;
    border: 2px solid var(--border-color);
    border-top-color: var(--primary-color);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .error-state {
    text-align: center;
    padding: 1.5rem 0;
    color: var(--danger-color, #dc2626);
    font-size: 0.8125rem;
  }

  .error-state p {
    margin: 0 0 0.75rem;
  }

  .btn-retry {
    padding: 0.375rem 0.75rem;
    background: transparent;
    color: var(--primary-color);
    border: 1px solid var(--primary-color);
    border-radius: 6px;
    font-size: 0.75rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
  }

  .btn-retry:hover {
    background: var(--primary-color);
    color: white;
  }

  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.5rem;
    padding: 2.5rem 1rem;
    text-align: center;
  }

  .empty-icon {
    color: var(--text-secondary);
    opacity: 0.4;
    margin-bottom: 0.5rem;
  }

  .empty-title {
    margin: 0;
    font-size: 0.9375rem;
    font-weight: 600;
    color: var(--text-color);
  }

  .empty-description {
    margin: 0;
    font-size: 0.8125rem;
    color: var(--text-secondary);
    max-width: 320px;
    line-height: 1.5;
  }

  .groups-section {
    display: flex;
    flex-direction: column;
    gap: 0.625rem;
  }

  .groups-section-title {
    margin: 0;
    font-size: 0.8125rem;
    font-weight: 600;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }

  .groups-grid {
    display: flex;
    flex-direction: column;
    gap: 0.375rem;
  }

  .group-card {
    display: flex;
    flex-direction: column;
    gap: 0.375rem;
    padding: 0.75rem 1rem;
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.15s;
    text-align: left;
    width: 100%;
  }

  .group-card:hover:not(:disabled) {
    border-color: var(--primary-color);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
  }

  .group-card:disabled {
    opacity: 0.7;
    cursor: wait;
  }

  .card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
  }

  .card-name {
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--text-color);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .card-description {
    margin: 0;
    font-size: 0.75rem;
    color: var(--text-secondary);
    line-height: 1.4;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .card-meta {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
  }

  .card-members {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    font-size: 0.75rem;
    color: var(--text-secondary);
  }

  .card-date {
    font-size: 0.6875rem;
    color: var(--text-secondary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
</style>
