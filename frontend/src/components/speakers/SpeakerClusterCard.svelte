<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { SpeakerCluster } from '$lib/types/speakerCluster';
  import AudioClipPlayer from './AudioClipPlayer.svelte';
  import { getAudioClipUrl } from '$lib/api/speakerClusters';

  export let cluster: SpeakerCluster;
  export let expanded = false;

  const dispatch = createEventDispatcher();

  let editingLabel = false;
  let labelInput = cluster.label || '';

  function toggleExpand() {
    expanded = !expanded;
    if (expanded) {
      dispatch('expand', { uuid: cluster.uuid });
    }
  }

  function startEdit() {
    labelInput = cluster.label || '';
    editingLabel = true;
  }

  function saveLabel() {
    editingLabel = false;
    if (labelInput !== cluster.label) {
      dispatch('update', { uuid: cluster.uuid, label: labelInput });
    }
  }

  function cancelEdit() {
    editingLabel = false;
    labelInput = cluster.label || '';
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') saveLabel();
    if (e.key === 'Escape') cancelEdit();
  }

  function qualityColor(score: number | null): string {
    if (score === null) return 'var(--color-text-tertiary, #9ca3af)';
    if (score >= 0.8) return '#10b981';
    if (score >= 0.6) return '#f59e0b';
    return '#ef4444';
  }
</script>

<div class="cluster-card" class:expanded>
  <div class="card-header" on:click={toggleExpand} on:keydown={toggleExpand} role="button" tabindex="0">
    <div class="header-left">
      <span class="expand-icon">{expanded ? '▾' : '▸'}</span>
      {#if editingLabel}
        <!-- svelte-ignore a11y-autofocus -->
        <input
          class="label-input"
          bind:value={labelInput}
          on:blur={saveLabel}
          on:keydown={handleKeydown}
          on:click|stopPropagation
          autofocus
          placeholder="Enter label..."
        />
      {:else}
        <!-- svelte-ignore a11y-no-static-element-interactions -->
        <span class="cluster-label" on:dblclick|stopPropagation={startEdit}>
          {cluster.label || 'Unlabeled Cluster'}
        </span>
      {/if}
    </div>
    <div class="header-right">
      {#if cluster.quality_score !== null}
        <span class="quality-badge" style="color: {qualityColor(cluster.quality_score)}">
          Q: {(cluster.quality_score * 100).toFixed(0)}%
        </span>
      {/if}
      <span class="member-count">{cluster.member_count} speakers</span>
      {#if cluster.promoted_to_profile_name}
        <span class="promoted-badge">Profile: {cluster.promoted_to_profile_name}</span>
      {/if}
    </div>
  </div>

  {#if expanded}
    <div class="card-body">
      <slot name="members" />
      <div class="card-actions">
        {#if !cluster.promoted_to_profile_id}
          <button class="action-btn promote" on:click={() => dispatch('promote', { uuid: cluster.uuid })}>
            Promote to Profile
          </button>
        {/if}
        <button class="action-btn merge" on:click={() => dispatch('merge', { uuid: cluster.uuid })}>
          Merge
        </button>
        {#if cluster.member_count > 1}
          <button class="action-btn split" on:click={() => dispatch('split', { uuid: cluster.uuid })}>
            Split
          </button>
        {/if}
        <button class="action-btn delete" on:click={() => dispatch('delete', { uuid: cluster.uuid })}>
          Delete
        </button>
      </div>
    </div>
  {/if}
</div>

<style>
  .cluster-card {
    border: 1px solid var(--color-border, #e5e7eb);
    border-radius: 8px;
    background: var(--color-bg-primary, #ffffff);
    overflow: hidden;
    transition: box-shadow 0.15s ease;
  }

  .cluster-card:hover {
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  }

  .card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    cursor: pointer;
    user-select: none;
  }

  .card-header:hover {
    background: var(--color-bg-hover, #f9fafb);
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
    min-width: 0;
  }

  .expand-icon {
    color: var(--color-text-tertiary, #9ca3af);
    font-size: 12px;
    width: 16px;
  }

  .cluster-label {
    font-weight: 500;
    color: var(--color-text-primary, #111827);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .label-input {
    font-weight: 500;
    border: 1px solid var(--color-primary, #3b82f6);
    border-radius: 4px;
    padding: 2px 6px;
    font-size: inherit;
    background: var(--color-bg-primary, #ffffff);
    color: var(--color-text-primary, #111827);
    outline: none;
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-shrink: 0;
  }

  .quality-badge {
    font-size: 12px;
    font-weight: 500;
  }

  .member-count {
    font-size: 13px;
    color: var(--color-text-secondary, #6b7280);
    white-space: nowrap;
  }

  .promoted-badge {
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 10px;
    background: var(--color-success-bg, #d1fae5);
    color: var(--color-success, #059669);
    white-space: nowrap;
  }

  .card-body {
    border-top: 1px solid var(--color-border, #e5e7eb);
    padding: 12px 16px;
  }

  .card-actions {
    display: flex;
    gap: 8px;
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid var(--color-border, #e5e7eb);
  }

  .action-btn {
    padding: 4px 12px;
    border-radius: 6px;
    border: 1px solid var(--color-border, #d1d5db);
    background: var(--color-bg-secondary, #f9fafb);
    color: var(--color-text-primary, #374151);
    font-size: 13px;
    cursor: pointer;
    transition: all 0.15s ease;
  }

  .action-btn:hover {
    background: var(--color-bg-hover, #f3f4f6);
  }

  .action-btn.promote {
    background: var(--color-primary, #3b82f6);
    color: white;
    border-color: var(--color-primary, #3b82f6);
  }

  .action-btn.promote:hover {
    opacity: 0.9;
  }

  .action-btn.delete {
    color: var(--color-danger, #ef4444);
    border-color: var(--color-danger, #ef4444);
  }

  .action-btn.delete:hover {
    background: var(--color-danger, #ef4444);
    color: white;
  }
</style>
