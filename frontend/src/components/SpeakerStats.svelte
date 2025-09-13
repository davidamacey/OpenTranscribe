<script>
  import { getSpeakerColor } from '$lib/utils/speakerColors';
  
  // Type definitions matching FileDetail.svelte
  /**
   * @typedef {Object} SpeakerTime
   * @property {Record<string, number>} [by_speaker] - Speaker time mapped by speaker name
   * @property {number} [total] - Total talk time in seconds
   */

  /**
   * @typedef {Object} Interruptions
   * @property {Record<string, number>} [by_speaker] - Interruptions count by speaker name
   * @property {number} [total] - Total interruptions
   */

  /**
   * @typedef {Object} TurnTaking
   * @property {Record<string, number>} [by_speaker] - Turn count by speaker name
   * @property {number} [total_turns] - Total turns
   */

  /**
   * @typedef {Object} Questions
   * @property {Record<string, number>} [by_speaker] - Questions count by speaker name
   * @property {number} [total] - Total questions
   */

  /**
   * @typedef {Object} OverallFileMetrics
   * @property {number} [word_count] - Total words in the transcript
   * @property {number} [duration_seconds] - Duration of the audio/video file in seconds
   * @property {string} [clarity_score] - Clarity score (e.g., "Good", "Fair", "Poor")
   * @property {number} [sentiment_score] - Sentiment score from -1 (negative) to 1 (positive)
   * @property {number} [sentiment_magnitude] - Strength of sentiment
   * @property {number} [silence_ratio] - Ratio of silence in the audio
   * @property {number} [speaking_pace] - Average words per minute
   * @property {string} [language] - Detected language
   * @property {SpeakerTime} [talk_time] - Talk time statistics
   * @property {Interruptions} [interruptions] - Interruptions statistics
   * @property {TurnTaking} [turn_taking] - Turn taking statistics
   * @property {Questions} [questions] - Questions statistics
   */
  
  // Default values for all metrics
  const DEFAULT_METRICS = {
    word_count: 0,
    duration_seconds: 0,
    clarity_score: 'N/A',
    sentiment_score: 0,
    sentiment_magnitude: 0,
    silence_ratio: 0,
    speaking_pace: 0,
    language: 'en',
    talk_time: { by_speaker: {}, total: 0 },
    interruptions: { by_speaker: {}, total: 0 },
    turn_taking: { by_speaker: {}, total_turns: 0 },
    questions: { by_speaker: {}, total: 0 }
  };
  
  // Component props - accept partial metrics with all properties optional
  /** @type {OverallFileMetrics} */
  export let analytics = {};
  /** @type {Array<{name: string, display_name: string}>} */
  export let speakerList = [];
  
  // Merge provided analytics with defaults
  const safeAnalytics = {
    ...DEFAULT_METRICS,
    ...analytics,
    talk_time: {
      by_speaker: {},
      total: 0,
      ...(analytics.talk_time || {})
    },
    interruptions: {
      by_speaker: {},
      total: 0,
      ...(analytics.interruptions || {})
    },
    turn_taking: {
      by_speaker: {},
      total_turns: 0,
      ...(analytics.turn_taking || {})
    },
    questions: {
      by_speaker: {},
      total: 0,
      ...(analytics.questions || {})
    }
  };
  
  // Create a normalized analytics object with default values
  $: normalizedAnalytics = {
    ...safeAnalytics,
    talk_time: {
      by_speaker: safeAnalytics.talk_time?.by_speaker || {},
      total: safeAnalytics.talk_time?.total || 0
    },
    interruptions: {
      by_speaker: safeAnalytics.interruptions?.by_speaker || {},
      total: safeAnalytics.interruptions?.total || 0
    },
    turn_taking: {
      by_speaker: safeAnalytics.turn_taking?.by_speaker || {},
      total_turns: safeAnalytics.turn_taking?.total_turns || 0
    },
    questions: {
      by_speaker: safeAnalytics.questions?.by_speaker || {},
      total: safeAnalytics.questions?.total || 0
    }
  };
  
  /**
   * Safely get entries from an object with type safety
   * @template T
   * @param {Record<string, T> | null | undefined} obj - The object to get entries from
   * @returns {[string, T][]} Array of [key, value] pairs
   */
  function getObjectEntries(obj) {
    return Object.entries(obj || {});
  }
  
  /**
   * Safely calculate percentage, handling division by zero
   * @param {number} [part=0] - The part of the total
   * @param {number} [total=0] - The total value
   * @returns {number} The calculated percentage or 0 if total is 0
   */
  function safeCalculatePercentage(part = 0, total = 0) {
    return total > 0 ? calculatePercentage(part, total) : 0;
  }
  
  /**
   * Calculate percentage for talk time
   * @param {number} speakerTime - The time a speaker has talked
   * @param {number} totalTime - The total time of the recording
   * @returns {number} - The percentage of time the speaker talked
   */
  function calculatePercentage(speakerTime, totalTime) {
    if (!totalTime) return 0;
    return (speakerTime / totalTime) * 100;
  }
  
  /**
   * Get the speaker name to use for color mapping (original name, not display name)
   * This ensures consistent colors even when display names change
   * @param {string} displayName - The display name shown in analytics
   * @returns {string} - The original speaker name for color mapping
   */
  function getSpeakerNameForColor(displayName) {
    // If this looks like an original speaker label (SPEAKER_XX), use it directly
    if (displayName.match(/^SPEAKER_\d+$/)) {
      return displayName;
    }
    
    // Find the original speaker name by looking up the display name in speakerList
    const speaker = speakerList.find(s => s.display_name === displayName);
    if (speaker) {
      return speaker.name; // Use original name for color consistency
    }
    
    // Fall back to display name if no mapping found
    return displayName;
  }

  /**
   * Get speaker color using the shared color system (matching transcript style)
   * @param {string} name - The name of the speaker
   * @returns {string} - A CSS color value
   */
  function getSpeakerBgColor(name) {
    return getSpeakerColor(getSpeakerNameForColor(name)).bg;
  }
  
  /**
   * Format time in minutes and seconds
   * @param {number} seconds - The time in seconds
   * @returns {string} - Formatted time string in MM:SS format
   */
  function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  }
