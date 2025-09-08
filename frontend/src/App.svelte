<script lang="ts">
  import { Router, Route, Link, navigate } from "svelte-navigator";
  import { onMount, onDestroy } from "svelte";
  import { get } from 'svelte/store';
  
  // Import theme styles
  import "./styles/theme.css";
  import "./styles/form-elements.css";
  import "./styles/tables.css";
  
  // Import auth store
  import { authStore, user, isAuthenticated, initAuth, authReady } from "$stores/auth";
  import { theme } from "./stores/theme";
  
  // Import components
  import Navbar from "./components/Navbar.svelte";
  import NotificationsPanel from "./components/NotificationsPanel.svelte";
  import ToastContainer from "./components/ToastContainer.svelte";
  
  // Import routes
  import Login from "./routes/Login.svelte";
  import Register from "./routes/Register.svelte";
  import MediaLibrary from "./routes/MediaLibrary.svelte";
  import FileDetail from "./routes/FileDetail.svelte";
  import UserSettings from "./routes/UserSettings.svelte";
  import AdminDashboard from "./routes/AdminDashboard.svelte";
  import FileStatus from "./routes/FileStatus.svelte";
  
  // Store the current path to handle redirects
  let currentPath = window.location.pathname;
  
  /**
   * Auth guard for protected routes
   * @param {any} context - The router context
   * @returns {string|null} Redirect path or null
   */
  function authGuard(context) {
    if (!get(authStore).ready) return null;
    if (!get(authStore).isAuthenticated) {
      return "/login";
    }
    return null;
  }
  
  /**
   * Admin guard for admin-only routes
   * @param {any} context - The router context
   * @returns {string|null} Redirect path or null
   */
  function adminGuard(context) {
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
      const isPublicPath = publicPaths.includes(currentPath);

      if (!isAuth && !isPublicPath) {
        navigate("/login", { replace: true });
      } else if (isAuth && isPublicPath) {
        navigate("/", { replace: true });
      }

    } catch (error) {
      console.error('App.svelte: onMount - Error during initAuth or subsequent logic:', error);
      if (currentPath !== "/login" && currentPath !== "/register") {
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
        <NotificationsPanel hideButton={true} />
      {/if}
      
      <main class="content {!$isAuthenticated ? 'no-navbar' : ''}">
        <Route path="/login" component={Login} />
        <Route path="/register" component={Register} />
        <Route path="/" condition={authGuard}>
          <MediaLibrary />
        </Route>
        <Route path="/files/:id" let:params primary={false}>
          <FileDetail id={params.id} />
        </Route>
        <Route path="/file-status" component={FileStatus} condition={authGuard} />
        <Route path="/settings" component={UserSettings} condition={authGuard} />
        <Route path="/admin" component={AdminDashboard} condition={adminGuard} />
      </main>
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
