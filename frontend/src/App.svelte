<script lang="ts">
  import { Router, Route, navigate } from "svelte-navigator";
  import { onMount } from "svelte";
  import { get } from 'svelte/store';
  
  // Import theme styles
  import "./styles/theme.css";
  import "./styles/form-elements.css";
  import "./styles/tables.css";
  
  // Import auth store
  import { authStore, isAuthenticated, initAuth, authReady } from "$stores/auth";
  import { theme } from "./stores/theme";
  
  // Import components
  import Navbar from "./components/Navbar.svelte";
  import NotificationsPanel from "./components/NotificationsPanel.svelte";
  import ToastContainer from "./components/ToastContainer.svelte";
  import UploadManager from "./components/UploadManager.svelte";
  
  // Import routes
  import Login from "./routes/Login.svelte";
  import Register from "./routes/Register.svelte";
  import MediaLibrary from "./routes/MediaLibrary.svelte";
  import FileDetail from "./routes/FileDetail.svelte";
  import UserSettings from "./routes/UserSettings.svelte";
  import AdminDashboard from "./routes/AdminDashboard.svelte";
  import FileStatus from "./routes/FileStatus.svelte";
  import AppContent from "./components/AppContent.svelte";

  
  /**
   * Auth guard for protected routes
   */
  function authGuard(_context: any): string | null {
    if (!get(authStore).ready) return null;
    if (!get(authStore).isAuthenticated) {
      return "/login";
    }
    return null;
  }
  
  /**
   * Admin guard for admin-only routes
   */
  function adminGuard(_context: any): string | null {
    if (!get(authStore).ready) return null;
    const currentAuth = get(authStore);
    if (!currentAuth.isAuthenticated) {
      return "/login";
    } else if (currentAuth.user && currentAuth.user.role !== "admin") {
      return "/";
    }
    return null;
  }
  
  // Initialize auth state when the component mounts
  onMount(async () => {
    // Initialize theme
    document.documentElement.setAttribute('data-theme', get(theme));
    
    try {
      await initAuth();

      const isAuth = get(isAuthenticated);
      const publicPaths = ["/login", "/register"];
      const isPublicPath = publicPaths.includes(window.location.pathname);

      if (!isAuth && !isPublicPath) {
        navigate("/login", { replace: true });
      } else if (isAuth && isPublicPath) {
        navigate("/", { replace: true });
      }

    } catch (error) {
      console.error('App.svelte: onMount - Error during initAuth or subsequent logic:', error);
      if (window.location.pathname !== "/login" && window.location.pathname !== "/register") {
        navigate("/login", { replace: true });
      }
    }
  });

</script>

{#if $authReady} 
  <Router>
    <div class="app">
      <ToastContainer />
      {#if $isAuthenticated}
        <Navbar />
        <NotificationsPanel />
        <UploadManager />
      {/if}

      {#if $isAuthenticated}
        <AppContent>
          <Route path="/" condition={authGuard}>
            <MediaLibrary />
          </Route>
          <Route path="/files/:id" let:params primary={false}>
            <FileDetail id={params.id} />
          </Route>
          <Route path="/file-status" component={FileStatus} condition={authGuard} />
          <Route path="/settings" component={UserSettings} condition={authGuard} />
          <Route path="/admin" component={AdminDashboard} condition={adminGuard} />
        </AppContent>
      {:else}
        <main class="content no-navbar">
          <Route path="/login" component={Login} />
          <Route path="/register" component={Register} />
        </main>
      {/if}
    </div>
  </Router>
{:else}
  <div>Loading application...</div> 
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
