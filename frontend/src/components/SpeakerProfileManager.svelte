<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { fade } from 'svelte/transition';
  import axiosInstance from '$lib/axios';
  import SpeakerVerification from './SpeakerVerification.svelte';
  import { toastStore } from '$stores/toast';
  import { t } from '$stores/locale';
  import { translateSpeakerLabel } from '$lib/i18n';

  export let fileId: string;  // UUID
  export let isVisible = false;

  const dispatch = createEventDispatcher();

  interface Speaker {
    uuid: string;  // UUID (public identifier)
    name: string;
    display_name?: string;
    verified: boolean;
    confidence?: number;
    profile?: {
      uuid: string;  // UUID (public identifier)
      name: string;
      description?: string;
    };
    // Backend computed fields
    computed_status?: string;
    status_text?: string;
    status_color?: string;
    resolved_display_name?: string;
  }

  interface SpeakerProfile {
    uuid: string;  // UUID (public identifier)
    name: string;
    description?: string;
    instance_count: number;
    media_count: number;
    media_files: any[];
  }

  let speakers: Speaker[] = [];
  let speakerProfiles: SpeakerProfile[] = [];
  let selectedSpeaker: Speaker | null = null;
  let showVerification = false;
  let suggestions: any[] = [];
  let crossMediaOccurrences: any[] = [];
  let isLoading = false;
  let errorMessage: string = '';

  onMount(() => {
    if (isVisible) {
      loadData();
    }
  });

  $: if (isVisible) {
    loadData();
  }

  async function loadData() {
    try {
      isLoading = true;

      // Load speakers for this file and user profiles
      const [speakersResponse, profilesResponse] = await Promise.all([
        axiosInstance.get(`/api/speakers/?file_uuid=${fileId}`),  // Use file_uuid parameter
        axiosInstance.get('/api/speaker-profiles/profiles')
      ]);

      speakers = speakersResponse.data;
      speakerProfiles = profilesResponse.data;

    } catch (error) {
      console.error('Error loading speaker data:', error);
      toastStore.error($t('speakerProfile.errorLoadingData'));
    } finally {
      isLoading = false;
    }
  }

  async function handleSpeakerClick(speaker: Speaker) {
    try {
      selectedSpeaker = speaker;

      // Get suggestions and cross-media occurrences
      const [suggestionsResponse, occurrencesResponse] = await Promise.all([
        axiosInstance.get(`/api/speaker-profiles/speakers/${speaker.uuid}/suggestions`).catch((err) => {
          console.error('Failed to load speaker suggestions:', err);
          return { data: [] };
        }),
        axiosInstance.get(`/api/speakers/${speaker.uuid}/cross-media`).catch((err) => {
          console.error('Failed to load cross-media occurrences:', err);
          return { data: [] };
        })
      ]);

      suggestions = suggestionsResponse.data || [];
      crossMediaOccurrences = occurrencesResponse.data || [];
      showVerification = true;

    } catch (error) {
      console.error('Error loading speaker suggestions:', error);
      toastStore.error($t('speakerProfile.errorLoadingSuggestions'));
    }
  }

  async function handleVerification(event: CustomEvent<{
    action: string;
    speaker_id: string;  // UUID
    profile_id?: string;  // UUID
    profile_name?: string;
  }>) {
    try {
      const { action, speaker_id, profile_id, profile_name } = event.detail;

      const response = await axiosInstance.post(`/api/speakers/${speaker_id}/verify`, {
        action,
        profile_id,
        profile_name
      });

      if (response.data.status === 'accepted' || response.data.status === 'created_and_assigned') {
        // Refresh data
        await loadData();
        dispatch('speakerVerified', response.data);
      }

      showVerification = false;
      selectedSpeaker = null;

    } catch (error) {
      console.error('Error verifying speaker:', error);
      errorMessage = $t('speakerProfile.errorVerifyingSpeaker');
    }
  }

  function handleVerificationCancel() {
    showVerification = false;
    selectedSpeaker = null;
    suggestions = [];
    crossMediaOccurrences = [];
  }

  // Speaker status computation is now handled by the backend
  function getSpeakerStatus(speaker: Speaker): string {
    return speaker.computed_status || 'unverified';
  }

  function getStatusColor(speaker: Speaker): string {
    return speaker.status_color || 'var(--error-color)';
  }

  function getStatusText(speaker: Speaker): string {
    return speaker.status_text || $t('speakerProfile.needsIdentification');
  }
</script>

