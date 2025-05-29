<div align="center">
  <img src="../assets/logo-banner.png" alt="OpenTranscribe Logo" width="400">
  
  # Frontend
</div>

A modern Svelte-based frontend for the OpenTranscribe AI-powered transcription application.

## 🚀 Quick Start

### Prerequisites
- Node.js (v18 or higher)
- npm or yarn package manager
- Docker and Docker Compose (for full stack development)

### Development Setup

1. **Using OpenTranscribe utility script** (recommended):
   ```bash
   # From project root
   ./opentr.sh start dev
   ```
   This starts the complete stack including frontend with hot module replacement.

2. **Standalone frontend development**:
   ```bash
   cd frontend/
   npm install
   npm run dev
   ```

### Frontend Access
- **Development**: http://localhost:5173 (with hot reload)
- **Production**: http://localhost:5173 (optimized build via NGINX)

## 🏗️ Architecture Overview

### Core Technologies
- **Svelte** - Reactive frontend framework with excellent performance
- **TypeScript** - Type-safe JavaScript development
- **Vite** - Fast build tool with hot module replacement
- **CSS3** - Modern styling with CSS Grid and Flexbox
- **Progressive Web App** - Service worker for offline capabilities

### Frontend Features
- **Responsive Design** - Works seamlessly across desktop and mobile
- **Real-time Updates** - WebSocket integration for live transcription progress
- **Dark/Light Mode** - Automatic theme switching with user preference
- **File Upload** - Drag-and-drop file upload with progress tracking
- **Media Player** - Custom video/audio player with transcript synchronization
- **Search Interface** - Full-text and semantic search capabilities
- **User Management** - Authentication, registration, and profile management

## 📁 Directory Structure

```
frontend/
├── public/                     # Static assets
│   ├── fonts/                 # Web fonts (Poppins)
│   ├── icons/                 # PWA icons
│   └── images/                # Static images
├── src/                       # Source code
│   ├── components/            # Reusable UI components
│   │   ├── AnalyticsSection.svelte
│   │   ├── CommentSection.svelte
│   │   ├── FileUploader.svelte
│   │   ├── Navbar.svelte
│   │   ├── TranscriptDisplay.svelte
│   │   ├── VideoPlayer.svelte
│   │   └── ...                # More components
│   ├── routes/                # Page components
│   │   ├── AdminDashboard.svelte
│   │   ├── FileDetail.svelte
│   │   ├── Login.svelte
│   │   ├── MediaLibrary.svelte
│   │   └── ...                # More routes
│   ├── stores/                # Svelte stores for state management
│   │   ├── auth.ts           # Authentication state
│   │   ├── notifications.ts   # Notification system
│   │   ├── theme.js          # Theme management
│   │   └── websocket.ts      # WebSocket connection
│   ├── lib/                  # Utilities and services
│   │   ├── axios.ts          # HTTP client configuration
│   │   ├── websocket.js      # WebSocket service
│   │   └── utils/            # Helper functions
│   ├── styles/               # Global styles
│   │   ├── theme.css         # CSS variables and themes
│   │   ├── form-elements.css # Form styling
│   │   └── tables.css        # Table styling
│   ├── App.svelte           # Main application component
│   └── main.ts              # Application entry point
├── Dockerfile.dev           # Development container
├── Dockerfile.prod          # Production container with NGINX
├── package.json             # Dependencies and scripts
├── tsconfig.json           # TypeScript configuration
├── vite.config.ts          # Vite build configuration
└── README.md               # This file
```

## 🧩 Component Architecture

### Core Components

#### Navigation & Layout
- **`Navbar.svelte`** - Main navigation with user menu and theme toggle
- **`ThemeToggle.svelte`** - Dark/light mode switcher
- **`NotificationsPanel.svelte`** - Real-time notification display

#### File Management
- **`FileUploader.svelte`** - Drag-and-drop file upload with progress
- **`FileHeader.svelte`** - File metadata and action buttons
- **`DownloadButton.svelte`** - Export and download options

#### Media & Transcription
- **`VideoPlayer.svelte`** - Custom media player with transcript sync
- **`TranscriptDisplay.svelte`** - Interactive transcript with speaker labels
- **`SpeakerEditor.svelte`** - Speaker management and editing
- **`MetadataDisplay.svelte`** - File information and statistics

