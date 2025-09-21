<script lang="ts">
  import type { SummaryData } from '$lib/types/summary';
  
  export let speakers: SummaryData['speakers'];
  
  let expanded = false;
  
  function formatTime(seconds: number): string {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
  }
  
  function getBarWidth(percentage: number): string {
    return `${Math.max(percentage, 2)}%`;
  }
</script>

<section class="speaker-analysis-section">
  <div class="section-header">
    <h3 class="section-title">Speaker Analysis</h3>
    <button 
      class="expand-toggle"
      class:expanded
      on:click={() => expanded = !expanded}
      aria-label={expanded ? 'Collapse speaker analysis' : 'Expand speaker analysis'}
    >
      <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
        <path d="M8 12a.5.5 0 0 0 .5-.5V5.707l2.146 2.147a.5.5 0 0 0 .708-.708l-3-3a.5.5 0 0 0-.708 0l-3 3a.5.5 0 1 0 .708.708L7.5 5.707V11.5a.5.5 0 0 0 .5.5z"/>
      </svg>
    </button>
  </div>
  
  {#if expanded}
    <div class="speakers-grid" transition:slide>
      {#each speakers as speaker}
        <div class="speaker-card">
          <div class="speaker-header">
            <div class="speaker-name">{speaker.name}</div>
            <div class="speaker-stats">
              <span class="talk-time">{formatTime(speaker.talk_time_seconds)}</span>
              <span class="percentage">({speaker.percentage.toFixed(1)}%)</span>
            </div>
          </div>
          
          <div class="talk-time-bar">
            <div 
              class="talk-time-fill"
              style="width: {getBarWidth(speaker.percentage)}"
            ></div>
          </div>
          
          {#if speaker.key_points && speaker.key_points.length > 0}
            <div class="key-points">
              <h4 class="key-points-title">Key Contributions:</h4>
              <ul class="key-points-list">
                {#each speaker.key_points as point}
                  <li class="key-point">{point}</li>
                {/each}
              </ul>
            </div>
          {/if}
        </div>
      {/each}
    </div>
  {:else}
    <div class="speakers-summary">
      <div class="speakers-overview">
        {#each speakers as speaker}
          <div class="speaker-chip">
            <span class="speaker-chip-name">{speaker.name}</span>
            <span class="speaker-chip-percentage">{speaker.percentage.toFixed(1)}%</span>
          </div>
        {/each}
      </div>
    </div>
  {/if}
</section>

<style>
  .speaker-analysis-section {
    margin-bottom: 2rem;
  }

  .section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.75rem;
  }

  .section-title {
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--text-primary);
    border-bottom: 2px solid var(--border-color);
    padding-bottom: 0.5rem;
    flex: 1;
  }

  .expand-toggle {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--text-secondary);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0.5rem;
    border-radius: 4px;
    transition: all 0.2s ease;
  }

  .expand-toggle:hover {
    background-color: var(--hover-bg);
    color: var(--text-primary);
  }

  .expand-toggle.expanded {
    transform: rotate(180deg);
  }

  .speakers-overview {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .speaker-chip {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.75rem;
    background-color: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 20px;
    font-size: 0.9rem;
  }

  .speaker-chip-name {
    font-weight: 500;
  }

  .speaker-chip-percentage {
    color: var(--primary-color);
    font-weight: 600;
  }

  .speakers-grid {
    display: grid;
    gap: 1.5rem;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  }

  .speaker-card {
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 1.25rem;
    background-color: var(--bg-secondary);
  }

  .speaker-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.75rem;
  }

  .speaker-name {
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--text-primary);
  }

  .speaker-stats {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.9rem;
  }

  .talk-time {
    font-family: 'Courier New', monospace;
    font-weight: 600;
    color: var(--primary-color);
  }

  .percentage {
    color: var(--text-secondary);
  }

  .talk-time-bar {
    height: 6px;
    background-color: var(--border-color);
    border-radius: 3px;
    overflow: hidden;
    margin-bottom: 1rem;
  }

  .talk-time-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--primary-color), var(--primary-light));
    border-radius: 3px;
    transition: width 0.3s ease;
  }

  .key-points-title {
    font-size: 0.95rem;
    font-weight: 600;
    margin-bottom: 0.5rem;
    color: var(--text-primary);
  }

  .key-points-list {
    list-style: none;
    padding: 0;
    margin: 0;
  }

  .key-point {
    padding: 0.25rem 0;
    padding-left: 1rem;
    position: relative;
    line-height: 1.4;
    color: var(--text-secondary);
  }

  .key-point::before {
    content: "•";
    color: var(--primary-color);
    position: absolute;
    left: 0;
    font-weight: bold;
  }
</style>

<script context="module">
  import { slide } from 'svelte/transition';
</script>