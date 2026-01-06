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
- **i18n** - Internationalization with 7 language support

### Frontend Features

- **Responsive Design** - Works seamlessly across desktop and mobile
- **Real-time Updates** - WebSocket integration for live transcription progress
- **Dark/Light Mode** - Automatic theme switching with user preference
- **Internationalization (i18n)** - UI available in 7 languages (English, Spanish, French, German, Portuguese, Chinese, Japanese, Russian)
- **Advanced Upload System** - Floating, draggable upload manager with concurrent processing
- **Upload Progress Tracking** - Real-time progress with estimated time remaining
- **Intelligent Upload Management** - Queue control, retry logic, and duplicate detection
- **Media Player** - Custom video/audio player with transcript synchronization
- **Full-Screen Transcript View** - Dedicated modal for reading and searching long transcripts with pagination
- **Enhanced Analytics Display** - Server-computed speaker analytics with comprehensive metrics visualization
- **Smart Error Handling** - Intelligent error categorization with user-friendly suggestions
- **Optimized Data Formatting** - Server-side formatted data for consistent display of dates, durations, and file sizes
- **Advanced Speaker Management** - Consolidated speaker suggestions with profile matching, confidence scoring, and merge UI
- **Search Interface** - Full-text and semantic search capabilities
- **User Management** - Authentication, registration, and profile management with settings
- **Transcription Settings** - User-level language preferences, speaker detection, and garbage cleanup
- **Recording Settings** - User-specific audio recording preferences and quality controls
- **Collection Management** - Comprehensive file organization with drag-and-drop collection editing
- **Modal Consistency** - Unified modal design patterns with improved UX
- **Auto-Refresh Systems** - Background updates without manual refresh requirements
- **System Statistics** - CPU, memory, disk, and GPU usage display for all users

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
│   │   ├── CollectionsEditor.svelte  # Inline collection management
│   │   ├── CommentSection.svelte
│   │   ├── ConfirmationModal.svelte  # Reusable confirmation dialog
│   │   ├── FileUploader.svelte
│   │   ├── Navbar.svelte
│   │   ├── SpeakerMerge.svelte       # Speaker merge UI
│   │   ├── TranscriptDisplay.svelte
│   │   ├── TranscriptModal.svelte    # Full-screen transcript viewer
│   │   ├── UploadManager.svelte      # Floating upload manager
│   │   ├── UploadProgress.svelte     # Individual upload progress
│   │   ├── VideoPlayer.svelte
│   │   ├── settings/                 # Settings-related components
│   │   │   ├── LanguageSettings.svelte      # UI language selection
│   │   │   ├── TranscriptionSettings.svelte # Transcription preferences
│   │   │   └── ...
│   │   └── ...                # More components
│   ├── routes/                # Page components
│   │   ├── AdminDashboard.svelte
│   │   ├── FileDetail.svelte
│   │   ├── Login.svelte
│   │   ├── MediaLibrary.svelte
│   │   └── ...                # More routes
│   ├── stores/                # Svelte stores for state management
│   │   ├── auth.ts           # Authentication state
│   │   ├── locale.ts         # Language/locale management
│   │   ├── notifications.ts   # Notification system
│   │   ├── recording.ts      # Recording state management
│   │   ├── theme.js          # Theme management
│   │   ├── uploads.ts        # Upload queue management
│   │   └── websocket.ts      # WebSocket connection
│   ├── lib/                  # Utilities and services
│   │   ├── api/              # API service modules
│   │   │   ├── userSettings.ts       # User settings API client
│   │   │   ├── transcriptionSettings.ts  # Transcription settings types
│   │   │   └── ...
│   │   ├── i18n/             # Internationalization system
│   │   │   ├── index.ts      # i18n initialization and exports
│   │   │   ├── languages.ts  # Language definitions
│   │   │   └── locales/      # Translation files
│   │   │       ├── en.json   # English (default)
│   │   │       ├── es.json   # Spanish
│   │   │       ├── fr.json   # French
│   │   │       ├── de.json   # German
│   │   │       ├── pt.json   # Portuguese
│   │   │       ├── zh.json   # Chinese
│   │   │       └── ja.json   # Japanese
│   │   ├── services/         # Business logic services
│   │   │   └── uploadService.ts # Upload management service
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
- **`UploadManager.svelte`** - **NEW**: Floating, draggable upload manager with real-time progress
- **`UploadProgress.svelte`** - **NEW**: Individual upload progress tracking with retry/cancel
- **`FileHeader.svelte`** - File metadata and action buttons
- **`DownloadButton.svelte`** - Export and download options

#### Media & Transcription

- **`VideoPlayer.svelte`** - Custom media player with transcript sync
- **`TranscriptDisplay.svelte`** - Interactive transcript with speaker labels
- **`TranscriptModal.svelte`** - **NEW**: Full-screen transcript viewer with search functionality
- **`SpeakerEditor.svelte`** - Speaker management and editing
- **`MetadataDisplay.svelte`** - File information and statistics

