<script lang="ts">
  import type { SummaryData } from '$lib/types/summary';
  import TopicsList from './TopicsList.svelte';

  export let summary: SummaryData;
  export let searchQuery: string = '';
  export let currentMatchIndex: number = 0;

  // Detect if this is a standard BLUF format or custom format
  $: isStandardBLUF = !!(summary.bluf && summary.brief_summary);

  // Create a function that generates all matches with proper indexing
  function highlightWithGlobalIndex(text: string, globalMatchIndex: { count: number }): string {
    if (!searchQuery || !text) return text;

    const escapedQuery = searchQuery.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const regex = new RegExp(`(${escapedQuery})`, 'gi');

    return text.replace(regex, (match) => {
      const isCurrentMatch = globalMatchIndex.count === currentMatchIndex;
      const thisMatchIndex = globalMatchIndex.count;
      globalMatchIndex.count++;

      if (isCurrentMatch) {
        return `<mark class="current-match" data-match-index="${thisMatchIndex}">${match}</mark>`;
      } else {
        return `<mark class="search-match" data-match-index="${thisMatchIndex}">${match}</mark>`;
      }
    });
  }

  // Highlighted rendering for custom formats with search
  function renderObjectWithHighlighting(obj: any, depth: number = 0): string {
    if (!searchQuery) {
      return renderObject(obj, depth);
    }

    const globalIndex = { count: 0 };
    return renderObjectWithIndex(obj, depth, globalIndex);
  }

  function renderObjectWithIndex(obj: any, depth: number, globalIndex: { count: number }): string {
    if (!obj || typeof obj !== 'object') return '';

    const entries = Object.entries(obj).filter(([key]) => key !== 'metadata');

    if (entries.length === 0) return '';

    return entries.map(([key, value]) => `
      <div class="field-group depth-${depth}">
        <div class="field-title">${formatFieldName(key)}</div>
        <div class="field-content">${renderValueWithIndex(value, depth + 1, globalIndex)}</div>
      </div>
    `).join('');
  }

  function renderValueWithIndex(value: any, depth: number, globalIndex: { count: number }): string {
    if (value === null || value === undefined) return '';

    if (Array.isArray(value)) {
      if (value.length === 0) return '<em class="empty-list">No items</em>';

      const isObjectArray = value.some(item => typeof item === 'object' && item !== null);

      if (isObjectArray) {
        return value.map(item => renderObjectWithIndex(item, depth + 1, globalIndex)).join('');
      } else {
        // Simple list - highlight strings
        return '<ul class="simple-list">' +
          value.map(item => {
            const text = escapeHtml(String(item));
            return `<li>${highlightText(text, globalIndex)}</li>`;
          }).join('') +
          '</ul>';
      }
    }

    if (typeof value === 'object') {
      return renderObjectWithIndex(value, depth, globalIndex);
    }

    if (typeof value === 'boolean') {
      return value ? '<span class="bool-value">Yes</span>' : '<span class="bool-value">No</span>';
    }

    if (typeof value === 'number') {
      return `<span class="number-value">${value}</span>`;
    }

    // String value - highlight and preserve line breaks
    const escapedText = escapeHtml(String(value));
    const highlightedText = highlightText(escapedText, globalIndex);
    return highlightedText.replace(/\n/g, '<br>');
  }

  function highlightText(text: string, globalIndex: { count: number }): string {
    if (!searchQuery || !text) return text;

    const escapedQuery = searchQuery.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const regex = new RegExp(`(${escapedQuery})`, 'gi');

    return text.replace(regex, (match) => {
      const isCurrentMatch = globalIndex.count === currentMatchIndex;
      const thisMatchIndex = globalIndex.count;
      globalIndex.count++;

      if (isCurrentMatch) {
        return `<mark class="current-match" data-match-index="${thisMatchIndex}">${match}</mark>`;
      } else {
        return `<mark class="search-match" data-match-index="${thisMatchIndex}">${match}</mark>`;
      }
    });
  }

  // Recursive rendering for flexible structures
  function formatFieldName(key: string): string {
    // Convert snake_case or camelCase to Title Case
    return key
      .replace(/_/g, ' ')
      .replace(/([A-Z])/g, ' $1')
      .split(' ')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  }

  function renderValue(value: any, depth: number = 0): string {
    if (value === null || value === undefined) return '';

    if (Array.isArray(value)) {
      if (value.length === 0) return '<em class="empty-list">No items</em>';

      // Check if array contains objects or primitives
      const isObjectArray = value.some(item => typeof item === 'object' && item !== null);

      if (isObjectArray) {
        return value.map(item => renderObject(item, depth + 1)).join('');
      } else {
        // Simple list of strings/numbers
        return '<ul class="simple-list">' +
          value.map(item => `<li>${escapeHtml(String(item))}</li>`).join('') +
          '</ul>';
      }
    }

    if (typeof value === 'object') {
      return renderObject(value, depth);
    }

    if (typeof value === 'boolean') {
      return value ? '<span class="bool-value">Yes</span>' : '<span class="bool-value">No</span>';
    }

    if (typeof value === 'number') {
      return `<span class="number-value">${value}</span>`;
    }

    // String value - preserve line breaks
    return escapeHtml(String(value)).replace(/\n/g, '<br>');
  }

  function renderObject(obj: any, depth: number = 0): string {
    if (!obj || typeof obj !== 'object') return '';

    const entries = Object.entries(obj).filter(([key]) => key !== 'metadata');

    if (entries.length === 0) return '';

    return entries.map(([key, value]) => `
      <div class="field-group depth-${depth}">
        <div class="field-title">${formatFieldName(key)}</div>
        <div class="field-content">${renderValue(value, depth + 1)}</div>
      </div>
    `).join('');
  }

  function escapeHtml(text: string): string {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  // Extract text from value (handles both strings and objects)
  function extractText(value: any): string {
    if (typeof value === 'string') {
      return value;
    }
    if (typeof value === 'object' && value !== null) {
      // Try common field names for text content
      return value.decision || value.text || value.item || value.description || JSON.stringify(value);
    }
    return String(value);
  }

  // Reactive function to generate highlighted content (for BLUF format)
  function getHighlightedContent() {
    if (!searchQuery || !summary) return null;

    const globalIndex = { count: 0 };

    return {
      bluf: summary.bluf ? highlightWithGlobalIndex(summary.bluf, globalIndex) : null,
      briefSummary: summary.brief_summary ? highlightWithGlobalIndex(summary.brief_summary, globalIndex) : null,
      keyDecisions: (summary.key_decisions || []).map(decision =>
        highlightWithGlobalIndex(extractText(decision), globalIndex)
      ),
      followUpItems: (summary.follow_up_items || []).map(item =>
        highlightWithGlobalIndex(extractText(item), globalIndex)
      ),
      majorTopics: (summary.major_topics || []).map(topic => ({
        ...topic,
        topic: highlightWithGlobalIndex(topic.topic || '', globalIndex),
        key_points: (topic.key_points || []).map(point => highlightWithGlobalIndex(point || '', globalIndex)),
        participants: (topic.participants || []).map(p => highlightWithGlobalIndex(p || '', globalIndex))
      }))
    };
  }

  let highlightedContent: any = null;
  let customHighlightedContent: string = '';

  // Reactive statement that triggers when searchQuery OR currentMatchIndex changes
  $: {
    // Reference these variables to track changes (Svelte reactivity)
    void searchQuery;
    void currentMatchIndex;
    void summary;

    if (summary) {
      if (searchQuery) {
        highlightedContent = getHighlightedContent();
        customHighlightedContent = renderObjectWithHighlighting(summary, 0);
      } else {
        highlightedContent = null;
        customHighlightedContent = renderObject(summary, 0);
      }
    }
  }
</script>

<div class="summary-content">
  {#if isStandardBLUF}
    <!-- Standard BLUF Format Display -->
    <section class="bluf-section">
      <h3 class="section-title">Executive Summary (BLUF)</h3>
      <div class="bluf-content">
        {@html highlightedContent?.bluf || summary.bluf}
      </div>
    </section>

    <section class="brief-summary-section">
      <h3 class="section-title">Brief Summary</h3>
      <div class="brief-summary-content">
        {@html highlightedContent?.briefSummary || summary.brief_summary}
      </div>
    </section>

    {#if summary.major_topics && summary.major_topics.length > 0}
      <TopicsList
        topics={highlightedContent?.majorTopics || summary.major_topics}
      />
    {/if}

    {#if summary.key_decisions && summary.key_decisions.length > 0}
      <section class="key-decisions-section">
        <h3 class="section-title">Key Decisions</h3>
        <div class="key-decisions-list">
          {#each (highlightedContent?.keyDecisions || summary.key_decisions) as decision}
            <div class="key-decision-item">
              <div class="decision-bullet">✓</div>
              <div class="decision-text">{@html extractText(decision)}</div>
            </div>
          {/each}
        </div>
      </section>
    {/if}

    {#if summary.follow_up_items && summary.follow_up_items.length > 0}
      <section class="follow-up-section">
        <h3 class="section-title">Follow-up Items</h3>
        <div class="follow-up-list">
          {#each (highlightedContent?.followUpItems || summary.follow_up_items) as item}
            <div class="follow-up-item">
              <div class="follow-up-bullet">→</div>
              <div class="follow-up-text">{@html extractText(item)}</div>
            </div>
          {/each}
        </div>
      </section>
    {/if}
  {:else}
    <!-- Flexible Custom Format Display -->
    <div class="custom-summary">
      {@html customHighlightedContent}
    </div>
  {/if}

  <!-- AI Disclaimer -->
  <section class="ai-disclaimer-section">
    <div class="ai-disclaimer">
      <p class="disclaimer-text">
        AI-generated summary - please verify important details.
        {#if summary.metadata}
          Generated by {summary.metadata.provider} ({summary.metadata.model}).
        {/if}
      </p>
    </div>
  </section>
</div>

<style>
  .summary-content {
    padding: 1.5rem;
    max-height: calc(100vh - 200px);
    overflow-y: auto;
  }

  .section-title {
    font-size: 1.25rem;
    font-weight: 600;
    margin-bottom: 0.75rem;
    color: var(--text-primary);
    border-bottom: 2px solid var(--border-color);
    padding-bottom: 0.5rem;
  }

  .bluf-section, .brief-summary-section {
    margin-bottom: 2rem;
  }

  /* Add consistent spacing between all sections */
  section {
    margin-bottom: 2rem;
  }

  section:last-child {
    margin-bottom: 1rem;
  }

  .bluf-content, .brief-summary-content {
    line-height: 1.6;
    color: var(--text-secondary);
  }


  .key-decisions-list, .follow-up-list {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .key-decision-item, .follow-up-item {
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
  }

  .decision-bullet, .follow-up-bullet {
    color: var(--success-color);
    font-weight: 600;
    margin-top: 0.1rem;
  }

  .decision-text, .follow-up-text {
    flex: 1;
    line-height: 1.5;
  }

  .ai-disclaimer-section {
    margin-top: 2rem;
    padding-top: 1rem;
    border-top: 1px solid var(--border-color);
  }

  .ai-disclaimer {
    text-align: center;
  }

  .disclaimer-text {
    font-size: 0.8rem;
    color: var(--text-muted);
    font-style: italic;
    margin: 0;
    line-height: 1.4;
  }

  /* Custom Summary Styles */
  .custom-summary {
    padding: 0.5rem 0;
  }

  :global(.field-group) {
    margin-bottom: 1.5rem;
    padding-left: 1rem;
  }

  :global(.field-group.depth-0) {
    border-left: 3px solid var(--primary-color);
    padding-left: 1rem;
    margin-bottom: 2rem;
  }

  :global(.field-group.depth-1) {
    border-left: 2px solid var(--border-color);
    padding-left: 0.75rem;
  }

  :global(.field-group.depth-2) {
    border-left: 1px solid var(--border-color);
    padding-left: 0.5rem;
  }

  :global(.field-title) {
    font-size: 1.1rem;
    font-weight: 600;
    margin-bottom: 0.5rem;
    color: var(--text-primary);
  }

  :global(.field-content) {
    color: var(--text-secondary);
    line-height: 1.6;
  }

  :global(.simple-list) {
    margin: 0.5rem 0;
    padding-left: 1.5rem;
  }

  :global(.simple-list li) {
    margin-bottom: 0.25rem;
    line-height: 1.5;
  }

  :global(.empty-list) {
    color: var(--text-tertiary, #999);
    font-style: italic;
  }

  :global(.bool-value) {
    font-weight: 500;
    color: var(--success-color);
  }

  :global(.number-value) {
    font-weight: 500;
    color: var(--primary-color);
  }

  /* Search highlighting styles */
  :global(.search-match) {
    background-color: #ffeb3b;
    color: #000;
    padding: 0.1rem 0.2rem;
    border-radius: 3px;
    font-weight: 500;
  }

  :global(.current-match) {
    background-color: #ff9800;
    color: #000;
    padding: 0.1rem 0.2rem;
    border-radius: 3px;
    font-weight: 600;
    box-shadow: 0 0 0 2px rgba(255, 152, 0, 0.3);
  }
</style>