#### Search & Filtering
- **`FilterSidebar.svelte`** - Advanced search and filtering options
- **`TagsEditor.svelte`** - Tag management interface
- **`TagsSection.svelte`** - Tag display and interaction

#### Analytics & Insights
- **`AnalyticsSection.svelte`** - Transcript analytics and statistics
- **`SpeakerStats.svelte`** - Speaker-specific analytics
- **`CommentSection.svelte`** - Time-stamped comments and annotations

#### Administration
- **`UserManagementTable.svelte`** - Admin user management interface
- **`ApiDebugger.svelte`** - Development API testing tool

### Page Components

#### User Pages
- **`Login.svelte`** - Authentication page with registration link
- **`Register.svelte`** - User registration form
- **`UserSettings.svelte`** - User profile and preferences
- **`MediaLibrary.svelte`** - Main file library with search and filtering

#### Content Pages
- **`FileDetail.svelte`** - Detailed file view with transcript and analytics
- **`Tasks.svelte`** - Background task monitoring and history

#### Admin Pages
- **`AdminDashboard.svelte`** - System administration interface

## 🔄 State Management

### Svelte Stores

#### Authentication Store (`stores/auth.ts`)
```typescript
// User authentication and session management
export const user = writable<User | null>(null);
export const isAuthenticated = derived(user, $user => !!$user);
export const isAdmin = derived(user, $user => $user?.is_superuser || false);
```

#### Theme Store (`stores/theme.js`)
```javascript
// Dark/light mode management with system preference detection
export const theme = writable('auto'); // 'light', 'dark', 'auto'
export const isDarkMode = derived(theme, ...);
```

#### Notifications Store (`stores/notifications.ts`)
```typescript
// Toast notifications and alerts
export const notifications = writable<Notification[]>([]);
export function addNotification(notification: Notification) { ... }
```

#### WebSocket Store (`stores/websocket.ts`)
```typescript
// Real-time communication for transcription progress
export const wsConnection = writable<WebSocket | null>(null);
export const taskUpdates = writable<TaskUpdate[]>([]);
```

## 🎨 Styling Architecture

### CSS Strategy
- **CSS Variables** - Theme-aware custom properties in `styles/theme.css`
- **Component Scoping** - Svelte's built-in style scoping
- **Global Styles** - Shared styles in `styles/` directory
- **Responsive Design** - Mobile-first approach with CSS Grid/Flexbox

### Theme System
```css
/* Light theme */
:root {
  --primary-color: #2563eb;
  --background-color: #ffffff;
  --text-color: #1f2937;
  --border-color: #e5e7eb;
}

/* Dark theme */
[data-theme="dark"] {
  --primary-color: #3b82f6;
  --background-color: #111827;
  --text-color: #f9fafb;
  --border-color: #374151;
}
```

### Responsive Breakpoints
```css
/* Mobile-first responsive design */
.container {
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 1rem;
}

@media (min-width: 768px) { /* Tablet */ }
@media (min-width: 1024px) { /* Desktop */ }
@media (min-width: 1280px) { /* Large desktop */ }
```

## 🌐 API Integration

### HTTP Client (`lib/axios.ts`)
```typescript
// Configured Axios instance with authentication
const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
});

// Request interceptor for authentication
api.interceptors.request.use(config => {
  const token = getAuthToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});
```

### WebSocket Integration (`lib/websocket.js`)
```javascript
// Real-time updates for transcription progress
export function connectWebSocket() {
  const ws = new WebSocket(`ws://${window.location.host}/ws`);
  
  ws.onmessage = (event) => {
    const update = JSON.parse(event.data);
    taskUpdates.update(updates => [...updates, update]);
  };
}
```

## 📱 Progressive Web App

### Service Worker
- **Offline Capability** - Cache critical resources for offline access
- **Background Sync** - Queue uploads when offline
- **Push Notifications** - Task completion notifications
- **Auto-update** - Seamless app updates

### PWA Features
```typescript
// Service worker registration
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/service-worker.js');
}

