import { writable } from 'svelte/store';

interface AudioPlaybackState {
  activeSpeakerUuid: string | null;
  isPlaying: boolean;
}

const { subscribe, set, update } = writable<AudioPlaybackState>({
  activeSpeakerUuid: null,
  isPlaying: false,
});

export const audioPlaybackStore = {
  subscribe,
  play(uuid: string) {
    set({ activeSpeakerUuid: uuid, isPlaying: true });
  },
  pause() {
    update((s) => ({ ...s, isPlaying: false }));
  },
  stop() {
    set({ activeSpeakerUuid: null, isPlaying: false });
  },
};
