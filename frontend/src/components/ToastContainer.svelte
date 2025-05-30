<script lang="ts">
  import { toastStore } from '$stores/toast';
  import Toast from './Toast.svelte';
</script>

{#if $toastStore.length > 0}
  <div class="toast-container">
    {#each $toastStore as toast (toast.id)}
      <Toast 
        message={toast.message} 
        type={toast.type} 
        duration={0}
        on:dismiss={() => toastStore.dismiss(toast.id)}
      />
    {/each}
  </div>
{/if}

<style>
  .toast-container {
    position: fixed;
    top: 20px;
    right: 20px;
    z-index: 9999;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  
  @media (max-width: 640px) {
    .toast-container {
      left: 20px;
      right: 20px;
      align-items: center;
    }
  }
</style>