// Install prompt
window.addEventListener('beforeinstallprompt', (e) => {
  // Show custom install prompt
});
```

## 🧪 Development Workflow

### Available Scripts
```bash
# Development server with hot reload
npm run dev

# Production build
npm run build

# Preview production build
npm run preview

# Type checking
npm run check

# Linting
npm run lint

# Format code
npm run format
```

### Code Style
- **TypeScript** - Strict type checking enabled
- **ESLint** - Code linting with Svelte-specific rules
- **Prettier** - Consistent code formatting
- **Svelte Check** - Svelte-specific type checking

### Development Guidelines
1. **Component Naming** - PascalCase for component files
2. **Store Organization** - Group related state in focused stores
3. **Type Safety** - Use TypeScript interfaces for all data structures
4. **Accessibility** - Follow WCAG guidelines for all components
5. **Performance** - Lazy load components and optimize bundle size

## 🚀 Build & Deployment

### Development Build
```bash
# Start development server
npm run dev

# Development features:
# - Hot module replacement
# - Source maps
# - Debug logging
# - API proxy to backend
```

### Production Build
```bash
# Create optimized production build
npm run build

# Production optimizations:
# - Code minification
# - Tree shaking
# - Asset optimization
# - Service worker generation
```

### Docker Deployment

#### Development Container
```bash
# Build and run development container
docker build -f Dockerfile.dev -t opentranscribe-frontend:dev .
docker run -p 5173:5173 -v $(pwd):/app opentranscribe-frontend:dev
```

#### Production Container
```bash
# Build and run production container with NGINX
docker build -f Dockerfile.prod -t opentranscribe-frontend:prod .
docker run -p 5173:80 opentranscribe-frontend:prod
```

## 🔧 Configuration

### Environment Variables
```bash
# API configuration
VITE_API_BASE_URL=http://localhost:8080/api
VITE_WS_URL=ws://localhost:8080/ws

# Feature flags
VITE_ENABLE_DEBUG=true
VITE_ENABLE_PWA=true

# Analytics
VITE_ANALYTICS_ID=your-analytics-id
```

### Vite Configuration (`vite.config.ts`)
```typescript
export default defineConfig({
  plugins: [sveltekit()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8080',
      '/ws': {
        target: 'ws://localhost:8080',
        ws: true
      }
    }
  }
});
```

## 🧪 Testing

### Test Structure
```
src/tests/
├── components/          # Component unit tests
├── stores/             # Store tests
├── utils/              # Utility function tests
└── integration/        # End-to-end tests
```

### Testing Tools
- **Vitest** - Unit testing framework
- **@testing-library/svelte** - Component testing utilities
- **Playwright** - End-to-end testing
- **MSW** - API mocking for tests

### Running Tests
```bash
# Unit tests
npm run test

# Component tests
npm run test:components

# E2E tests
npm run test:e2e

# Test coverage
npm run test:coverage
```

## 🐛 Troubleshooting

### Common Issues

#### Development Server Issues
```bash
# Clear node_modules and reinstall
rm -rf node_modules package-lock.json
npm install

# Clear Vite cache
rm -rf .vite
npm run dev
```

#### Build Issues
```bash
# Type checking errors
npm run check

# Linting errors
npm run lint --fix

# Clean build
rm -rf dist
npm run build
```

#### WebSocket Connection Issues
- Check backend WebSocket endpoint is running
- Verify CORS configuration allows WebSocket connections
- Check browser developer tools for connection errors

### Performance Optimization
- **Bundle Analysis** - Use `npm run build -- --analyze`
- **Lighthouse Audit** - Regular performance audits
- **Image Optimization** - Use WebP format when possible
- **Code Splitting** - Lazy load non-critical components

## 📚 Resources

### Documentation
- [Svelte Documentation](https://svelte.dev/docs)
- [Vite Documentation](https://vitejs.dev/guide/)
- [TypeScript Documentation](https://www.typescriptlang.org/docs/)

### Development Tools
- [Svelte DevTools](https://github.com/RedHatter/svelte-devtools)
- [Vite DevTools](https://github.com/webfansplz/vite-plugin-vue-devtools)
- [Chrome DevTools](https://developers.google.com/web/tools/chrome-devtools)

---

**Built with ❤️ using Svelte, TypeScript, and modern web technologies.**