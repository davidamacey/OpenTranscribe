<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { SpeakerInboxItem as InboxItemType } from '$lib/types/speakerCluster';
  import AudioClipPlayer from './AudioClipPlayer.svelte';
  import { getAudioClipUrl } from '$lib/api/speakerClusters';

  export let item: InboxItemType;

  const dispatch = createEventDispatcher();

  function confidenceColor(confidence: number | null): string {
    if (confidence === null) return 'var(--color-text-tertiary, #9ca3af)';
    if (confidence >= 0.75) return '#10b981';
    if (confidence >= 0.5) return '#f59e0b';
    return '#ef4444';
  }
</script>

<div class="inbox-item">
  <div class="item-left">
    {#if item.audio_clip_uuid}
      <AudioClipPlayer clipUrl={getAudioClipUrl(item.speaker_uuid)} small />
    {:else}
      <div class="no-clip-placeholder" title="No audio clip available">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" opacity="0.3">
          <path d="M8 1a3 3 0 0 0-3 3v4a3 3 0 1 0 6 0V4a3 3 0 0 0-3-3z" />
          <path d="M3 7a1 1 0 0 0-2 0 7 7 0 0 0 6 6.93V15H5a1 1 0 1 0 0 2h6a1 1 0 1 0 0-2H9v-1.07A7 7 0 0 0 15 7a1 1 0 1 0-2 0 5 5 0 0 1-10 0z" />
        </svg>
      </div>
    {/if}
    <div class="item-info">
      <div class="speaker-name">{item.speaker_name}</div>
      {#if item.suggested_name}
        <div class="suggestion">
          <span class="suggestion-label">Suggestion:</span>
          <span class="suggestion-name">{item.suggested_name}</span>
          {#if item.confidence !== null}
            <span class="confidence" style="color: {confidenceColor(item.confidence)}">
              {(item.confidence * 100).toFixed(0)}%
            </span>
          {/if}
          {#if item.suggestion_source}
            <span class="source-badge">{item.suggestion_source}</span>
          {/if}
        </div>
      {/if}
      <div class="meta">
        {#if item.media_file_title}
          <span class="file-title">{item.media_file_title}</span>
        {/if}
        {#if item.predicted_gender}
          <span class="attribute">{item.predicted_gender}</span>
        {/if}
        {#if item.cluster_label}
          <span class="cluster-tag">Cluster: {item.cluster_label}</span>
        {:else if item.cluster_member_count > 1}
          <span class="cluster-tag">{item.cluster_member_count} similar</span>
        {/if}
      </div>
    </div>
  </div>
  <div class="item-actions">
    {#if item.suggested_name}
      <button
        class="action-btn accept"
        on:click={() => dispatch('action', { type: 'accept', speaker_uuid: item.speaker_uuid })}
        title="Accept suggestion (A)"
      >
        Accept
      </button>
    {/if}
    <button
      class="action-btn skip"
      on:click={() => dispatch('action', { type: 'skip', speaker_uuid: item.speaker_uuid })}
      title="Skip (S)"
    >
      Skip
    </button>
  </div>
</div>

<style>
  .inbox-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 16px;
    border-bottom: 1px solid var(--color-border, #e5e7eb);
    transition: background 0.1s ease;
  }

  .inbox-item:hover {
    background: var(--color-bg-hover, #f9fafb);
  }

  .item-left {
    display: flex;
    align-items: center;
    gap: 12px;
    flex: 1;
    min-width: 0;
  }

  .no-clip-placeholder {
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .item-info {
    flex: 1;
    min-width: 0;
  }

  .speaker-name {
    font-weight: 500;
    color: var(--color-text-primary, #111827);
    font-size: 14px;
  }

  .suggestion {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-top: 2px;
    font-size: 13px;
  }

  .suggestion-label {
    color: var(--color-text-tertiary, #9ca3af);
  }

  .suggestion-name {
    color: var(--color-primary, #3b82f6);
    font-weight: 500;
  }

  .confidence {
    font-weight: 600;
    font-size: 12px;
  }

  .source-badge {
    font-size: 11px;
    padding: 1px 6px;
    border-radius: 8px;
    background: var(--color-bg-tertiary, #f3f4f6);
    color: var(--color-text-tertiary, #9ca3af);
  }

  .meta {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 3px;
    font-size: 12px;
    color: var(--color-text-tertiary, #9ca3af);
  }

  .file-title {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 200px;
  }

  .attribute {
    text-transform: capitalize;
  }

  .cluster-tag {
    padding: 1px 6px;
    border-radius: 8px;
    background: var(--color-bg-tertiary, #f3f4f6);
  }

  .item-actions {
    display: flex;
    gap: 6px;
    flex-shrink: 0;
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

  .action-btn.accept {
    background: #10b981;
    color: white;
    border-color: #10b981;
  }

  .action-btn.accept:hover {
    background: #059669;
  }
</style>
