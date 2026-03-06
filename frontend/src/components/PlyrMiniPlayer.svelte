<script lang="ts">
  import { onMount, onDestroy, createEventDispatcher } from 'svelte';
  import Plyr from 'plyr';
  import 'plyr/dist/plyr.css';
  import WaveformPlayer from '$components/WaveformPlayer.svelte';

  export let mediaUrl: string;
  export let contentType: string;
  export let startTime: number = 0;
  export let endTime: number = 0;
  export let autoplay: boolean = true;
  export let fileId: string = '';
  export let compact: boolean = true;

  const dispatch = createEventDispatcher();

  let mediaElement: HTMLVideoElement | HTMLAudioElement;
  let player: Plyr | null = null;
  let seeking = true;
  let playerCurrentTime = 0;
  let playerDuration = 0;
  let fallbackTimeout: ReturnType<typeof setTimeout>;

  $: isVideo = contentType?.startsWith('video/');

  function initPlayer() {
    if (!mediaElement) {
      seeking = false;
      return;
    }

    destroyPlayer();
    seeking = true;

    mediaElement.load();

    const audioControls = ['play', 'current-time', 'duration', 'progress', 'mute', 'volume', 'settings'];
    const videoControls = ['play', 'current-time', 'duration', 'progress', 'mute', 'settings', 'fullscreen'];

    player = new Plyr(mediaElement, {
      controls: isVideo ? videoControls : audioControls,
      settings: isVideo ? ['captions', 'speed'] : ['speed'],
      iconUrl: '/plyr.svg',
      keyboard: { global: false },
      tooltips: { controls: true },
      captions: { active: true, language: 'auto', update: true },
      fullscreen: { iosNative: true },
    });

    let hasStartedPlayback = false;

    function seekAndPlay() {
      if (hasStartedPlayback || !player) return;
      hasStartedPlayback = true;

      if (startTime > 0) {
        player.currentTime = startTime;
      }
      if (autoplay) {
        const playResult = player.play();
        if (playResult && typeof playResult.catch === 'function') {
          playResult.catch(() => {
            seeking = false;
          });
        }
      } else {
        seeking = false;
      }
    }

    const media = (player as any).media as HTMLMediaElement | undefined;
    if (media) {
      const onCanPlay = () => {
        seekAndPlay();
        media.removeEventListener('canplay', onCanPlay);
      };
      media.addEventListener('canplay', onCanPlay);
      // Handle already-ready media (e.g., from browser cache)
      if (media.readyState >= 3) {
        seekAndPlay();
      }
      media.addEventListener('seeked', () => { seeking = false; }, { once: true });
      media.addEventListener('playing', () => { seeking = false; }, { once: true });
      media.addEventListener('error', () => { seeking = false; }, { once: true });
    }

    player.on('timeupdate', () => {
      if (player) {
        playerCurrentTime = player.currentTime;
        playerDuration = player.duration || 0;
        dispatch('timeupdate', { currentTime: player.currentTime });

        if (endTime > 0 && player.currentTime >= endTime) {
          player.pause();
        }
      }
    });

    player.on('playing', () => { seeking = false; });
    player.on('error', () => { seeking = false; });
    player.on('ready', () => { dispatch('ready'); });
    player.on('ended', () => { dispatch('ended'); });

    // Fallback: clear spinner after timeout
    fallbackTimeout = setTimeout(() => { seeking = false; }, 15000);
  }

  function destroyPlayer() {
    if (player) {
      try { player.destroy(); } catch {}
      player = null;
    }
  }

  export function seek(time: number) {
    if (player) {
      player.currentTime = time;
    }
  }

  export function getPlayer(): Plyr | null {
    return player;
  }

  function handleWaveformSeek(event: CustomEvent<{ time: number }>) {
    if (player && event.detail?.time != null) {
      player.currentTime = event.detail.time;
    }
  }

  onMount(() => {
    // Wait for Svelte to bind the media element
    setTimeout(() => {
      initPlayer();
    }, 50);
  });

  onDestroy(() => {
    clearTimeout(fallbackTimeout);
    destroyPlayer();
  });
</script>

