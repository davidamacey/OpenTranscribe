import { writable, derived } from 'svelte/store';
import type { Group, GroupDetail } from '$lib/types/groups';

interface GroupsState {
  groups: Group[];
  selectedGroup: GroupDetail | null;
  loading: boolean;
  error: string | null;
}

const initialState: GroupsState = {
  groups: [],
  selectedGroup: null,
  loading: false,
  error: null,
};

function createGroupsStore() {
  const store = writable<GroupsState>(initialState);

  return {
    ...store,
    setGroups: (groups: Group[]) =>
      store.update((s) => ({ ...s, groups, loading: false, error: null })),
    addGroup: (group: Group) => store.update((s) => ({ ...s, groups: [...s.groups, group] })),
    removeGroup: (uuid: string) =>
      store.update((s) => ({
        ...s,
        groups: s.groups.filter((g) => g.uuid !== uuid),
      })),
    updateGroup: (uuid: string, updates: Partial<Group>) =>
      store.update((s) => ({
        ...s,
        groups: s.groups.map((g) => (g.uuid === uuid ? { ...g, ...updates } : g)),
      })),
    setSelectedGroup: (group: GroupDetail | null) =>
      store.update((s) => ({ ...s, selectedGroup: group })),
    setLoading: (loading: boolean) => store.update((s) => ({ ...s, loading })),
    setError: (error: string | null) => store.update((s) => ({ ...s, error, loading: false })),
    reset: () => store.set(initialState),
  };
}

export const groupsStore = createGroupsStore();

// Derived stores
export const myGroups = derived(groupsStore, ($store) =>
  $store.groups.filter((g) => g.my_role === 'owner')
);
export const memberGroups = derived(groupsStore, ($store) =>
  $store.groups.filter((g) => g.my_role !== 'owner')
);
