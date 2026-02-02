import { writable, derived } from 'svelte/store';
import { browser } from '$app/environment';

// LocalStorage key for view mode persistence
const VIEW_MODE_STORAGE_KEY = 'gallery-view-mode';

// Helper to get persisted view mode
function getPersistedViewMode(): 'grid' | 'list' {
  if (!browser) return 'grid';
  const stored = localStorage.getItem(VIEW_MODE_STORAGE_KEY);
  if (stored === 'list' || stored === 'grid') {
    return stored;
  }
  return 'grid';
}

// Pagination metadata interface
interface PaginationMetadata {
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  hasMore: boolean;
}

// Types for gallery state
export type ViewMode = 'grid' | 'list';

export interface GalleryState {
  activeTab: 'gallery' | 'status';
  viewMode: ViewMode;
  isSelecting: boolean;
  selectedFiles: Set<string>; // UUIDs
  lastSelectedId: string | null; // For shift+click range selection
  files: any[];
  showFilters: boolean;
  currentPage: number; // 0 = nothing loaded
  pageSize: number;
  totalFiles: number;
  totalPages: number;
  hasMoreFiles: boolean;
  isLoadingMore: boolean;
}

export interface GalleryActions {
  setActiveTab: (tab: 'gallery' | 'status') => void;
  setViewMode: (mode: ViewMode) => void;
  toggleSelection: () => void;
  setSelecting: (selecting: boolean) => void;
  toggleFileSelection: (fileId: string) => void; // UUID
  handleMultiSelect: (fileId: string, ctrlKey: boolean, shiftKey: boolean) => void;
  selectAllFiles: () => void;
  clearSelection: () => void;
  setFiles: (files: any[]) => void;
  toggleFilters: () => void;
  triggerUpload: () => void;
  triggerCollections: () => void;
  triggerAddToCollection: () => void;
  triggerDeleteSelected: () => void;
  appendFiles: (newFiles: any[], metadata: PaginationMetadata) => void;
  resetPagination: () => void;
  setLoadingMore: (loading: boolean) => void;
}

// Initial state
const initialState: GalleryState = {
  activeTab: 'gallery',
  viewMode: getPersistedViewMode(),
  isSelecting: false,
  selectedFiles: new Set<string>(), // UUIDs
  lastSelectedId: null,
  files: [],
  showFilters: true,
  currentPage: 0,
  pageSize: 20,
  totalFiles: 0,
  totalPages: 0,
  hasMoreFiles: false,
  isLoadingMore: false,
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
      update((state) => ({ ...state, activeTab: tab }));
    },

    setViewMode: (mode: ViewMode) => {
      if (browser) {
        localStorage.setItem(VIEW_MODE_STORAGE_KEY, mode);
      }
      update((state) => ({ ...state, viewMode: mode }));
    },

    setSelecting: (selecting: boolean) => {
      update((state) => ({
        ...state,
        isSelecting: selecting,
        selectedFiles: selecting ? state.selectedFiles : new Set<string>(),
        lastSelectedId: selecting ? state.lastSelectedId : null,
      }));
    },

    toggleSelection: () => {
      update((state) => ({
        ...state,
        isSelecting: !state.isSelecting,
        selectedFiles: !state.isSelecting ? state.selectedFiles : new Set<string>(),
        lastSelectedId: !state.isSelecting ? state.lastSelectedId : null,
      }));
    },

    toggleFileSelection: (fileId: string) => {
      update((state) => {
        const newSelected = new Set(state.selectedFiles);
        if (newSelected.has(fileId)) {
          newSelected.delete(fileId);
        } else {
          newSelected.add(fileId);
        }
        return { ...state, selectedFiles: newSelected, lastSelectedId: fileId };
      });
    },

    handleMultiSelect: (fileId: string, ctrlKey: boolean, shiftKey: boolean) => {
      update((state) => {
        const newSelected = new Set(state.selectedFiles);

        if (shiftKey && state.lastSelectedId) {
          // Range select: find indices of anchor and target in files array
          const fileIds = state.files.map((f) => f.uuid);
          const anchorIdx = fileIds.indexOf(state.lastSelectedId);
          const targetIdx = fileIds.indexOf(fileId);

          if (anchorIdx !== -1 && targetIdx !== -1) {
            const start = Math.min(anchorIdx, targetIdx);
            const end = Math.max(anchorIdx, targetIdx);
            for (let i = start; i <= end; i++) {
              newSelected.add(fileIds[i]);
            }
          } else {
            // Fallback: just toggle the item
            if (newSelected.has(fileId)) {
              newSelected.delete(fileId);
            } else {
              newSelected.add(fileId);
            }
          }
        } else {
          // Ctrl/Cmd+click or shift without anchor: toggle individual
          if (newSelected.has(fileId)) {
            newSelected.delete(fileId);
          } else {
            newSelected.add(fileId);
          }
        }

        const isSelecting = newSelected.size > 0;
        return {
          ...state,
          selectedFiles: newSelected,
          lastSelectedId: fileId,
          isSelecting,
        };
      });
    },

    selectAllFiles: () => {
      update((state) => {
        const allSelected = state.selectedFiles.size === state.files.length;
        const newSelected = allSelected
          ? new Set<string>()
          : new Set(state.files.map((f) => f.uuid));
        return { ...state, selectedFiles: newSelected };
      });
    },

    clearSelection: () => {
      update((state) => ({
        ...state,
        isSelecting: false,
        selectedFiles: new Set<string>(),
        lastSelectedId: null,
      }));
    },

    setFiles: (files: any[]) => {
      update((state) => ({ ...state, files }));
    },

    toggleFilters: () => {
      update((state) => ({ ...state, showFilters: !state.showFilters }));
    },

    // Action triggers (for UI operations)
    triggerUpload: () => {
      uploadTrigger.update((n) => n + 1);
    },

    triggerCollections: () => {
      collectionsTrigger.update((n) => n + 1);
    },

    triggerAddToCollection: () => {
      addToCollectionTrigger.update((n) => n + 1);
    },

    triggerDeleteSelected: () => {
      deleteSelectedTrigger.update((n) => n + 1);
    },

    appendFiles: (newFiles: any[], metadata: PaginationMetadata) => {
      update((state) => ({
        ...state,
        files: metadata.page === 1 ? newFiles : [...state.files, ...newFiles],
        currentPage: metadata.page,
        pageSize: metadata.pageSize,
        totalFiles: metadata.total,
        totalPages: metadata.totalPages,
        hasMoreFiles: metadata.hasMore,
      }));
    },

    resetPagination: () => {
      update((state) => ({
        ...state,
        currentPage: 0,
        totalFiles: 0,
        totalPages: 0,
        hasMoreFiles: false,
        isLoadingMore: false,
      }));
    },

    setLoadingMore: (loading: boolean) => {
      update((state) => ({ ...state, isLoadingMore: loading }));
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
export const galleryState = derived(galleryStore, ($store) => $store);
export const isGalleryPage = derived(galleryStore, ($store) => $store.activeTab === 'gallery');
export const galleryViewMode = derived(galleryStore, ($store) => $store.viewMode);
export const selectedCount = derived(galleryStore, ($store) => $store.selectedFiles.size);
export const allFilesSelected = derived(
  galleryStore,
  ($store) => $store.files.length > 0 && $store.selectedFiles.size === $store.files.length
);
export const hasMoreFiles = derived(galleryStore, ($store) => $store.hasMoreFiles);
export const isLoadingMore = derived(galleryStore, ($store) => $store.isLoadingMore);
export const galleryTotalCount = derived(galleryStore, ($store) => $store.totalFiles);
