import { writable, derived } from 'svelte/store';

// Types for gallery state
export interface GalleryState {
  activeTab: 'gallery' | 'status';
  isSelecting: boolean;
  selectedFiles: Set<number>;
  files: any[];
  showFilters: boolean;
}

export interface GalleryActions {
  setActiveTab: (tab: 'gallery' | 'status') => void;
  toggleSelection: () => void;
  setSelecting: (selecting: boolean) => void;
  toggleFileSelection: (fileId: number) => void;
  selectAllFiles: () => void;
  clearSelection: () => void;
  setFiles: (files: any[]) => void;
  toggleFilters: () => void;
  triggerUpload: () => void;
  triggerCollections: () => void;
  triggerAddToCollection: () => void;
  triggerDeleteSelected: () => void;
}

// Initial state
const initialState: GalleryState = {
  activeTab: 'gallery',
  isSelecting: false,
  selectedFiles: new Set<number>(),
  files: [],
  showFilters: true
};

// Create the store
function createGalleryStore() {
  const { subscribe, set, update } = writable<GalleryState>(initialState);

  // Action stores for triggering operations
  const uploadTrigger = writable<number>(0);
  const collectionsTrigger = writable<number>(0);
  const addToCollectionTrigger = writable<number>(0);
  const deleteSelectedTrigger = writable<number>(0);

  return {
    subscribe,
    // State management actions
    setActiveTab: (tab: 'gallery' | 'status') => {
      update(state => ({ ...state, activeTab: tab }));
    },

    setSelecting: (selecting: boolean) => {
      update(state => ({
        ...state,
        isSelecting: selecting,
        selectedFiles: selecting ? state.selectedFiles : new Set<number>()
      }));
    },

    toggleSelection: () => {
      update(state => ({
        ...state,
        isSelecting: !state.isSelecting,
        selectedFiles: !state.isSelecting ? state.selectedFiles : new Set<number>()
      }));
    },

    toggleFileSelection: (fileId: number) => {
      update(state => {
        const newSelected = new Set(state.selectedFiles);
        if (newSelected.has(fileId)) {
          newSelected.delete(fileId);
        } else {
          newSelected.add(fileId);
        }
        return { ...state, selectedFiles: newSelected };
      });
    },

    selectAllFiles: () => {
      update(state => {
        const allSelected = state.selectedFiles.size === state.files.length;
        const newSelected = allSelected ? new Set<number>() : new Set(state.files.map(f => f.id));
        return { ...state, selectedFiles: newSelected };
      });
    },

    clearSelection: () => {
      update(state => ({
        ...state,
        isSelecting: false,
        selectedFiles: new Set<number>()
      }));
    },

    setFiles: (files: any[]) => {
      update(state => ({ ...state, files }));
    },

    toggleFilters: () => {
      update(state => ({ ...state, showFilters: !state.showFilters }));
    },

    // Action triggers (for UI operations)
    triggerUpload: () => {
      uploadTrigger.update(n => n + 1);
    },

    triggerCollections: () => {
      collectionsTrigger.update(n => n + 1);
    },

    triggerAddToCollection: () => {
      addToCollectionTrigger.update(n => n + 1);
    },

    triggerDeleteSelected: () => {
      deleteSelectedTrigger.update(n => n + 1);
    },

    // Subscribe to action triggers (skip initial values)
    onUploadTrigger: (callback: (value: number) => void) => {
      let hasInitialized = false;
      return uploadTrigger.subscribe((value) => {
        if (hasInitialized && value > 0) {
          callback(value);
        }
        hasInitialized = true;
      });
    },

    onCollectionsTrigger: (callback: (value: number) => void) => {
      let hasInitialized = false;
      return collectionsTrigger.subscribe((value) => {
        if (hasInitialized && value > 0) {
          callback(value);
        }
        hasInitialized = true;
      });
    },

    onAddToCollectionTrigger: (callback: (value: number) => void) => {
      let hasInitialized = false;
      return addToCollectionTrigger.subscribe((value) => {
        if (hasInitialized && value > 0) {
          callback(value);
        }
        hasInitialized = true;
      });
    },

    onDeleteSelectedTrigger: (callback: (value: number) => void) => {
      let hasInitialized = false;
      return deleteSelectedTrigger.subscribe((value) => {
        if (hasInitialized && value > 0) {
          callback(value);
        }
        hasInitialized = true;
      });
    },
  };
}

export const galleryStore = createGalleryStore();

// Derived stores for convenient access
export const galleryState = derived(galleryStore, $store => $store);
export const isGalleryPage = derived(galleryStore, $store => $store.activeTab === 'gallery');
export const selectedCount = derived(galleryStore, $store => $store.selectedFiles.size);
export const allFilesSelected = derived(galleryStore, $store =>
  $store.files.length > 0 && $store.selectedFiles.size === $store.files.length
);