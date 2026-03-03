import { writable } from 'svelte/store';
import type { Share, SharedCollection, PermissionLevel } from '$lib/types/groups';

interface SharingState {
  currentCollectionShares: Share[];
  sharedCollections: SharedCollection[];
  loadingShares: boolean;
  loadingSharedCollections: boolean;
  error: string | null;
}

const initialState: SharingState = {
  currentCollectionShares: [],
  sharedCollections: [],
  loadingShares: false,
  loadingSharedCollections: false,
  error: null,
};

function createSharingStore() {
  const store = writable<SharingState>(initialState);

  return {
    ...store,
    setCurrentShares: (shares: Share[]) =>
      store.update((s) => ({ ...s, currentCollectionShares: shares, loadingShares: false })),
    addShare: (share: Share) =>
      store.update((s) => ({
        ...s,
        currentCollectionShares: [...s.currentCollectionShares, share],
      })),
    removeShare: (uuid: string) =>
      store.update((s) => ({
        ...s,
        currentCollectionShares: s.currentCollectionShares.filter((sh) => sh.uuid !== uuid),
      })),
    updateSharePermission: (uuid: string, permission: PermissionLevel) =>
      store.update((s) => ({
        ...s,
        currentCollectionShares: s.currentCollectionShares.map((sh) =>
          sh.uuid === uuid ? { ...sh, permission } : sh
        ),
      })),
    setSharedCollections: (collections: SharedCollection[]) =>
      store.update((s) => ({
        ...s,
        sharedCollections: collections,
        loadingSharedCollections: false,
      })),
    setLoadingShares: (loading: boolean) => store.update((s) => ({ ...s, loadingShares: loading })),
    setLoadingSharedCollections: (loading: boolean) =>
      store.update((s) => ({ ...s, loadingSharedCollections: loading })),
    setError: (error: string | null) => store.update((s) => ({ ...s, error })),
    reset: () => store.set(initialState),
  };
}

export const sharingStore = createSharingStore();
