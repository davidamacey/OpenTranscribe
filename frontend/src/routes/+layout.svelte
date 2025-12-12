<script lang="ts">
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import { page } from "$app/stores";
  import { get } from 'svelte/store';

  // Import theme styles
  import "../styles/theme.css";
  import "../styles/form-elements.css";
  import "../styles/tables.css";

  // Import auth store
  import { authStore, isAuthenticated, initAuth, authReady } from "$stores/auth";
  import { theme } from "../stores/theme";
  import { locale, t } from "../stores/locale";
  import { llmStatusStore } from "../stores/llmStatus";
  import { networkStore } from "../stores/network";

  // Import components
  import Navbar from "../components/Navbar.svelte";
  import NotificationsPanel from "../components/NotificationsPanel.svelte";
  import ToastContainer from "../components/ToastContainer.svelte";
  import UploadManager from "../components/UploadManager.svelte";
  import AppContent from "../components/AppContent.svelte";
  import SettingsModal from "../components/SettingsModal.svelte";

  // Initialize auth state when the component mounts
  onMount(async () => {
    // Initialize theme
    document.documentElement.setAttribute('data-theme', get(theme));

    // Initialize locale/i18n
    await locale.initialize();

    // Initialize network connectivity monitoring
    networkStore.initialize();

    try {
      await initAuth();

      const isAuth = get(isAuthenticated);
      const publicPaths = ["/login", "/register"];
      const currentPath = $page.url.pathname;
      const isPublicPath = publicPaths.includes(currentPath);

      if (!isAuth && !isPublicPath) {
        goto("/login", { replaceState: true });
      } else if (isAuth && isPublicPath) {
        goto("/", { replaceState: true });
      }

      // Initialize LLM status store after authentication is ready
      if (isAuth) {
        try {
          await llmStatusStore.initialize();
        } catch (error) {
          console.warn('[Layout] Failed to initialize LLM status store:', error);
        }
      }

    } catch (error) {
      console.error('Layout: onMount - Error during initAuth or subsequent logic:', error);
      const currentPath = $page.url.pathname;
      if (currentPath !== "/login" && currentPath !== "/register") {
        goto("/login", { replaceState: true });
      }
    }
  });

</script>

{#if $authReady}
  <div class="app">
    <ToastContainer />
    {#if $isAuthenticated}
      <Navbar />
      <NotificationsPanel />
      <UploadManager />
      <SettingsModal />
    {/if}

    {#if $isAuthenticated}
      <AppContent>
        <slot />
      </AppContent>
    {:else}
      <main class="content no-navbar">
        <slot />
      </main>
    {/if}
  </div>
{:else}
  <div>{$t('app.loadingApplication')}</div>
{/if}

<style>
  .app {
    display: flex;
    flex-direction: column;
    min-height: 100vh;
  }

  .content {
    flex: 1;
    padding: 1rem;
    margin-top: 60px; /* Navbar height */
  }

  .content.no-navbar {
    margin-top: 0;
  }

  @media (min-width: 768px) {
    .content {
      padding: 2rem;
    }
  }
</style>