</script>

<div class="speaker-stats compact-layout">
  <!-- Analytics Overview Cards -->
  <div class="analytics-overview">
    <div class="overview-card">
      <div class="card-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
        </svg>
      </div>
      <div class="card-content">
        <div class="card-value">{normalizedAnalytics.word_count || 0}</div>
        <div class="card-label">Words</div>
      </div>
    </div>
    
    <div class="overview-card">
      <div class="card-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"/>
          <polyline points="12,6 12,12 16,14"/>
        </svg>
      </div>
      <div class="card-content">
        <div class="card-value">{formatTime(normalizedAnalytics.duration_seconds || 0)}</div>
        <div class="card-label">Duration</div>
      </div>
    </div>
    
    <div class="overview-card">
      <div class="card-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M8 7a4 4 0 1 0 8 0 4 4 0 0 0-8 0z"/>
          <path d="M6 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2"/>
        </svg>
      </div>
      <div class="card-content">
        <div class="card-value">{Object.keys(normalizedAnalytics.talk_time?.by_speaker || {}).length}</div>
        <div class="card-label">Speakers</div>
      </div>
    </div>
    
    {#if normalizedAnalytics.interruptions?.total > 0}
    <div class="overview-card">
      <div class="card-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
        </svg>
      </div>
      <div class="card-content">
        <div class="card-value">{normalizedAnalytics.interruptions.total}</div>
        <div class="card-label">Interruptions</div>
      </div>
    </div>
    {/if}
  </div>
  
  {#if normalizedAnalytics.talk_time.total > 0}
    <!-- Compact Talk Time Section -->
    <div class="section-compact">
      <h3 class="section-title">
        <span class="section-icon">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 3v18h18"/>
            <path d="M18.7 8l-5.1 5.2-2.8-2.7L7 14.3"/>
          </svg>
        </span>
        Talk Time Distribution
      </h3>
      
      <!-- Large Horizontal Bar Chart -->
      <div class="talk-time-bar-large">
        {#each getObjectEntries(normalizedAnalytics.talk_time.by_speaker) as [speakerName, time]}
          <div 
            class="speaker-segment-large"
            style="
              width: {safeCalculatePercentage(time, normalizedAnalytics.talk_time.total)}%;
              background-color: {getSpeakerBgColor(speakerName)};
            "
            title="{speakerName}: {formatTime(time)} ({safeCalculatePercentage(time, normalizedAnalytics.talk_time.total).toFixed(1)}%)"
          ></div>
        {/each}
      </div>
      
      <!-- Combined Speaker Data Chips -->
      <div class="speaker-chips-grid">
        {#each getObjectEntries(normalizedAnalytics.talk_time.by_speaker).sort(([,a], [,b]) => b - a) as [speakerName, time]}
          {@const speakerTurns = normalizedAnalytics.turn_taking?.by_speaker?.[speakerName] || 0}
          <div class="speaker-chip">
            <div class="chip-header">
              <div class="speaker-dot-large" style="background-color: {getSpeakerBgColor(speakerName)};"></div>
              <span class="speaker-name-chip">{speakerName}</span>
            </div>
            <div class="chip-stats">
              <div class="stat-item">
                <span class="stat-value">{formatTime(time)}</span>
                <span class="stat-label">time</span>
              </div>
              <div class="stat-item">
                <span class="stat-value">{safeCalculatePercentage(time, normalizedAnalytics.talk_time.total).toFixed(1)}%</span>
                <span class="stat-label">share</span>
              </div>
              {#if normalizedAnalytics.turn_taking?.total_turns > 0}
              <div class="stat-item">
                <span class="stat-value">{speakerTurns}</span>
                <span class="stat-label">{speakerTurns === 1 ? 'turn' : 'turns'}</span>
              </div>
              {/if}
            </div>
          </div>
        {/each}
      </div>
    </div>
    
      <!-- Additional Metrics Row -->
      {#if (normalizedAnalytics.interruptions?.total > 0) || (normalizedAnalytics.questions?.total > 0)}
      <div class="additional-metrics-row">
        {#if normalizedAnalytics.interruptions?.total > 0}
        <div class="metric-section">
          <h4 class="metric-title">
            <span class="metric-icon">
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
              </svg>
            </span>
            Interruptions
          </h4>
          <div class="metric-list">
            {#each getObjectEntries(normalizedAnalytics.interruptions.by_speaker) as [speakerName, count]}
              <div class="metric-item">
                <div class="metric-speaker">
                  <div class="speaker-dot" style="background-color: {getSpeakerBgColor(speakerName)};"></div>
                  <span class="speaker-name-small">{speakerName}</span>
                </div>
                <span class="metric-value">{count}</span>
              </div>
            {/each}
          </div>
        </div>
        {/if}
        
        {#if normalizedAnalytics.questions?.total > 0}
        <div class="metric-section">
          <h4 class="metric-title">
            <span class="metric-icon">
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="10"/>
                <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/>
                <point cx="12" cy="17"/>
              </svg>
            </span>
            Questions
          </h4>
          <div class="metric-list">
            {#each getObjectEntries(normalizedAnalytics.questions.by_speaker) as [speakerName, count]}
              <div class="metric-item">
                <div class="metric-speaker">
                  <div class="speaker-dot" style="background-color: {getSpeakerBgColor(speakerName)};"></div>
                  <span class="speaker-name-small">{speakerName}</span>
                </div>
                <span class="metric-value">{count}</span>
              </div>
            {/each}
          </div>
        </div>
        {/if}
      </div>
      {/if}
  {:else}
    <div class="empty-state">
      <p>No speaker analytics available for this file.</p>
    </div>
  {/if}
</div>

<style>
  .speaker-stats.compact-layout {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    background-color: var(--surface-color);
    border-radius: 8px;
    padding: 1rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  }
  
  /* Analytics Overview Cards */
  .analytics-overview {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 0.75rem;
    margin-bottom: 0.5rem;
  }
  
  .overview-card {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: var(--background-color);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    padding: 0.75rem;
    transition: all 0.2s ease;
  }
  
  .overview-card:hover {
    border-color: var(--primary-color);
    transform: translateY(-1px);
  }
  
  .card-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--primary-color);
    flex-shrink: 0;
  }
  
  .card-icon svg {
    width: 16px;
    height: 16px;
  }
  
  .card-content {
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
    min-width: 0;
  }
  
  .card-value {
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--text-primary);
    line-height: 1.2;
  }
  
  .card-label {
    font-size: 0.75rem;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    line-height: 1;
  }
  
  /* Compact Sections */
  .section-compact {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  
  .section-title {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.9rem;
    font-weight: 600;
    color: var(--text-primary);
    margin: 0;
  }
  
  .section-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--primary-color);
  }
  
  .section-icon svg {
    width: 14px;
    height: 14px;
  }
  
  /* Large Talk Time Bar */
  .talk-time-bar-large {
    display: flex;
    width: 100%;
    height: 24px;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
    margin: 0.75rem 0 1rem 0;
    border: 1px solid var(--border-color);
  }
  
  .speaker-segment-large {
    height: 100%;
    transition: all 0.2s ease;
    cursor: pointer;
  }
  
  .speaker-segment-large:hover {
    opacity: 0.85;
    transform: scaleY(1.1);
  }
  
  /* Speaker Data Chips Grid */
  .speaker-chips-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 0.75rem;
  }
  
  .speaker-chip {
    background: var(--background-color);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 0.75rem;
    transition: all 0.2s ease;
  }
  
  .speaker-chip:hover {
    border-color: var(--primary-color);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    transform: translateY(-1px);
  }
  
  .chip-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
  }
  
  .speaker-dot-large {
    width: 16px;
    height: 16px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  
  .speaker-name-chip {
    font-weight: 500;
    color: var(--text-primary);
    font-size: 0.9rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1;
    min-width: 0;
  }
  
  .chip-stats {
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
  }
  
  .stat-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    flex: 1;
  }
  
  .stat-value {
    font-weight: 600;
    color: var(--text-primary);
    font-size: 0.9rem;
    line-height: 1.2;
  }
  
  .stat-label {
    font-size: 0.7rem;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-top: 0.1rem;
  }
  
  /* Additional Metrics Row */
  .additional-metrics-row {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 0.75rem;
    margin-top: 0.75rem;
  }
  
  .metric-section {
    background: var(--background-color);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    padding: 0.75rem;
  }
  
  .metric-title {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--text-primary);
    margin: 0 0 0.5rem 0;
  }
  
  .metric-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-secondary);
  }
  
  .metric-icon svg {
    width: 12px;
    height: 12px;
  }
  
  .metric-list {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
  }
  
  .metric-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.8rem;
    padding: 0.2rem 0;
  }
  
  .metric-speaker {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    flex: 1;
    min-width: 0;
  }
  
  .speaker-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  
  .speaker-name-small {
    color: var(--text-primary);
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  
  .metric-value {
    color: var(--text-secondary);
    font-weight: 500;
    flex-shrink: 0;
  }
  
  .empty-state {
    text-align: center;
    color: var(--text-light);
    padding: 1rem;
  }
  
  @media (max-width: 768px) {
    .speaker-stats.compact-layout {
      padding: 0.75rem;
    }
    
    .analytics-overview {
      grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
      gap: 0.5rem;
    }
    
    .overview-card {
      padding: 0.5rem;
    }
    
    .card-value {
      font-size: 1rem;
    }
    
    .card-label {
      font-size: 0.7rem;
    }
    
    .speaker-chips-grid {
      grid-template-columns: 1fr;
    }
    
    .chip-stats {
      gap: 0.5rem;
    }
    
    .additional-metrics-row {
      grid-template-columns: 1fr;
    }
  }
  
  @media (max-width: 480px) {
    .analytics-overview {
      grid-template-columns: repeat(2, 1fr);
    }
    
    .card-icon svg {
      width: 14px;
      height: 14px;
    }
    
    .section-title {
      font-size: 0.85rem;
    }
    
    .talk-time-bar-large {
      height: 20px;
      border-radius: 10px;
    }
    
    .speaker-chip {
      padding: 0.5rem;
    }
    
    .chip-stats {
      flex-direction: column;
      gap: 0.4rem;
    }
    
    .stat-item {
      flex-direction: row;
      justify-content: space-between;
    }
  }
</style>
