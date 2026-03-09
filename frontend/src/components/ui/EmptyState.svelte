<script lang="ts">
  export let icon: string = '';
  export let title: string = '';
  export let description: string = '';
  export let padding: string = '48px 24px';
</script>

<div class="empty-state" style="padding: {padding}">
  {#if $$slots.icon}
    <div class="empty-icon"><slot name="icon" /></div>
  {:else if icon}
    <div class="empty-icon">{icon}</div>
  {/if}
  {#if title}
    <h3 class="empty-title">{title}</h3>
  {/if}
  {#if description}
    <p class="empty-description">{description}</p>
  {/if}
  <slot />
</div>

<style>
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
  }

  .empty-icon {
    font-size: 2.5rem;
    line-height: 1;
    margin-bottom: 12px;
    color: var(--text-secondary);
    opacity: 0.5;
  }

  .empty-title {
    margin: 0 0 6px 0;
    font-size: 15px;
    font-weight: 600;
    color: var(--text-color);
  }

  .empty-description {
    margin: 0;
    font-size: 13px;
    color: var(--text-secondary);
    max-width: 360px;
    line-height: 1.5;
  }
</style>
