import { writable } from "svelte/store";

export type SettingsSection =
  // User sections
  | "profile"
  | "recording"
  | "audio-extraction"
  | "transcription"
  | "ai-prompts"
  | "llm-provider"
  // System sections (visible to all users)
  | "system-statistics"
  // Admin sections
  | "admin-users"
  | "admin-task-health"
  | "admin-settings";

interface SettingsModalState {
  isOpen: boolean;
  activeSection: SettingsSection;
  dirtyState: Record<SettingsSection, boolean>;
}

const initialState: SettingsModalState = {
  isOpen: false,
  activeSection: "profile",
  dirtyState: {
    profile: false,
    recording: false,
    "audio-extraction": false,
    transcription: false,
    "ai-prompts": false,
    "llm-provider": false,
    "system-statistics": false,
    "admin-users": false,
    "admin-task-health": false,
    "admin-settings": false,
  },
};

function createSettingsModalStore() {
  const { subscribe, set, update } = writable<SettingsModalState>(initialState);

  return {
    subscribe,
    open: (section?: SettingsSection) => {
      update((state) => ({
        ...state,
        isOpen: true,
        activeSection: section || "profile",
      }));
    },
    close: () => {
      update((state) => ({
        ...state,
        isOpen: false,
      }));
    },
    setActiveSection: (section: SettingsSection) => {
      update((state) => ({
        ...state,
        activeSection: section,
      }));
    },
    setDirty: (section: SettingsSection, isDirty: boolean) => {
      update((state) => ({
        ...state,
        dirtyState: {
          ...state.dirtyState,
          [section]: isDirty,
        },
      }));
    },
    clearDirty: (section: SettingsSection) => {
      update((state) => ({
        ...state,
        dirtyState: {
          ...state.dirtyState,
          [section]: false,
        },
      }));
    },
    clearAllDirty: () => {
      update((state) => ({
        ...state,
        dirtyState: Object.keys(state.dirtyState).reduce(
          (acc, key) => {
            acc[key as SettingsSection] = false;
            return acc;
          },
          {} as Record<SettingsSection, boolean>,
        ),
      }));
    },
    hasAnyDirty: (state: SettingsModalState): boolean => {
      return Object.values(state.dirtyState).some((isDirty) => isDirty);
    },
    reset: () => set(initialState),
  };
}

export const settingsModalStore = createSettingsModalStore();
