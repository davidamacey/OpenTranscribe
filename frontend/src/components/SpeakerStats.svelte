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

<div class="speaker-stats">
  <h2>Speaker Analytics</h2>
  
  {#if normalizedAnalytics.talk_time.total > 0}
    <div class="talk-time-container">
      <h3>Talk Time Distribution</h3>
      
      <!-- Single horizontal bar showing all speakers -->
      <div class="talk-time-combined-bar">
        {#each getObjectEntries(normalizedAnalytics.talk_time.by_speaker) as [speakerName, time]}
          <div 
            class="speaker-segment"
            style="
              width: {safeCalculatePercentage(time, normalizedAnalytics.talk_time.total)}%;
              background-color: {getSpeakerBgColor(speakerName)};
              border-right: 1px solid {getSpeakerColor(getSpeakerNameForColor(speakerName)).border};
            "
            title="{speakerName}: {formatTime(time)} ({safeCalculatePercentage(time, normalizedAnalytics.talk_time.total).toFixed(1)}%)"
          ></div>
        {/each}
      </div>
      
      <!-- Legend below the bar -->
      <div class="talk-time-legend">
        {#each getObjectEntries(normalizedAnalytics.talk_time.by_speaker) as [speakerName, time]}
          <div class="legend-item">
            <div 
              class="legend-color-indicator" 
              style="background-color: {getSpeakerBgColor(speakerName)}; border: 1px solid {getSpeakerColor(getSpeakerNameForColor(speakerName)).border};"
            ></div>
            <span class="legend-speaker-name">{speakerName}</span>
            <span class="legend-time">{formatTime(time)}</span>
            <span class="legend-percentage">({safeCalculatePercentage(time, normalizedAnalytics.talk_time.total).toFixed(1)}%)</span>
          </div>
        {/each}
      </div>
      
      <div class="total-time">
        <span>Total: {formatTime(normalizedAnalytics.talk_time.total)}</span>
      </div>
    </div>
  
    {#if normalizedAnalytics.interruptions.total > 0}
    <div class="interruptions-container">
      <h3>Interruptions</h3>
      
      <div class="interruptions-list">
        {#each getObjectEntries(normalizedAnalytics.interruptions.by_speaker) as [speakerName, count]}
          <div class="interruption-item">
            <div class="speaker-name-container">
              <div 
                class="speaker-color-indicator" 
                style="background-color: {getSpeakerBgColor(speakerName)}; border: 1px solid {getSpeakerColor(getSpeakerNameForColor(speakerName)).border};"
              ></div>
              <span class="speaker-name">{speakerName}</span>
            </div>
            
            <div class="interruption-count">
              {count} {count === 1 ? 'interruption' : 'interruptions'}
            </div>
          </div>
        {/each}
      </div>
      
      <div class="total-interruptions">
        <span>Total: {normalizedAnalytics.interruptions.total} {normalizedAnalytics.interruptions.total === 1 ? 'interruption' : 'interruptions'}</span>
      </div>
    </div>
  {/if}
  
  {#if normalizedAnalytics.turn_taking.total_turns > 0}
    <div class="turn-taking-container">
      <h3>Turn Taking</h3>
      
      <div class="turns-count">
        <span>Total turns: {normalizedAnalytics.turn_taking.total_turns}</span>
      </div>
      
      <div class="turn-distribution">
        <div class="turn-bars">
          {#each getObjectEntries(normalizedAnalytics.turn_taking.by_speaker) as [speakerName, turns]}
            <div class="speaker-bar">
              <div class="speaker-name-container">
                <div 
                  class="speaker-color-indicator" 
                  style="background-color: {getSpeakerBgColor(speakerName)}; border: 1px solid {getSpeakerColor(getSpeakerNameForColor(speakerName)).border};"
                ></div>
                <span class="speaker-name">{speakerName}</span>
              </div>
              
              <div class="bar-container">
                <div 
                  class="bar-fill" 
                  style="
                    width: {safeCalculatePercentage(turns, normalizedAnalytics.turn_taking.total_turns)}%; 
                    background-color: {getSpeakerBgColor(speakerName)};
                    border: 1px solid {getSpeakerColor(getSpeakerNameForColor(speakerName)).border};
                  "
                ></div>
                <span class="turn-label">{turns} {turns === 1 ? 'turn' : 'turns'}</span>
              </div>
            </div>
          {/each}
        </div>
      </div>
    </div>
  {/if}
  
  {#if normalizedAnalytics.questions.total > 0}
    <div class="questions-container">
      <h3>Questions</h3>
      
      <div class="questions-list">
        {#each getObjectEntries(normalizedAnalytics.questions.by_speaker) as [speakerName, count]}
          <div class="question-item">
            <div class="speaker-name-container">
              <div 
                class="speaker-color-indicator" 
                style="background-color: {getSpeakerBgColor(speakerName)}; border: 1px solid {getSpeakerColor(getSpeakerNameForColor(speakerName)).border};"
              ></div>
              <span class="speaker-name">{speakerName}</span>
            </div>
            
            <div class="question-count">
              {count} {count === 1 ? 'question' : 'questions'}
            </div>
          </div>
        {/each}
      </div>
      
      <div class="total-questions">
        <span>Total: {normalizedAnalytics.questions.total} {normalizedAnalytics.questions.total === 1 ? 'question' : 'questions'}</span>
      </div>
    </div>
  {/if}
  {:else}
    <div class="empty-state">
      <p>No speaker analytics available for this file.</p>
    </div>
  {/if}
</div>

<style>
  .speaker-stats {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
    background-color: var(--surface-color);
    border-radius: 8px;
    padding: 1.5rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  }
  
  .speaker-stats h2 {
    font-size: 1.2rem;
    margin: 0 0 0.5rem;
  }
  
  .speaker-stats h3 {
    font-size: 1rem;
    font-weight: 500;
    color: var(--text-color);
    margin: 0 0 1rem;
  }
  
  .talk-time-container, .interruptions-container, .turn-taking-container, .questions-container {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  
  .talk-time-combined-bar {
    display: flex;
    width: 100%;
    height: 24px;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    margin-bottom: 1rem;
  }
  
  .speaker-segment {
    height: 100%;
    transition: opacity 0.2s ease;
  }
  
  .speaker-segment:hover {
    opacity: 0.8;
  }
  
  .talk-time-legend {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
  }
  
  .legend-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.85rem;
  }
  
  .legend-color-indicator {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  
  .legend-speaker-name {
    font-weight: 500;
    color: var(--text-color);
    min-width: 80px;
  }
  
  .legend-time {
    color: var(--text-color);
    min-width: 50px;
  }
  
  .legend-percentage {
    color: var(--text-light);
    font-size: 0.8rem;
  }
  
  .turn-bars {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  
  .speaker-bar {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  
  .speaker-name-container {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  
  .speaker-color-indicator {
    width: 12px;
    height: 12px;
    border-radius: 50%;
  }
  
  .speaker-name {
    font-size: 0.9rem;
    color: var(--text-color);
  }
  
  .bar-container {
    height: 10px;
    background-color: var(--background-color);
    border-radius: 5px;
    overflow: hidden;
    position: relative;
    margin-bottom: 1.25rem;
  }
  
  .bar-fill {
    height: 100%;
    border-radius: 5px;
  }
  
  .turn-label {
    position: absolute;
    right: 0;
    bottom: -20px;
    font-size: 0.8rem;
    color: var(--text-light);
  }
  
  .total-time, .total-interruptions, .turns-count, .total-questions {
    font-size: 0.9rem;
    color: var(--text-light);
    margin-top: 0.5rem;
    text-align: right;
  }
  
  .interruptions-list, .questions-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  
  .interruption-item, .question-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.9rem;
  }
  
  .interruption-count, .question-count {
    color: var(--text-light);
  }
  
  .empty-state {
    text-align: center;
    color: var(--text-light);
    padding: 1rem;
  }
  
  @media (max-width: 768px) {
    .speaker-stats {
      padding: 1rem;
    }
  }
</style>
