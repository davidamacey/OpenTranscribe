import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

// This runs in Node.js - Don't use client-side code here (browser APIs, JSX...)

/**
 * Creating a sidebar enables you to:
 - create an ordered group of docs
 - render a sidebar for each doc of that group
 - provide next/previous navigation

 The sidebars can be generated from the filesystem, or explicitly defined here.

 Create as many sidebars as you want.
 */
const sidebars: SidebarsConfig = {
  // Main documentation sidebar
  docsSidebar: [
    {
      type: 'category',
      label: 'Getting Started',
      items: [
        'getting-started/introduction',
        'getting-started/quick-start',
        'getting-started/first-transcription',
      ],
    },
    {
      type: 'category',
      label: 'Installation',
      items: [
        'installation/docker-compose',
        'installation/hardware-requirements',
        'installation/gpu-setup',
        'installation/model-cache',
        'installation/huggingface-setup',
        'installation/offline-installation',
        'installation/troubleshooting',
      ],
    },
    {
      type: 'category',
      label: 'User Guide',
      items: [
        'user-guide/uploading-files',
        'user-guide/recording-audio',
        'user-guide/managing-transcriptions',
        'user-guide/speaker-management',
        'user-guide/ai-summarization',
        'user-guide/search-and-filters',
        'user-guide/collections',
        'user-guide/export-options',
      ],
    },
    {
      type: 'category',
      label: 'Features',
      items: [
        'features/transcription',
        'features/speaker-diarization',
        'features/llm-integration',
        'features/search',
        'features/analytics',
        'features/pwa',
      ],
    },
    {
      type: 'category',
      label: 'Configuration',
      items: [
        'configuration/environment-variables',
        'configuration/multi-gpu-scaling',
        'configuration/llm-providers',
        'configuration/security',
      ],
    },
    {
      type: 'category',
      label: 'Developer Guide',
      items: [
        'developer-guide/architecture',
        'developer-guide/backend-development',
        'developer-guide/frontend-development',
        'developer-guide/testing',
        'developer-guide/contributing',
        'developer-guide/code-style',
      ],
    },
    {
      type: 'category',
      label: 'Deployment',
      items: [
        'deployment/production',
        'deployment/docker-build',
        'deployment/reverse-proxy',
        'deployment/monitoring',
        'deployment/backup-restore',
      ],
    },
    {
      type: 'category',
      label: 'Use Cases',
      items: [
        'use-cases/meetings',
        'use-cases/interviews',
        'use-cases/podcasts',
        'use-cases/lectures',
      ],
    },
    'faq',
  ],

  // API Reference sidebar
  apiSidebar: [
    {
      type: 'category',
      label: 'API Reference',
      items: [
        'api/authentication',
        'api/files',
        'api/transcriptions',
        'api/speakers',
        'api/summaries',
        'api/search',
        'api/websockets',
      ],
    },
  ],
};

export default sidebars;