{#if isVisible}
  <div class="speaker-manager" transition:fade>
    {#if isLoading}
      <div class="loading-state">
        <div class="loading-spinner"></div>
        <p>{$t('speakerProfile.loadingData')}</p>
      </div>
    {:else if errorMessage}
      <div class="error-state">
        <p class="error-message">{errorMessage}</p>
        <button on:click={loadData} class="retry-button">
          {$t('speakerProfile.retry')}
        </button>
      </div>
    {:else}
      <div class="manager-header">
        <h3 class="manager-title">{$t('speakerProfile.title')}</h3>
        <p class="manager-subtitle">
          {$t('speakerProfile.subtitle')}
        </p>
      </div>

      {#if speakers.length === 0}
        <div class="empty-state">
          <p>{$t('speakerProfile.noSpeakersDetected')}</p>
        </div>
      {:else}
        <div class="speakers-grid">
          {#each speakers as speaker}
            {@const status = getSpeakerStatus(speaker)}
            {#if !speaker.verified || !speaker.profile}
              <button
                class="speaker-card {status} clickable"
                on:click={() => handleSpeakerClick(speaker)}
              >
                <div class="speaker-info">
                  <div class="speaker-header">
                    <span class="speaker-name">{translateSpeakerLabel(speaker.display_name || speaker.name)}</span>
                    <div class="speaker-status" style="color: {getStatusColor(speaker)}">
                      {#if status === 'verified'}
                        ✓
                      {:else if status === 'suggested'}
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display: inline;">
                          <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/>
                          <path d="M12 9v4"/>
                          <path d="m12 17 .01 0"/>
                        </svg>
                      {:else}
                        ?
                      {/if}
                    </div>
                  </div>

                  <p class="speaker-description">
                    {getStatusText(speaker)}
                  </p>

                  {#if speaker.confidence}
                    <div class="confidence-indicator">
                      <div class="confidence-bar">
                        <div
                          class="confidence-fill"
                          style="width: {speaker.confidence * 100}%; background-color: {getStatusColor(speaker)}"
                        ></div>
                      </div>
                      <span class="confidence-text">{Math.round(speaker.confidence * 100)}%</span>
                    </div>
                  {/if}
                </div>

                <div class="speaker-action">
                  <span class="verify-text">
                    {$t('speakerProfile.clickToVerify')}
                  </span>
                </div>
              </button>
            {:else}
              <button
                class="speaker-card {status} clickable"
                on:click={() => handleSpeakerClick(speaker)}
              >
                <div class="speaker-info">
                  <div class="speaker-header">
                    <span class="speaker-name">{translateSpeakerLabel(speaker.display_name || speaker.name)}</span>
                    <div class="speaker-status" style="color: {getStatusColor(speaker)}">
                      ✓
                    </div>
                  </div>

                  <p class="speaker-description">
                    {getStatusText(speaker)}
                  </p>

                  {#if speaker.confidence}
                    <div class="confidence-indicator">
                      <div class="confidence-bar">
                        <div
                          class="confidence-fill"
                          style="width: {speaker.confidence * 100}%; background-color: {getStatusColor(speaker)}"
                        ></div>
                      </div>
                      <span class="confidence-text">{Math.round(speaker.confidence * 100)}%</span>
                    </div>
                  {/if}
                </div>

                <div class="speaker-action">
                  <span class="verify-text">
                    {$t('speakerProfile.clickToViewDetails')}
                  </span>
                </div>
              </button>
            {/if}
          {/each}
        </div>

        {#if speakerProfiles.length > 0}
          <div class="profiles-section">
            <h4 class="section-title">{$t('speakerProfile.yourProfiles')}</h4>
            <div class="profiles-grid">
              {#each speakerProfiles as profile}
                <div class="profile-card">
                  <div class="profile-info">
                    <span class="profile-name">{profile.name}</span>
                    <span class="profile-stats">
                      {profile.instance_count} {profile.instance_count !== 1 ? $t('speakerProfile.instances') : $t('speakerProfile.instance')}
                      • {profile.media_count} {profile.media_count !== 1 ? $t('speakerProfile.files') : $t('speakerProfile.file')}
                    </span>
                  </div>
                </div>
              {/each}
            </div>
          </div>
        {/if}
      {/if}
    {/if}
  </div>
{/if}

{#if showVerification && selectedSpeaker}
  <div class="verification-overlay" transition:fade>
    <SpeakerVerification
      speaker={selectedSpeaker}
      {suggestions}
      {crossMediaOccurrences}
      on:verify={handleVerification}
      on:cancel={handleVerificationCancel}
    />
  </div>
{/if}

<style>
  .speaker-manager {
    background: var(--card-background);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    padding: 1.5rem;
    box-shadow: var(--card-shadow);
  }

  .manager-header {
    margin-bottom: 1.5rem;
  }

  .manager-title {
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--text-color);
    margin: 0 0 0.5rem 0;
  }

  .manager-subtitle {
    font-size: 0.875rem;
    color: var(--text-secondary);
    margin: 0;
  }

  .loading-state, .error-state, .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    text-align: center;
  }

  .loading-spinner {
    width: 2rem;
    height: 2rem;
    border: 3px solid var(--border-color);
    border-top: 3px solid var(--primary-color);
    border-radius: 50%;
    animation: spin 1s linear infinite;
    margin-bottom: 1rem;
  }

  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }

  .error-message {
    color: var(--error-color);
    margin-bottom: 1rem;
  }

  .retry-button {
    padding: 0.5rem 1rem;
    background: var(--primary-color);
    color: white;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    font-size: 0.875rem;
    transition: all 0.2s ease;
  }

  .retry-button:hover {
    background: var(--primary-hover);
  }

  .speakers-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 1rem;
    margin-bottom: 2rem;
  }

  .speaker-card {
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 10px;
    padding: 1rem;
    transition: all 0.2s ease;
    width: 100%;
    text-align: left;
    font-family: inherit;
    font-size: inherit;
  }

  .speaker-card.clickable {
    cursor: pointer;
  }

  .speaker-card.clickable:hover {
    border-color: var(--primary-color);
    box-shadow: 0 2px 8px rgba(var(--primary-color-rgb), 0.1);
  }

  .speaker-card.clickable:focus {
    outline: 2px solid var(--primary-color);
    outline-offset: 2px;
  }

  .speaker-card.verified {
    border-color: var(--success-color);
    background: color-mix(in srgb, var(--success-color) 5%, var(--surface-color));
  }

  .speaker-card.suggested {
    border-color: var(--warning-color);
    background: color-mix(in srgb, var(--warning-color) 5%, var(--surface-color));
  }

  .speaker-card.unverified {
    border-color: var(--error-color);
    background: color-mix(in srgb, var(--error-color) 5%, var(--surface-color));
  }

  .speaker-info {
    flex: 1;
  }

  .speaker-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.5rem;
  }

  .speaker-name {
    font-weight: 500;
    color: var(--text-color);
    font-size: 0.95rem;
  }

  .speaker-status {
    font-size: 1.1rem;
    font-weight: bold;
  }

  .speaker-description {
    font-size: 0.8rem;
    color: var(--text-secondary);
    margin: 0 0 0.75rem 0;
    line-height: 1.4;
  }

  .confidence-indicator {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
  }

  .confidence-bar {
    flex: 1;
    height: 4px;
    background: var(--border-color);
    border-radius: 2px;
    overflow: hidden;
  }

  .confidence-fill {
    height: 100%;
    transition: width 0.3s ease;
    border-radius: 2px;
  }

  .confidence-text {
    font-size: 0.75rem;
    font-weight: 500;
    color: var(--text-secondary);
    min-width: 3rem;
    text-align: right;
  }

  .speaker-action {
    margin-top: 0.75rem;
  }

  .verify-text {
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--primary-color);
    text-align: center;
    display: block;
  }

  .profiles-section {
    border-top: 1px solid var(--border-color);
    padding-top: 1.5rem;
  }

  .section-title {
    font-size: 1rem;
    font-weight: 500;
    color: var(--text-color);
    margin: 0 0 1rem 0;
  }

  .profiles-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 0.75rem;
  }

  .profile-card {
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 0.75rem;
  }

  .profile-info {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .profile-name {
    font-weight: 500;
    color: var(--text-color);
    font-size: 0.875rem;
  }

  .profile-stats {
    font-size: 0.75rem;
    color: var(--text-secondary);
  }

  .verification-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: var(--modal-backdrop);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    padding: 1rem;
  }

  /* Responsive design */
  @media (max-width: 768px) {
    .speakers-grid {
      grid-template-columns: 1fr;
    }

    .profiles-grid {
      grid-template-columns: 1fr;
    }
  }

  /* Reduced motion support */
  @media (prefers-reduced-motion: reduce) {
    .loading-spinner {
      animation: none;
    }

    * {
      transition: none !important;
    }
  }
</style>
