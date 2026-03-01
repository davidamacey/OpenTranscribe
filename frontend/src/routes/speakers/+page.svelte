<script lang="ts">
  import { onMount } from 'svelte';
  import { t } from '$stores/locale';
  import SpeakerClusterCard from '$components/speakers/SpeakerClusterCard.svelte';
  import SpeakerInboxItem from '$components/speakers/SpeakerInboxItem.svelte';
  import {
    listClusters,
    getClusterDetail,
    updateCluster,
    deleteCluster,
    promoteCluster,
    triggerRecluster,
    getUnverifiedSpeakers,
    batchVerifySpeakers
  } from '$lib/api/speakerClusters';
  import type {
    SpeakerCluster,
    SpeakerClusterDetail,
    SpeakerClusterMember,
    SpeakerInboxItem as InboxItem,
    PaginatedResponse
  } from '$lib/types/speakerCluster';
  import axiosInstance from '$lib/axios';

  type Tab = 'clusters' | 'profiles' | 'inbox';
  let activeTab: Tab = 'clusters';

  // Clusters state
  let clusters: SpeakerCluster[] = [];
  let clusterTotal = 0;
  let clusterPage = 1;
  let clusterPages = 0;
  let clusterSearch = '';
  let expandedCluster: string | null = null;
  let clusterMembers: Record<string, SpeakerClusterMember[]> = {};
  let loadingClusters = false;
  let reclustering = false;

  // Profiles state
  let profiles: Record<string, unknown>[] = [];
  let loadingProfiles = false;

  // Inbox state
  let inboxItems: InboxItem[] = [];
  let inboxTotal = 0;
  let inboxPage = 1;
  let inboxPages = 0;
  let loadingInbox = false;

  let error = '';

  onMount(() => {
    loadClusters();
  });

  function switchTab(tab: Tab) {
    activeTab = tab;
    error = '';
    if (tab === 'clusters' && clusters.length === 0) loadClusters();
    if (tab === 'profiles' && profiles.length === 0) loadProfiles();
    if (tab === 'inbox' && inboxItems.length === 0) loadInbox();
  }

  async function loadClusters() {
    loadingClusters = true;
    error = '';
    try {
      const res = await listClusters(clusterPage, 20, clusterSearch || undefined);
      clusters = res.items;
      clusterTotal = res.total;
      clusterPages = res.pages;
    } catch (e) {
      error = 'Failed to load clusters';
    } finally {
      loadingClusters = false;
    }
  }

  async function loadProfiles() {
    loadingProfiles = true;
    try {
      const res = await axiosInstance.get('/speaker-profiles/profiles');
      profiles = res.data;
    } catch (e) {
      error = 'Failed to load profiles';
    } finally {
      loadingProfiles = false;
    }
  }

  async function loadInbox() {
    loadingInbox = true;
    try {
      const res = await getUnverifiedSpeakers(inboxPage, 20);
      inboxItems = res.items;
      inboxTotal = res.total;
      inboxPages = res.pages;
    } catch (e) {
      error = 'Failed to load inbox';
    } finally {
      loadingInbox = false;
    }
  }

  async function handleClusterExpand(e: CustomEvent<{ uuid: string }>) {
    const uuid = e.detail.uuid;
    expandedCluster = uuid;
    if (!clusterMembers[uuid]) {
      try {
        const detail = await getClusterDetail(uuid);
        clusterMembers[uuid] = detail.members;
        clusterMembers = clusterMembers;
      } catch {
        // silently fail
      }
    }
  }

  async function handleClusterUpdate(e: CustomEvent<{ uuid: string; label: string }>) {
    try {
      await updateCluster(e.detail.uuid, { label: e.detail.label });
      await loadClusters();
    } catch {
      error = 'Failed to update cluster';
    }
  }

  async function handleClusterPromote(e: CustomEvent<{ uuid: string }>) {
    const name = prompt('Enter profile name:');
    if (!name) return;
    try {
      await promoteCluster(e.detail.uuid, name);
      await loadClusters();
    } catch {
      error = 'Failed to promote cluster';
    }
  }

  async function handleClusterDelete(e: CustomEvent<{ uuid: string }>) {
    if (!confirm('Delete this cluster?')) return;
    try {
      await deleteCluster(e.detail.uuid);
      await loadClusters();
    } catch {
      error = 'Failed to delete cluster';
    }
  }

  async function handleRecluster() {
    reclustering = true;
    try {
      await triggerRecluster();
      setTimeout(loadClusters, 3000);
    } catch {
      error = 'Failed to start re-clustering';
    } finally {
      reclustering = false;
    }
  }

  async function handleInboxAction(e: CustomEvent<{ type: string; speaker_uuid: string }>) {
    const { type, speaker_uuid } = e.detail;
    if (type === 'accept') {
      try {
        await batchVerifySpeakers([speaker_uuid], 'accept');
        inboxItems = inboxItems.filter((i) => i.speaker_uuid !== speaker_uuid);
        inboxTotal--;
      } catch {
        error = 'Failed to accept speaker';
      }
    } else if (type === 'skip') {
      inboxItems = inboxItems.filter((i) => i.speaker_uuid !== speaker_uuid);
    }
  }

  function handleKeydown(e: KeyboardEvent) {
    if (activeTab !== 'inbox' || !inboxItems.length) return;
    if (e.key === 'a' || e.key === 'A') {
      const first = inboxItems[0];
      if (first?.suggested_name) {
        handleInboxAction(
          new CustomEvent('action', { detail: { type: 'accept', speaker_uuid: first.speaker_uuid } })
        );
      }
    }
    if (e.key === 's' || e.key === 'S') {
      const first = inboxItems[0];
      if (first) {
        handleInboxAction(
          new CustomEvent('action', { detail: { type: 'skip', speaker_uuid: first.speaker_uuid } })
        );
      }
    }
  }

  function handleClusterSearch() {
    clusterPage = 1;
    loadClusters();
  }
