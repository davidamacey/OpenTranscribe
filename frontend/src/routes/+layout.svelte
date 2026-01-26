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
  import { authStore, isAuthenticated, initAuth, authReady, getAuthMethods } from "$stores/auth";
  import { theme } from "../stores/theme";
  import { locale } from "../stores/locale";
  import { llmStatusStore } from "../stores/llmStatus";
  import { networkStore } from "../stores/network";

  // Import components
  import Navbar from "../components/Navbar.svelte";
  import NotificationsPanel from "../components/NotificationsPanel.svelte";
  import ToastContainer from "../components/ToastContainer.svelte";
  import UploadManager from "../components/UploadManager.svelte";
  import AppContent from "../components/AppContent.svelte";
  import SettingsModal from "../components/SettingsModal.svelte";
  import ClassificationBanner from "$lib/components/ClassificationBanner.svelte";

  // Classification banner state
  let bannerEnabled = false;
  let bannerClassification: 'UNCLASSIFIED' | 'CUI' | 'FOUO' | 'CONFIDENTIAL' | 'SECRET' | 'TOP SECRET' | 'TOP SECRET//SCI' = 'UNCLASSIFIED';

  // Initialize auth state when the component mounts
  onMount(async () => {
    // Initialize theme
    document.documentElement.setAttribute('data-theme', get(theme));

    // Initialize locale/i18n
    await locale.initialize();

    // Initialize network connectivity monitoring
    networkStore.initialize();

    // Fetch auth methods to get banner settings
    try {
      const authMethods = await getAuthMethods();
      if (authMethods.login_banner_enabled) {
        bannerEnabled = true;
        bannerClassification = (authMethods.login_banner_classification as typeof bannerClassification) || 'UNCLASSIFIED';
      }
    } catch (error) {
      console.warn('[Layout] Failed to fetch auth methods for banner:', error);
    }

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
  <!-- Classification Banner (FedRAMP AC-8) - shows on all pages when enabled -->
  {#if bannerEnabled && $isAuthenticated}
    <ClassificationBanner
      classification={bannerClassification}
      position="top"
    />
  {/if}

  <div class="app" class:has-banner={bannerEnabled && $isAuthenticated} style="--banner-offset: {bannerEnabled && $isAuthenticated ? '28px' : '0px'}">
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
  <div class="loading-app">Loading...</div>
{/if}

<style>
  .app {
    display: flex;
    flex-direction: column;
    min-height: 100vh;
  }

  /* Offset for classification banner (approx 28px) */
  .app.has-banner {
    padding-top: 28px;
  }

  /* Push navbar down when banner is present */
  :global(.app.has-banner .navbar) {
    top: 28px !important;
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

  .loading-app {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 100vh;
    color: var(--text-muted, #6c757d);
    font-size: 1rem;
  }
</style>
