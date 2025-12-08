<script lang="ts">
  import { page } from '$app/stores';

  // Track if we're on the gallery page for styling
  $: isGalleryPage = $page.url.pathname === '/' || ($page.url.pathname as string) === '';
</script>

<main class="content {isGalleryPage ? 'gallery-page' : ''}">
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
