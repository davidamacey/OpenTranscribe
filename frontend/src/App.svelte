<script>
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
  
  // Import routes
  import Login from "./routes/Login.svelte";
  import Register from "./routes/Register.svelte";
  import MediaLibrary from "./routes/MediaLibrary.svelte";
  import FileDetail from "./routes/FileDetail.svelte";
  import UserSettings from "./routes/UserSettings.svelte";
  import AdminDashboard from "./routes/AdminDashboard.svelte";
  import Tasks from "./routes/Tasks.svelte";
  
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
    console.log('App.svelte: onMount - Initializing authentication');
    
    // Initialize theme
    document.documentElement.setAttribute('data-theme', get(theme));
    
    try {
      await initAuth();
      console.log('App.svelte: onMount - initAuth completed. Auth state:', get(authStore));

      const isAuth = get(isAuthenticated);
      const publicPaths = ["/login", "/register"];
      const isPublicPath = publicPaths.includes(currentPath);

      if (!isAuth && !isPublicPath) {
        console.log('App.svelte: onMount - Not authenticated and not on public path, redirecting to login');
        navigate("/login", { replace: true });
      } else if (isAuth && isPublicPath) {
        console.log('App.svelte: onMount - Authenticated and on public/login path, redirecting to home');
        navigate("/", { replace: true });
      } else {
        console.log('App.svelte: onMount - Authentication check complete, no redirect needed.');
      }

    } catch (error) {
      console.error('App.svelte: onMount - Error during initAuth or subsequent logic:', error);
      if (currentPath !== "/login" && currentPath !== "/register") {
        console.log('App.svelte: onMount - Redirecting to login due to initialization error');
        navigate("/login", { replace: true });
      }
    }
  });

</script>

{#if $authReady} 
  <Router>
    <div class="app">
      {#if $isAuthenticated}
        <Navbar />
        <NotificationsPanel hideButton={true} />
      {/if}
      
      <main class="content {!$isAuthenticated ? 'no-navbar' : ''}">
        <Route path="/login" component={Login} />
        <Route path="/register" component={Register} />
        <Route path="/" component={MediaLibrary} condition={authGuard} />
        <Route path="/files/:id" let:params primary={false}>
          <FileDetail id={params.id} />
        </Route>
        <Route path="/tasks" component={Tasks} condition={authGuard} />
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
