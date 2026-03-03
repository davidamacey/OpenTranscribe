<script lang="ts">
  export let clipUrl: string;
  export let small = false;

  let audio: HTMLAudioElement;
  let playing = false;

  function toggle() {
    if (!audio) return;
    if (playing) {
      audio.pause();
    } else {
      audio.play();
    }
  }

  function onPlay() {
    playing = true;
  }
  function onPause() {
    playing = false;
  }
  function onEnded() {
    playing = false;
  }
</script>

<div class="audio-clip-player" class:small>
  <audio
    bind:this={audio}
    src={clipUrl}
    preload="none"
    on:play={onPlay}
    on:pause={onPause}
    on:ended={onEnded}
  ></audio>
  <button
    class="play-btn"
    class:playing
    on:click={toggle}
    title={playing ? 'Pause' : 'Play voice sample'}
  >
    {#if playing}
      <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
        <rect x="3" y="2" width="4" height="12" rx="1" />
        <rect x="9" y="2" width="4" height="12" rx="1" />
      </svg>
    {:else}
      <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
        <path d="M4 2l10 6-10 6V2z" />
      </svg>
    {/if}
  </button>
</div>

<style>
  .audio-clip-player {
    display: inline-flex;
    align-items: center;
  }

  .play-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    border: 1px solid var(--color-border, #d1d5db);
    background: var(--color-bg-secondary, #f9fafb);
    color: var(--color-text-primary, #111827);
    cursor: pointer;
    transition: all 0.15s ease;
  }

  .play-btn:hover {
    background: var(--color-primary, #3b82f6);
    color: white;
    border-color: var(--color-primary, #3b82f6);
  }

  .play-btn.playing {
    background: var(--color-primary, #3b82f6);
    color: white;
    border-color: var(--color-primary, #3b82f6);
  }

  .small .play-btn {
    width: 24px;
    height: 24px;
  }

  .small .play-btn svg {
    width: 12px;
    height: 12px;
  }
</style>