#### Search & Filtering

- **`FilterSidebar.svelte`** - Advanced search and filtering options
- **`TagsEditor.svelte`** - Tag management interface
- **`TagsSection.svelte`** - Tag display and interaction
- **`CollectionsEditor.svelte`** - **NEW**: Inline collection management with drag-and-drop
- **`CollectionsPanel.svelte`** - Collection organization interface

#### Analytics & Insights

- **`AnalyticsSection.svelte`** - Transcript analytics and statistics
- **`SpeakerStats.svelte`** - Speaker-specific analytics
- **`CommentSection.svelte`** - Time-stamped comments and annotations

#### Administration

- **`UserManagementTable.svelte`** - Admin user management interface
- **`ApiDebugger.svelte`** - Development API testing tool
- **`ConfirmationModal.svelte`** - **NEW**: Reusable confirmation dialog for destructive actions

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
export const isAuthenticated = derived(user, ($user) => !!$user);
export const isAdmin = derived(user, ($user) => $user?.is_superuser || false);
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

#### Locale Store (`stores/locale.ts`)

```typescript
// Internationalization with persistent language preference
export const locale = writable<string>('en');
export const SUPPORTED_LANGUAGES = [
  { code: 'en', name: 'English', nativeName: 'English' },
  { code: 'es', name: 'Spanish', nativeName: 'Español' },
  { code: 'fr', name: 'French', nativeName: 'Français' },
  { code: 'de', name: 'German', nativeName: 'Deutsch' },
  { code: 'pt', name: 'Portuguese', nativeName: 'Português' },
  { code: 'zh', name: 'Chinese', nativeName: '中文' },
  { code: 'ja', name: 'Japanese', nativeName: '日本語' },
  { code: "ru", name: 'Russian', nativeName: 'Русский' },
];
export const t = derived(locale, ...); // Translation function
```

## 🌐 Internationalization (i18n)

### Overview

OpenTranscribe frontend supports 8 languages with a simple, efficient i18n system.

### Supported Languages

- **English** (en) - Default
- **Spanish** (es) - Español
- **French** (fr) - Français
- **German** (de) - Deutsch
- **Portuguese** (pt) - Português
- **Chinese** (zh) - 中文
- **Japanese** (ja) - 日本語
- **Russian** (ru) - Русский

### Usage in Components

```svelte
<script>
  import { t } from '$stores/locale';
</script>

<h1>{$t('common.title')}</h1>
<button>{$t('actions.save')}</button>
```

### Translation Files

Translation files are JSON format located in `src/lib/i18n/locales/`:

```json
{
  "common": {
    "title": "OpenTranscribe",
    "loading": "Loading..."
  },
  "actions": {
    "save": "Save",
    "cancel": "Cancel"
  }
}
```

### Adding New Languages

1. Create new translation file in `src/lib/i18n/locales/` (e.g., `ko.json`)
2. Add language definition to `src/lib/i18n/languages.ts`
3. Import and register in `src/lib/i18n/index.ts`

### Language Persistence

User language preference is stored in localStorage and restored on page load.

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

@media (min-width: 768px) {
  /* Tablet */
}
@media (min-width: 1024px) {
  /* Desktop */
}
@media (min-width: 1280px) {
  /* Large desktop */
}
```

## 🌐 API Integration

### HTTP Client (`lib/axios.ts`)

```typescript
// Configured Axios instance with authentication
const api = axios.create({
  baseURL: "/api",
  timeout: 10000,
});

// Request interceptor for authentication
api.interceptors.request.use((config) => {
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
    taskUpdates.update((updates) => [...updates, update]);
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
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/service-worker.js");
}

// Install prompt
window.addEventListener("beforeinstallprompt", (e) => {
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

- **TypeScript** - Strict type checking enabled with comprehensive ESLint integration
- **ESLint** - Code linting with Svelte-specific rules and TypeScript support
- **Prettier** - Consistent code formatting
- **Svelte Check** - Svelte-specific type checking

### Enhanced Development Features

- **ESLint Integration** - Comprehensive linting with TypeScript and Svelte plugins
- **Type Safety Improvements** - Reduced TypeScript errors with proper parameter typing
- **Code Quality Tooling** - Automated formatting and error detection
- **Performance Optimizations** - Improved component reactivity and reduced re-renders
- **Server-Side Integration** - Enhanced API integration with formatted data and intelligent error handling
- **Advanced Component Architecture** - Consolidated UI patterns with reusable confirmation modals and status management
- **Optimized Data Flow** - Reduced frontend processing through server-side computation and formatting

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
VITE_API_BASE_URL=http://localhost:5174/api
VITE_WS_URL=ws://localhost:5174/ws

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
      "/api": "http://localhost:5174",
      "/ws": {
        target: "ws://localhost:5174",
        ws: true,
      },
    },
  },
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