</script>

<svelte:window on:keydown={handleKeydown} />

<div class="speakers-page">
  <div class="page-header">
    <h1>{$t('speakers.title')}</h1>
  </div>

  <div class="tabs">
    <button class="tab" class:active={activeTab === 'clusters'} on:click={() => switchTab('clusters')}>
      {$t('speakers.tabs.clusters')}
      {#if clusterTotal > 0}
        <span class="badge">{clusterTotal}</span>
      {/if}
    </button>
    <button class="tab" class:active={activeTab === 'profiles'} on:click={() => switchTab('profiles')}>
      {$t('speakers.tabs.profiles')}
      {#if profiles.length > 0}
        <span class="badge">{profiles.length}</span>
      {/if}
    </button>
    <button class="tab" class:active={activeTab === 'inbox'} on:click={() => switchTab('inbox')}>
      {$t('speakers.tabs.inbox')}
      {#if inboxTotal > 0}
        <span class="badge alert">{inboxTotal}</span>
      {/if}
    </button>
  </div>

  {#if error}
    <div class="error-bar">{error}</div>
  {/if}

  <!-- Clusters Tab -->
  {#if activeTab === 'clusters'}
    <div class="tab-content">
      <div class="toolbar">
        <input
          type="text"
          class="search-input"
          placeholder="Search clusters..."
          bind:value={clusterSearch}
          on:input={handleClusterSearch}
        />
        <button class="btn-recluster" on:click={handleRecluster} disabled={reclustering}>
          {reclustering ? $t('speakers.clusters.reclustering') : $t('speakers.clusters.recluster')}
        </button>
      </div>

      {#if loadingClusters}
        <div class="loading">Loading clusters...</div>
      {:else if clusters.length === 0}
        <div class="empty-state">
          <p>{$t('speakers.clusters.empty')}</p>
        </div>
      {:else}
        <div class="cluster-list">
          {#each clusters as cluster (cluster.uuid)}
            <SpeakerClusterCard
              {cluster}
              expanded={expandedCluster === cluster.uuid}
              on:expand={handleClusterExpand}
              on:update={handleClusterUpdate}
              on:promote={handleClusterPromote}
              on:delete={handleClusterDelete}
            >
              <div slot="members">
                {#if clusterMembers[cluster.uuid]}
                  <div class="member-list">
                    {#each clusterMembers[cluster.uuid] as member}
                      <div class="member-row">
                        <span class="member-name">{member.display_name || member.speaker_name}</span>
                        <span class="member-file">{member.media_file_title || ''}</span>
                        <span class="member-confidence">{(member.confidence * 100).toFixed(0)}%</span>
                        {#if member.verified}
                          <span class="verified-badge">Verified</span>
                        {/if}
                      </div>
                    {/each}
                  </div>
                {:else}
                  <div class="loading-members">Loading members...</div>
                {/if}
              </div>
            </SpeakerClusterCard>
          {/each}
        </div>

        {#if clusterPages > 1}
          <div class="pagination">
            <button disabled={clusterPage <= 1} on:click={() => { clusterPage--; loadClusters(); }}>Prev</button>
            <span>Page {clusterPage} of {clusterPages}</span>
            <button disabled={clusterPage >= clusterPages} on:click={() => { clusterPage++; loadClusters(); }}>Next</button>
          </div>
        {/if}
      {/if}
    </div>
  {/if}

  <!-- Profiles Tab -->
  {#if activeTab === 'profiles'}
    <div class="tab-content">
      {#if loadingProfiles}
        <div class="loading">Loading profiles...</div>
      {:else if profiles.length === 0}
        <div class="empty-state">
          <p>{$t('speakers.profiles.empty')}</p>
        </div>
      {:else}
        <div class="profile-list">
          {#each profiles as profile}
            <div class="profile-card">
              <div class="profile-name">{profile.name || 'Unnamed'}</div>
              {#if profile.description}
                <div class="profile-desc">{profile.description}</div>
              {/if}
              <div class="profile-meta">
                {#if profile.embedding_count}
                  <span>{profile.embedding_count} embeddings</span>
                {/if}
                {#if profile.predicted_gender}
                  <span class="attribute">{profile.predicted_gender}</span>
                {/if}
              </div>
            </div>
          {/each}
        </div>
      {/if}
    </div>
  {/if}

  <!-- Inbox Tab -->
  {#if activeTab === 'inbox'}
    <div class="tab-content">
      {#if activeTab === 'inbox'}
        <div class="inbox-hint">
          Keyboard shortcuts: <kbd>A</kbd> Accept &middot; <kbd>S</kbd> Skip
        </div>
      {/if}
      {#if loadingInbox}
        <div class="loading">Loading inbox...</div>
      {:else if inboxItems.length === 0}
        <div class="empty-state">
          <p>{$t('speakers.inbox.empty')}</p>
        </div>
      {:else}
        <div class="inbox-list">
          {#each inboxItems as item (item.speaker_uuid)}
            <SpeakerInboxItem {item} on:action={handleInboxAction} />
          {/each}
        </div>

        {#if inboxPages > 1}
          <div class="pagination">
            <button disabled={inboxPage <= 1} on:click={() => { inboxPage--; loadInbox(); }}>Prev</button>
            <span>Page {inboxPage} of {inboxPages}</span>
            <button disabled={inboxPage >= inboxPages} on:click={() => { inboxPage++; loadInbox(); }}>Next</button>
          </div>
        {/if}
      {/if}
    </div>
  {/if}
</div>

<style>
  .speakers-page {
    max-width: 1000px;
    margin: 0 auto;
    padding: 24px 16px;
  }

  .page-header h1 {
    font-size: 24px;
    font-weight: 600;
    color: var(--color-text-primary, #111827);
    margin: 0 0 16px 0;
  }

  .tabs {
    display: flex;
    border-bottom: 2px solid var(--color-border, #e5e7eb);
    margin-bottom: 20px;
  }

  .tab {
    padding: 10px 20px;
    border: none;
    background: none;
    color: var(--color-text-secondary, #6b7280);
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    border-bottom: 2px solid transparent;
    margin-bottom: -2px;
    transition: all 0.15s ease;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .tab:hover {
    color: var(--color-text-primary, #111827);
  }

  .tab.active {
    color: var(--color-primary, #3b82f6);
    border-bottom-color: var(--color-primary, #3b82f6);
  }

  .badge {
    font-size: 11px;
    padding: 1px 7px;
    border-radius: 10px;
    background: var(--color-bg-tertiary, #e5e7eb);
    color: var(--color-text-secondary, #6b7280);
  }

  .badge.alert {
    background: var(--color-danger, #ef4444);
    color: white;
  }

  .error-bar {
    padding: 8px 16px;
    background: #fef2f2;
    color: #dc2626;
    border-radius: 6px;
    margin-bottom: 16px;
    font-size: 14px;
  }

  .toolbar {
    display: flex;
    gap: 12px;
    margin-bottom: 16px;
  }

  .search-input {
    flex: 1;
    padding: 8px 12px;
    border: 1px solid var(--color-border, #d1d5db);
    border-radius: 6px;
    background: var(--color-bg-primary, #ffffff);
    color: var(--color-text-primary, #111827);
    font-size: 14px;
  }

  .search-input::placeholder {
    color: var(--color-text-tertiary, #9ca3af);
  }

  .btn-recluster {
    padding: 8px 16px;
    border-radius: 6px;
    border: 1px solid var(--color-primary, #3b82f6);
    background: var(--color-primary, #3b82f6);
    color: white;
    font-size: 14px;
    cursor: pointer;
    white-space: nowrap;
  }

  .btn-recluster:hover:not(:disabled) {
    opacity: 0.9;
  }

  .btn-recluster:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .loading {
    text-align: center;
    padding: 40px;
    color: var(--color-text-tertiary, #9ca3af);
  }

  .empty-state {
    text-align: center;
    padding: 60px 20px;
    color: var(--color-text-tertiary, #9ca3af);
  }

  .cluster-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .member-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .member-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 6px 8px;
    border-radius: 4px;
    font-size: 13px;
  }

  .member-row:hover {
    background: var(--color-bg-hover, #f9fafb);
  }

  .member-name {
    font-weight: 500;
    color: var(--color-text-primary, #111827);
    min-width: 120px;
  }

  .member-file {
    color: var(--color-text-tertiary, #9ca3af);
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .member-confidence {
    color: var(--color-text-secondary, #6b7280);
    font-size: 12px;
  }

  .verified-badge {
    font-size: 11px;
    padding: 1px 6px;
    border-radius: 8px;
    background: #d1fae5;
    color: #059669;
  }

  .loading-members {
    padding: 12px;
    color: var(--color-text-tertiary, #9ca3af);
    font-size: 13px;
  }

  .profile-list {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 12px;
  }

  .profile-card {
    padding: 16px;
    border: 1px solid var(--color-border, #e5e7eb);
    border-radius: 8px;
    background: var(--color-bg-primary, #ffffff);
  }

  .profile-name {
    font-weight: 600;
    font-size: 15px;
    color: var(--color-text-primary, #111827);
  }

  .profile-desc {
    margin-top: 4px;
    font-size: 13px;
    color: var(--color-text-secondary, #6b7280);
  }

  .profile-meta {
    margin-top: 8px;
    display: flex;
    gap: 8px;
    font-size: 12px;
    color: var(--color-text-tertiary, #9ca3af);
  }

  .attribute {
    text-transform: capitalize;
  }

  .inbox-hint {
    padding: 8px 16px;
    background: var(--color-bg-tertiary, #f3f4f6);
    border-radius: 6px;
    font-size: 13px;
    color: var(--color-text-secondary, #6b7280);
    margin-bottom: 12px;
  }

  .inbox-hint kbd {
    padding: 1px 6px;
    background: var(--color-bg-primary, #ffffff);
    border: 1px solid var(--color-border, #d1d5db);
    border-radius: 3px;
    font-family: monospace;
    font-size: 12px;
  }

  .inbox-list {
    border: 1px solid var(--color-border, #e5e7eb);
    border-radius: 8px;
    overflow: hidden;
  }

  .pagination {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 16px;
    margin-top: 16px;
    font-size: 14px;
    color: var(--color-text-secondary, #6b7280);
  }

  .pagination button {
    padding: 6px 14px;
    border: 1px solid var(--color-border, #d1d5db);
    border-radius: 6px;
    background: var(--color-bg-primary, #ffffff);
    color: var(--color-text-primary, #374151);
    cursor: pointer;
  }

  .pagination button:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
</style>
