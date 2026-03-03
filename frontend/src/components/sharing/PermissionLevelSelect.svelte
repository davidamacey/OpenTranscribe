<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { t } from '$stores/locale';
  import type { PermissionLevel } from '$lib/types/groups';

  export let value: PermissionLevel = 'viewer';
  export let disabled: boolean = false;

  const dispatch = createEventDispatcher();

  const options: { value: PermissionLevel; labelKey: string; descKey: string }[] = [
    { value: 'viewer', labelKey: 'sharing.permissionViewer', descKey: 'sharing.permissionViewerDesc' },
    { value: 'editor', labelKey: 'sharing.permissionEditor', descKey: 'sharing.permissionEditorDesc' },
  ];

  function handleChange(event: Event) {
    const target = event.target as HTMLSelectElement;
    const newValue = target.value as PermissionLevel;
    value = newValue;
    dispatch('change', newValue);
  }
</script>

<select
  class="permission-select"
  {disabled}
  {value}
  on:change={handleChange}
  title={$t(options.find(o => o.value === value)?.descKey || '')}
>
  {#each options as option}
    <option value={option.value} title={$t(option.descKey)}>
      {$t(option.labelKey)}
    </option>
  {/each}
</select>

<style>
  .permission-select {
    padding: 0.35rem 0.5rem;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    background-color: var(--input-bg, var(--background-color));
    color: var(--text-color);
    font-size: 0.8rem;
    cursor: pointer;
    transition: border-color 0.2s ease;
    min-width: 90px;
  }

  .permission-select:hover:not(:disabled) {
    border-color: var(--primary-color);
  }

  .permission-select:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.15);
  }

  .permission-select:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  :global([data-theme='dark']) .permission-select {
    background-color: rgba(255, 255, 255, 0.05);
  }
</style>
