<script lang="ts">
  import { page } from '$app/stores';

  // Track if we're on a full-bleed page (own layout, no wrapper padding)
  $: isFullBleedPage = $page.url.pathname === '/' || ($page.url.pathname as string) === '' || $page.url.pathname === '/search';
</script>

<main class="content {isFullBleedPage ? 'gallery-page' : ''}">
  <slot />
</main>

<style>
  .content {
    padding: 1rem;
    margin-top: 60px; /* Navbar height */
  }

  /* Remove padding for gallery page - it handles its own layout */
  :global(.content.gallery-page) {
    padding: 0 !important;
  }

  @media (min-width: 768px) {
    .content {
      padding: 2rem;
    }
  }
</style>
