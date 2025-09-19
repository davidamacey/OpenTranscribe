<script lang="ts">
  import { createEventDispatcher, onMount, onDestroy } from 'svelte';
  import Plyr from 'plyr';
  import 'plyr/dist/plyr.css';

  export let videoUrl: string = '';
  export let file: any = null;
  export let isPlayerBuffering: boolean = false;
  export let loadProgress: number = 0;
  export let errorMessage: string = '';
  export let speakerList: any[] = [];

  const dispatch = createEventDispatcher();

  let player: Plyr | null = null;
  let mediaElement: HTMLVideoElement | HTMLAudioElement;
  let currentTime = 0;
  let duration = 0;
  let currentSubtitleBlobUrl: string | null = null;
  let trackElement: HTMLTrackElement | null = null;
  let currentLoadHandler: ((event: Event) => void) | null = null;


  function handleRetry() {
    dispatch('retry');
  }

  // External seek function for waveform and transcript clicks
  export async function seekToTime(time: number) {
    if (!player) {
      return;
    }

    // Update player time
    player.currentTime = time;
    currentTime = time;

    // Dispatch the seek event to parent
    dispatch('timeupdate', {
      currentTime: time,
      duration: duration
    });
  }

  // External function to update subtitles when transcript becomes available or is edited
  export async function updateSubtitles() {
    if (!player || !file || !file.transcript_segments || !Array.isArray(file.transcript_segments) || file.transcript_segments.length === 0) {
      return;
    }

    try {
      // Find the track element
      const videoElement = player.media as HTMLVideoElement;
      trackElement = videoElement?.querySelector('track[kind="captions"]') as HTMLTrackElement;

      if (!trackElement) {
        console.error('No track element found!');
        return;
      }

      // Create speaker display name mapping
      const speakerMapping = new Map();
      speakerList.forEach((speaker: any) => {
        speakerMapping.set(speaker.name, speaker.display_name || speaker.name);
      });

      // Generate WebVTT content from transcript segments with speaker mapping
      const webvttContent = generateWebVTTFromSegments(file.transcript_segments, speakerMapping);

      // Create blob URL for the WebVTT content
      const blob = new Blob([webvttContent], { type: 'text/vtt' });
      const vttUrl = URL.createObjectURL(blob);

      // Clean up any existing blob URL to prevent memory leaks
      if (currentSubtitleBlobUrl) {
        URL.revokeObjectURL(currentSubtitleBlobUrl);
      }
      currentSubtitleBlobUrl = vttUrl;

      // Remove any existing event listeners to prevent duplicates
      if (currentLoadHandler) {
        trackElement.removeEventListener('load', currentLoadHandler);
      }

      // Update the track element's src - this will trigger reload
      trackElement.src = vttUrl;

      // Set up proper track loading
      const textTrack = trackElement.track;
      if (textTrack) {
        // First disable the track
        textTrack.mode = 'disabled';

        // Create and store the load handler for proper cleanup
        currentLoadHandler = () => {
          textTrack.mode = 'showing';

          if (player.captions) {
            player.captions.active = true;
          }

          // Force Plyr to update its caption state
          if (player.elements?.buttons?.captions && !player.captions.active) {
            player.elements.buttons.captions.click();
          }
        };

        // Set up load event listener
        trackElement.addEventListener('load', currentLoadHandler, { once: true });

        // Also try setting up without waiting for load event (fallback)
        setTimeout(() => {
          if (textTrack.cues?.length === 0) {
            textTrack.mode = 'showing';

            if (player.captions) {
              player.captions.active = true;
            }
          }
        }, 1000);
      }

    } catch (error) {
      console.error('Error updating subtitles:', error);
    }
  }

  function initializePlyr() {
    if (!mediaElement || player) {
      return;
    }

    const isAudio = file?.content_type?.startsWith('audio/');
    const isMac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);

    // Build controls array based on media type and platform - YouTube style layout
    const controls = [
      'play-large',
      'play',
      'current-time', // Elapsed time
      'duration', // Total time
      'progress' // Progress bar will be repositioned via CSS
    ];

    // Add volume controls first, then CC to the right of volume
    controls.push('mute', 'volume');

    // Add captions only for video - to the right of volume
    if (!isAudio) {
      controls.push('captions');
    }

    // Add remaining controls
    controls.push('settings');
    if (!isAudio) {
      controls.push('pip');
    }
    if (isMac) {
      controls.push('airplay');
    }
    if (!isAudio) {
      controls.push('fullscreen');
    }

    // Settings menu options
    const settings = isAudio ? ['speed'] : ['captions', 'speed'];

    const plyrConfig = {
      controls,
      settings,
      iconUrl: '/plyr.svg',
      keyboard: { global: true },
      tooltips: { controls: true },
      captions: {
        active: true,
        language: 'auto',
        update: true
      },
      playsinline: true,
      fullscreen: { iosNative: true }
    };

    try {
      // Initialize Plyr
      player = new Plyr(mediaElement, plyrConfig);

      // Set up event listeners
      player.on('ready', () => {
        duration = player.duration;
        dispatch('loadedmetadata', { duration });

        // Initialize subtitles when player is ready
        if (file && file.status === 'completed' && file.transcript_segments && file.transcript_segments.length > 0) {
          setTimeout(() => {
            updateSubtitles();
          }, 500);
        }
      });

      player.on('timeupdate', () => {
        currentTime = player.currentTime;
        duration = player.duration;
        dispatch('timeupdate', {
          currentTime,
          duration
        });
      });

      player.on('play', () => dispatch('play'));
      player.on('pause', () => dispatch('pause'));
      player.on('ended', () => dispatch('ended'));
      player.on('seeking', () => dispatch('seeking'));
      player.on('seeked', () => dispatch('seeked'));

    } catch (error) {
      console.error('Error creating Plyr player:', error);
    }
  }

  function destroyPlyr() {
    // Clean up subtitle blob URL
    if (currentSubtitleBlobUrl) {
      URL.revokeObjectURL(currentSubtitleBlobUrl);
      currentSubtitleBlobUrl = null;
    }

    // Clean up event listener reference
    if (currentLoadHandler && trackElement) {
      trackElement.removeEventListener('load', currentLoadHandler);
      currentLoadHandler = null;
    }

    if (player) {
      try {
        player.destroy();
        player = null;
      } catch (error) {
        console.error('Error destroying Plyr player:', error);
      }
    }
  }

  function generateWebVTTFromSegments(segments: any[], speakerMapping?: Map<string, string>): string {
    // Ensure proper WebVTT header with NOTE for debugging
    let webvtt = 'WEBVTT\n\nNOTE Generated from transcript segments\n\n';

    let validCues = 0;
    segments.forEach((segment, index) => {
      // Check for required fields with multiple possible field names
      const startTime = segment.start_time !== undefined ? segment.start_time : segment.start;
      const endTime = segment.end_time !== undefined ? segment.end_time : segment.end;
      const text = segment.text;

      if (startTime !== undefined && endTime !== undefined && text && startTime < endTime) {
        const formattedStartTime = formatTime(startTime);
        const formattedEndTime = formatTime(endTime);

        // Get original speaker name from segment
        const originalSpeakerName = segment.speaker_label || segment.speaker?.name || segment.speaker || `Speaker ${index + 1}`;

        // Use speaker mapping to get display name, fallback to original
        const displaySpeakerName = speakerMapping?.get(originalSpeakerName) ||
                                  segment.speaker?.display_name ||
                                  originalSpeakerName;

        const displayText = `${displaySpeakerName}: ${text.trim()}`;

        // Add cue with proper WebVTT format
        webvtt += `${formattedStartTime} --> ${formattedEndTime}\n`;
        webvtt += `${displayText}\n\n`;
        validCues++;
      }
    });

    return webvtt;
  }

  function formatTime(seconds: number): string {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    const ms = Math.floor((seconds % 1) * 1000);

    if (hours > 0) {
      return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}.${ms.toString().padStart(3, '0')}`;
    } else {
      return `${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}.${ms.toString().padStart(3, '0')}`;
    }
  }

  onMount(() => {
    if (videoUrl && mediaElement) {
      initializePlyr();
    }
  });

  onDestroy(() => {
    destroyPlyr();
  });

  // Watch for changes to videoUrl or mediaElement to initialize player
  $: if (videoUrl && mediaElement && !player) {
    initializePlyr();
  }
</script>

<div class="video-player-container">
  {#if videoUrl}
    {#if file?.content_type?.startsWith('audio/')}
      <!-- Plyr Audio Player -->
      <!-- svelte-ignore a11y-media-has-caption -->
      <audio
        bind:this={mediaElement}
        id="player"
        preload="auto"
        playsinline
      >
        <source src={videoUrl} type={file.content_type} />
        Your browser does not support the audio element.
      </audio>
    {:else}
      <!-- Plyr Video Player -->
      <!-- svelte-ignore a11y-media-has-caption -->
      <video
        bind:this={mediaElement}
        id="player"
        preload="auto"
        playsinline
      >
        <source src={videoUrl} type={file?.content_type || 'video/mp4'} />
        <!-- Always include track element so CC button appears -->
        <track kind="captions" label="Auto-generated Captions" srclang="en" default />
        Your browser does not support the video element.
      </video>
    {/if}

    {#if isPlayerBuffering}
      <div class="buffer-indicator">
        <div class="spinner"></div>
        <div class="buffer-text">Loading video... {Math.round(loadProgress)}%</div>
      </div>
    {/if}

    {#if errorMessage}
      <p class="error-message">{errorMessage}</p>
      <button
        class="retry-button"
        on:click={handleRetry}
        title="Retry loading the video file"
      >Retry Loading Video</button>
    {/if}
  {:else}
    <div class="no-preview">
      {#if errorMessage}
        <p class="error-message">{errorMessage}</p>
        <button on:click={handleRetry} class="retry-button">Retry Loading Video</button>
      {:else}
        Video not available.
      {/if}
    </div>
  {/if}
</div>

<style>
  .video-player-container {
    position: relative;
    width: 100%;
    border-radius: 8px;
    overflow: visible !important;
    background: var(--surface-color);
    z-index: 100;
  }

  /* Force container overflow and positioning for audio menus */
  :global(.plyr--audio) {
    overflow: visible !important;
    transform: none !important;
  }

  /* Ensure parent containers don't clip */
  :global(.video-column) {
    overflow: visible !important;
  }

  :global(.main-content-grid) {
    overflow: visible !important;
  }

  :global(.plyr) {
    border-radius: 8px;
    overflow: hidden;
  }

  :global(.plyr__video-wrapper) {
    border-radius: 8px;
  }

  :global(.plyr--video .plyr__control:not([data-plyr="settings"]):hover) {
    background: rgba(255, 255, 255, 0.25) !important;
  }

  /* CC button - transparent background like other video icons */
  :global(.plyr--video .plyr__control[data-plyr="captions"]) {
    background: transparent !important;
    color: white !important;
  }

  :global(.plyr--video .plyr__control[data-plyr="captions"]:hover) {
    background: rgba(255, 255, 255, 0.25) !important;
    color: white !important;
  }


  :global(.plyr--video .plyr__control[data-plyr="play"]:hover) {
    background: rgba(255, 255, 255, 0.25) !important;
  }

  /* Settings button for video - transparent background with white icon like CC */
  :global(.plyr--video .plyr__control[data-plyr="settings"]) {
    background: transparent !important;
    color: white !important;
  }

  :global(.plyr--video .plyr__control[data-plyr="settings"]:hover) {
    background: rgba(255, 255, 255, 0.25) !important;
    color: white !important;
  }

  /* Settings button SVG styling */
  :global(.plyr--video .plyr__control[data-plyr="settings"] svg) {
    color: white !important;
    fill: white !important;
  }

  /* Settings menu container - transparent background */
  :global(.plyr--video .plyr__controls__item.plyr__menu) {
    background: transparent !important;
    border: none !important;
  }

  :global(.plyr--video .plyr__volume input[type="range"]::-webkit-slider-thumb:hover) {
    background: #ffffff !important;
  }

  :global(.plyr--video .plyr__volume input[type="range"]::-moz-range-thumb:hover) {
    background: #ffffff !important;
  }

  /* YouTube-style progress bar positioning - above controls, full player width - VIDEO ONLY */
  :global(.plyr--video .plyr__controls) {
    position: absolute !important;
    bottom: 0 !important;
    left: 0 !important;
    right: 0 !important;
    padding-top: 12px !important; /* Increased spacing to prevent overlap */
  }

  /* Position progress bar above controls at full player width - moved up - VIDEO ONLY */
  :global(.plyr--video .plyr__progress) {
    position: absolute !important;
    top: -8px !important; /* Moved up to prevent button overlap */
    left: 0 !important;
    right: 0 !important;
    width: 100% !important;
    height: auto !important;
    margin: 0 !important;
    padding: 0 !important;
    z-index: 10 !important;
  }

  /* Ensure progress bar input takes full width - VIDEO ONLY */
  :global(.plyr--video .plyr__progress input[type="range"]) {
    width: 100% !important;
    margin: 0 !important;
    padding: 0 !important;
  }

  /* Style the progress bar to be more prominent like YouTube - VIDEO ONLY */
  :global(.plyr--video .plyr__progress input[type="range"]::-webkit-slider-track) {
    height: 4px !important;
  }

  :global(.plyr--video .plyr__progress input[type="range"]::-moz-range-track) {
    height: 4px !important;
  }

  /* Make the progress bar slightly thicker on hover - VIDEO ONLY */
  :global(.plyr--video .plyr__progress:hover input[type="range"]::-webkit-slider-track) {
    height: 6px !important;
  }

  :global(.plyr--video .plyr__progress:hover input[type="range"]::-moz-range-track) {
    height: 6px !important;
  }

  /* Style time displays next to play button like YouTube - elapsed / total */
  :global(.plyr__time) {
    margin-left: 8px !important;
    margin-right: 2px !important;
    font-size: 14px !important;
    color: rgba(255, 255, 255, 0.9) !important;
  }

  /* Add slash separator between current time and duration */
  :global(.plyr__time--current-time::after) {
    content: " / " !important;
    color: rgba(255, 255, 255, 0.7) !important;
  }

  /* Style duration time */
  :global(.plyr__time--duration) {
    margin-left: 0 !important;
    margin-right: 16px !important;
  }

  /* Ensure proper spacing between controls */
  :global(.plyr__control) {
    margin-right: 4px !important;
  }

  /* Dark mode styles for audio players only */
  :global(.plyr--audio) {
    background: var(--surface-color) !important;
    color: var(--text-color) !important;
  }

  :global(.plyr--audio .plyr__controls) {
    background: var(--surface-color) !important;
    border-color: var(--border-color) !important;
    padding-top: 28px !important; /* Increased space above controls for progress bar visibility */
  }

  :global(.plyr--audio .plyr__control:not([data-plyr="speed"])) {
    color: var(--text-color) !important;
  }

  :global(.plyr--audio .plyr__control:not([data-plyr="speed"]):hover) {
    background: var(--hover-color) !important;
    color: var(--text-color) !important;
  }

  :global(.plyr--audio .plyr__control:not([data-plyr="speed"])[aria-pressed="true"]) {
    background: var(--primary-color) !important;
    color: white !important;
  }

  :global(.plyr--audio .plyr__time) {
    color: var(--text-color) !important;
  }

  :global(.plyr--audio .plyr__progress input[type="range"]) {
    background: transparent !important;
  }

  :global(.plyr--audio .plyr__progress input[type="range"]::-webkit-slider-track) {
    background: var(--border-color) !important;
  }

  :global(.plyr--audio .plyr__progress input[type="range"]::-moz-range-track) {
    background: var(--border-color) !important;
  }

  /* Audio progress bar thumb - blue in light mode, white in dark mode */
  :global(.plyr--audio .plyr__progress input[type="range"]::-webkit-slider-thumb) {
    background: var(--primary-color) !important;
    border: none !important;
  }

  :global(.plyr--audio .plyr__progress input[type="range"]::-moz-range-thumb) {
    background: var(--primary-color) !important;
    border: none !important;
  }

  /* Dark mode specific - white thumbs */
  :global([data-theme='dark'] .plyr--audio .plyr__progress input[type="range"]::-webkit-slider-thumb) {
    background: white !important;
  }

  :global([data-theme='dark'] .plyr--audio .plyr__progress input[type="range"]::-moz-range-thumb) {
    background: white !important;
  }

  /* Audio player progress bar positioning and sizing - AUDIO ONLY */
  :global(.plyr--audio .plyr__progress) {
    position: absolute !important;
    top: 6px !important; /* Position in the increased padding space with more clearance */
    left: 8px !important;
    right: 8px !important;
    width: calc(100% - 16px) !important;
    height: auto !important;
    margin: 0 !important;
    padding: 0 !important;
    z-index: 10 !important;
  }

  /* Make audio progress bar track more prominent */
  :global(.plyr--audio .plyr__progress input[type="range"]::-webkit-slider-track) {
    height: 6px !important;
    border-radius: 3px !important;
  }

  :global(.plyr--audio .plyr__progress input[type="range"]::-moz-range-track) {
    height: 6px !important;
    border-radius: 3px !important;
  }

  /* Make audio progress bar thumb more prominent */
  :global(.plyr--audio .plyr__progress input[type="range"]::-webkit-slider-thumb) {
    width: 16px !important;
    height: 16px !important;
    border-radius: 50% !important;
    cursor: pointer !important;
  }

  :global(.plyr--audio .plyr__progress input[type="range"]::-moz-range-thumb) {
    width: 16px !important;
    height: 16px !important;
    border-radius: 50% !important;
    cursor: pointer !important;
  }

  :global(.plyr--audio .plyr__volume input[type="range"]::-webkit-slider-track) {
    background: var(--border-color) !important;
  }

  :global(.plyr--audio .plyr__volume input[type="range"]::-moz-range-track) {
    background: var(--border-color) !important;
  }

  /* Audio volume thumb - blue in light mode, white in dark mode */
  :global(.plyr--audio .plyr__volume input[type="range"]::-webkit-slider-thumb) {
    background: var(--primary-color) !important;
    border: none !important;
  }

  :global(.plyr--audio .plyr__volume input[type="range"]::-moz-range-thumb) {
    background: var(--primary-color) !important;
    border: none !important;
  }

  /* Dark mode specific - white volume thumbs */
  :global([data-theme='dark'] .plyr--audio .plyr__volume input[type="range"]::-webkit-slider-thumb) {
    background: white !important;
  }

  :global([data-theme='dark'] .plyr--audio .plyr__volume input[type="range"]::-moz-range-thumb) {
    background: white !important;
  }

  /* Ensure audio player popups appear above other components */
  :global(.plyr--audio .plyr__menu) {
    z-index: 99999 !important;
    position: relative !important;
  }

  :global(.plyr--audio .plyr__menu__container) {
    z-index: 99999 !important;
    position: absolute !important;
  }

  :global(.plyr--audio .plyr__menu__container .plyr__control) {
    z-index: 99999 !important;
  }

  :global(.plyr--audio .plyr__tooltip) {
    z-index: 99999 !important;
  }

  :global(.plyr--audio .plyr__volume) {
    z-index: 1000 !important;
  }

  /* Ensure the settings button and its dropdown have highest z-index */
  :global(.plyr--audio .plyr__control--overlaid) {
    z-index: 99998 !important;
  }

  :global(.plyr--audio .plyr__control[aria-haspopup="true"]) {
    z-index: 99998 !important;
  }

  /* Force the entire audio player container to have elevated z-index when menu is open */
  :global(.plyr--audio.plyr--menu-open) {
    z-index: 99997 !important;
    position: relative !important;
  }

  /* Dark mode styles for audio player settings popup menu only */
  :global(.plyr--audio .plyr__menu) {
    background: var(--surface-color) !important;
    border: none !important;
    color: var(--text-color) !important;
  }

  /* Target the menu container with role="menu" */
  :global(.plyr--audio [role="menu"]) {
    background: var(--surface-color) !important;
  }

  /* Target speed control buttons */
  :global(.plyr--audio button[data-plyr="speed"]) {
    color: var(--text-color) !important;
    background: transparent !important;
    border: none !important;
  }

  :global(.plyr--audio button[data-plyr="speed"]:hover) {
    background: var(--hover-color) !important;
    color: var(--text-color) !important;
  }

  /* Selected speed option */
  :global(.plyr--audio button[data-plyr="speed"][aria-checked="true"]) {
    background: var(--primary-color) !important;
    color: white !important;
  }

  /* Speed button spans */
  :global(.plyr--audio button[data-plyr="speed"] span) {
    color: inherit !important;
  }

  /* Dark mode styles for video player settings popup menu */
  :global(.plyr--video .plyr__menu) {
    background: var(--surface-color) !important;
    border: none !important;
    color: var(--text-color) !important;
  }

  /* Target the menu container with role="menu" for video */
  :global(.plyr--video [role="menu"]) {
    background: var(--surface-color) !important;
  }

  /* Force all menu items in video to have dark theme colors */
  :global(.plyr--video .plyr__menu .plyr__control) {
    color: var(--text-color) !important;
    background: transparent !important;
  }

  :global(.plyr--video .plyr__menu .plyr__control:hover) {
    background: var(--hover-color) !important;
    color: var(--text-color) !important;
  }

  /* Target speed and caption control buttons for video */
  :global(.plyr--video button[data-plyr="speed"]),
  :global(.plyr--video button[data-plyr="captions"]) {
    color: var(--text-color) !important;
    background: transparent !important;
    border: none !important;
  }

  :global(.plyr--video button[data-plyr="speed"]:hover),
  :global(.plyr--video button[data-plyr="captions"]:hover) {
    background: var(--hover-color) !important;
    color: var(--text-color) !important;
  }

  /* Selected options for video */
  :global(.plyr--video button[data-plyr="speed"][aria-checked="true"]),
  :global(.plyr--video button[data-plyr="captions"][aria-checked="true"]) {
    background: var(--primary-color) !important;
    color: white !important;
  }

  /* Button spans for video */
  :global(.plyr--video button[data-plyr="speed"] span),
  :global(.plyr--video button[data-plyr="captions"] span) {
    color: inherit !important;
  }

  /* Video settings menu forward buttons */
  :global(.plyr--video button[data-plyr="settings"].plyr__control--forward) {
    color: var(--text-color) !important;
    background: transparent !important;
    border: none !important;
  }

  :global(.plyr--video button[data-plyr="settings"].plyr__control--forward:hover) {
    background: var(--hover-color) !important;
    color: var(--text-color) !important;
  }

  /* Language controls - ensure readable text */
  :global(.plyr--video button[data-plyr="language"]) {
    color: var(--text-color) !important;
    background: var(--surface-color) !important;
    border: none !important;
  }

  :global(.plyr--video button[data-plyr="language"]:hover) {
    background: var(--hover-color) !important;
    color: var(--text-color) !important;
  }

  /* Selected language option */
  :global(.plyr--video button[data-plyr="language"][aria-checked="true"]) {
    background: var(--primary-color) !important;
    color: white !important;
  }

  /* Menu value spans and badge */
  :global(.plyr--video .plyr__menu__value),
  :global(.plyr--video .plyr__badge) {
    color: inherit !important;
  }

  /* Dark mode for menu back button - audio only */
  :global(.plyr--audio button.plyr__control--back) {
    color: var(--text-color) !important;
    background: transparent !important;
    border: none !important;
  }

  :global(.plyr--audio button.plyr__control--back:hover) {
    background: var(--hover-color) !important;
    color: var(--text-color) !important;
  }

  :global(.plyr--audio button.plyr__control--back span) {
    color: inherit !important;
  }

  /* Dark mode for video menu back button */
  :global(.plyr--video button.plyr__control--back) {
    color: var(--text-color) !important;
    background: var(--surface-color) !important;
    border: none !important;
  }

  :global(.plyr--video button.plyr__control--back:hover) {
    background: var(--hover-color) !important;
    color: var(--text-color) !important;
  }

  :global(.plyr--video button.plyr__control--back span) {
    color: inherit !important;
  }

  .buffer-indicator {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    text-align: center;
    color: white;
    z-index: 10;
  }

  .spinner {
    border: 4px solid rgba(255, 255, 255, 0.1);
    border-left: 4px solid white;
    border-radius: 50%;
    width: 40px;
    height: 40px;
    animation: spin 1s linear infinite;
    margin: 0 auto 10px;
  }

  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }

  .buffer-text {
    font-size: 14px;
    font-weight: 500;
  }

  .error-message {
    color: var(--error-color);
    margin: 10px 0;
    text-align: center;
  }

  .retry-button {
    background: var(--primary-color);
    color: white;
    border: none;
    padding: 8px 16px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 14px;
    transition: background-color 0.2s;
  }

  .retry-button:hover {
    background: var(--primary-color-hover);
  }

  .no-preview {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 200px;
    background: var(--bg-color);
    border: 2px dashed var(--border-color);
    border-radius: 8px;
    color: var(--text-muted);
  }
</style>