<div class="plyr-mini-player" class:compact class:audio-mode={!isVideo} class:video-mode={isVideo}>
  {#if seeking}
    <div class="seek-overlay">
      <div class="seek-spinner"></div>
    </div>
  {/if}

  {#if isVideo}
    <!-- svelte-ignore a11y-media-has-caption -->
    <video
      bind:this={mediaElement}
      preload="auto"
    >
      <source src={mediaUrl} />
    </video>
  {:else}
    <!-- svelte-ignore a11y-media-has-caption -->
    <audio
      bind:this={mediaElement}
      preload="auto"
    >
      <source src={mediaUrl} />
    </audio>
    {#if fileId}
      <div class="mini-waveform">
        <WaveformPlayer
          fileId={fileId}
          duration={playerDuration}
          currentTime={playerCurrentTime}
          height={60}
          on:seek={handleWaveformSeek}
        />
      </div>
    {/if}
  {/if}
</div>

<style>
  .plyr-mini-player {
    position: relative;
  }

  /* Seeking overlay */
  .seek-overlay {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.45);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10;
    pointer-events: none;
    border-radius: 0;
  }

  .seek-spinner {
    width: 28px;
    height: 28px;
    border: 3px solid rgba(255, 255, 255, 0.2);
    border-left-color: white;
    border-radius: 50%;
    animation: mini-spin 0.8s linear infinite;
  }

  @keyframes mini-spin {
    to { transform: rotate(360deg); }
  }

  /* Audio layout */
  .plyr-mini-player.audio-mode {
    display: flex;
    flex-direction: column;
  }

  .mini-waveform {
    width: 100%;
    padding: 0.5rem 0.5rem 0;
    background: var(--surface-color);
  }

  .plyr-mini-player.audio-mode :global(audio) {
    width: 100%;
  }

  /* Audio Plyr styles */
  .plyr-mini-player.audio-mode :global(.plyr--audio) {
    overflow: visible !important;
    transform: none !important;
    background: var(--surface-color) !important;
    color: var(--text-color) !important;
  }

  .plyr-mini-player.audio-mode :global(.plyr--audio .plyr__controls) {
    background: var(--surface-color) !important;
    border-color: var(--border-color) !important;
    padding-top: 28px !important;
  }

  .plyr-mini-player.audio-mode :global(.plyr--audio .plyr__progress) {
    position: absolute !important;
    top: 6px !important;
    left: 8px !important;
    right: 8px !important;
    width: calc(100% - 16px) !important;
    height: auto !important;
    margin: 0 !important;
    padding: 0 !important;
    z-index: 10 !important;
  }

  .plyr-mini-player.audio-mode :global(.plyr--audio .plyr__progress input[type="range"]::-webkit-slider-track) {
    height: 6px !important;
    border-radius: 3px !important;
  }

  .plyr-mini-player.audio-mode :global(.plyr--audio .plyr__progress input[type="range"]::-moz-range-track) {
    height: 6px !important;
    border-radius: 3px !important;
  }

  .plyr-mini-player.audio-mode :global(.plyr--audio .plyr__progress input[type="range"]::-webkit-slider-thumb) {
    width: 16px !important;
    height: 16px !important;
    border-radius: 50% !important;
    background: var(--primary-color) !important;
    border: none !important;
    cursor: pointer !important;
  }

  .plyr-mini-player.audio-mode :global(.plyr--audio .plyr__progress input[type="range"]::-moz-range-thumb) {
    width: 16px !important;
    height: 16px !important;
    border-radius: 50% !important;
    background: var(--primary-color) !important;
    border: none !important;
    cursor: pointer !important;
  }

  :global([data-theme='dark']) .plyr-mini-player.audio-mode :global(.plyr--audio .plyr__progress input[type="range"]::-webkit-slider-thumb) {
    background: white !important;
  }

  :global([data-theme='dark']) .plyr-mini-player.audio-mode :global(.plyr--audio .plyr__progress input[type="range"]::-moz-range-thumb) {
    background: white !important;
  }

  .plyr-mini-player.audio-mode :global(.plyr--audio .plyr__control:hover) {
    z-index: 20 !important;
  }

  .plyr-mini-player.audio-mode :global(.plyr--audio .plyr__tooltip) {
    z-index: 99999 !important;
  }

  .plyr-mini-player.audio-mode :global(.plyr--audio .plyr__control:not([data-plyr="speed"])) {
    color: var(--text-color) !important;
  }

  .plyr-mini-player.audio-mode :global(.plyr--audio .plyr__control:not([data-plyr="speed"]):hover) {
    background: var(--hover-color) !important;
    color: var(--text-color) !important;
  }

  .plyr-mini-player.audio-mode :global(.plyr--audio .plyr__time) {
    color: var(--text-color) !important;
    font-size: 13px !important;
  }

  .plyr-mini-player.audio-mode :global(.plyr--audio .plyr__volume input[type="range"]) {
    color: var(--primary-color) !important;
  }

  /* Video styles */
  .plyr-mini-player.video-mode :global(video) {
    width: 100%;
    max-height: 280px;
    display: block;
    background: #000;
  }

  .plyr-mini-player.video-mode :global(.plyr--fullscreen-active video),
  .plyr-mini-player.video-mode :global(.plyr--fullscreen-enabled video) {
    max-height: none;
  }

  :global(.plyr--fullscreen-active video),
  :global(.plyr:fullscreen video) {
    max-height: none !important;
    width: 100% !important;
    height: 100% !important;
    object-fit: contain;
  }

  .plyr-mini-player :global(.plyr) {
    border-radius: 0;
    overflow: visible;
  }

  /* Compact controls sizing */
  .plyr-mini-player.compact :global(.plyr__control) {
    padding: 5px !important;
    margin: 0 1px !important;
  }

  .plyr-mini-player.compact :global(.plyr__control svg) {
    width: 16px !important;
    height: 16px !important;
  }

  /* Video control hover backgrounds */
  .plyr-mini-player :global(.plyr--video .plyr__control:hover) {
    background: rgba(255, 255, 255, 0.25) !important;
  }

  .plyr-mini-player :global(.plyr--video .plyr__controls__item.plyr__menu) {
    background: transparent !important;
    border: none !important;
  }

  /* Settings gear button */
  .plyr-mini-player :global(.plyr--video .plyr__menu .plyr__control[aria-expanded]) {
    background: transparent !important;
    border-radius: 3px !important;
  }

  .plyr-mini-player :global(.plyr--video .plyr__menu .plyr__control[aria-expanded]:hover) {
    background: rgba(255, 255, 255, 0.25) !important;
  }

  /* YouTube-style progress bar positioning - above controls */
  .plyr-mini-player :global(.plyr--video .plyr__controls) {
    position: absolute !important;
    bottom: 0 !important;
    left: 0 !important;
    right: 0 !important;
    padding: 6px 6px 4px !important;
    align-items: center !important;
    flex-wrap: nowrap !important;
    overflow: visible !important;
  }

  .plyr-mini-player :global(.plyr--video .plyr__progress) {
    position: absolute !important;
    top: -6px !important;
    left: 0 !important;
    right: 0 !important;
    width: 100% !important;
    height: auto !important;
    margin: 0 !important;
    padding: 0 !important;
    z-index: 10 !important;
    overflow: visible !important;
  }

  .plyr-mini-player :global(.plyr--video .plyr__progress__container) {
    overflow: visible !important;
  }

  .plyr-mini-player :global(.plyr--video .plyr__progress input[type="range"]) {
    width: 100% !important;
    margin: 0 !important;
    padding: 0 !important;
  }

  .plyr-mini-player :global(.plyr--video .plyr__progress input[type="range"]::-webkit-slider-track) {
    height: 3px !important;
  }

  .plyr-mini-player :global(.plyr--video .plyr__progress input[type="range"]::-moz-range-track) {
    height: 3px !important;
  }

  .plyr-mini-player :global(.plyr--video .plyr__progress:hover input[type="range"]::-webkit-slider-track) {
    height: 5px !important;
  }

  .plyr-mini-player :global(.plyr--video .plyr__progress:hover input[type="range"]::-moz-range-track) {
    height: 5px !important;
  }

  /* Compact time display */
  .plyr-mini-player :global(.plyr__time) {
    margin-left: 4px !important;
    margin-right: 2px !important;
    font-size: 12px !important;
    color: rgba(255, 255, 255, 0.9) !important;
  }

  .plyr-mini-player :global(.plyr__time--current-time::after) {
    content: " / " !important;
    color: rgba(255, 255, 255, 0.6) !important;
  }

  .plyr-mini-player :global(.plyr__time--duration) {
    margin-left: 0 !important;
    margin-right: 4px !important;
  }

  /* Settings menu styling for dark mode */
  .plyr-mini-player :global(.plyr--video .plyr__menu) {
    background: var(--surface-color) !important;
    border: none !important;
    color: var(--text-color) !important;
  }

  .plyr-mini-player :global(.plyr--video [role="menu"]) {
    background: var(--surface-color) !important;
  }

  .plyr-mini-player :global(.plyr--video .plyr__menu .plyr__control) {
    color: var(--text-color) !important;
    background: transparent !important;
  }

  .plyr-mini-player :global(.plyr--video .plyr__menu .plyr__control:hover) {
    background: var(--hover-color) !important;
    color: var(--text-color) !important;
  }

  .plyr-mini-player :global(.plyr--video button[data-plyr="speed"]),
  .plyr-mini-player :global(.plyr--video button[data-plyr="captions"]) {
    color: var(--text-color) !important;
    background: transparent !important;
    border: none !important;
  }

  .plyr-mini-player :global(.plyr--video button[data-plyr="speed"]:hover),
  .plyr-mini-player :global(.plyr--video button[data-plyr="captions"]:hover) {
    background: var(--hover-color) !important;
    color: var(--text-color) !important;
  }

  .plyr-mini-player :global(.plyr--video button[data-plyr="speed"][aria-checked="true"]),
  .plyr-mini-player :global(.plyr--video button[data-plyr="captions"][aria-checked="true"]) {
    background: var(--primary-color) !important;
    color: white !important;
  }

  .plyr-mini-player :global(.plyr--video button[data-plyr="speed"] span),
  .plyr-mini-player :global(.plyr--video button[data-plyr="captions"] span) {
    color: inherit !important;
  }

  .plyr-mini-player :global(.plyr--video .plyr__menu__value),
  .plyr-mini-player :global(.plyr--video .plyr__badge) {
    color: inherit !important;
  }

  .plyr-mini-player :global(.plyr--video button.plyr__control--back) {
    color: var(--text-color) !important;
    background: var(--surface-color) !important;
    border: none !important;
  }

  .plyr-mini-player :global(.plyr--video button.plyr__control--back:hover) {
    background: var(--hover-color) !important;
    color: var(--text-color) !important;
  }

  .plyr-mini-player :global(.plyr--video button.plyr__control--back span) {
    color: inherit !important;
  }

  /* Audio time color override for light mode */
  .plyr-mini-player.audio-mode :global(.plyr__time) {
    color: var(--text-color) !important;
  }
</style>
