import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

// This runs in Node.js - Don't use client-side code here (browser APIs, JSX...)

const config: Config = {
  title: 'OpenTranscribe',
  tagline: 'AI-Powered Transcription and Media Analysis Platform',
  favicon: 'img/favicon.ico',

  // Future flags, see https://docusaurus.io/docs/api/docusaurus-config#future
  future: {
    v4: true, // Improve compatibility with the upcoming Docusaurus v4
  },

  // Set the production url of your site here
  url: 'https://docs.opentranscribe.io',
  // Set the /<baseUrl>/ pathname under which your site is served
  // For GitHub pages deployment, it is often '/<projectName>/'
  baseUrl: '/',

  // GitHub pages deployment config.
  // If you aren't using GitHub pages, you don't need these.
  organizationName: 'davidamacey', // Usually your GitHub org/user name.
  projectName: 'OpenTranscribe', // Usually your repo name.

  onBrokenLinks: 'warn', // Changed from 'throw' to allow build with broken links during development

  // Even if you don't use internationalization, you can use this field to set
  // useful metadata like html lang. For example, if your site is Chinese, you
  // may want to replace "en" with "zh-Hans".
  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          // Please change this to your repo.
          // Remove this to remove the "edit this page" links.
          editUrl:
            'https://github.com/davidamacey/OpenTranscribe/tree/master/docs-site/',
        },
        blog: {
          showReadingTime: true,
          feedOptions: {
            type: ['rss', 'atom'],
            xslt: true,
          },
          // Please change this to your repo.
          // Remove this to remove the "edit this page" links.
          editUrl:
            'https://github.com/davidamacey/OpenTranscribe/tree/master/docs-site/',
          // Useful options to enforce blogging best practices
          onInlineTags: 'warn',
          onInlineAuthors: 'warn',
          onUntruncatedBlogPosts: 'warn',
        },
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    // Replace with your project's social card
    image: 'img/opentranscribe-social-card.png',
    colorMode: {
      defaultMode: 'dark',
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: 'OpenTranscribe',
      logo: {
        alt: 'OpenTranscribe Logo',
        src: 'img/logo.png',
        srcDark: 'img/logo-dark.png',
      },
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'docsSidebar',
          position: 'left',
          label: 'Docs',
        },
        // TODO: Uncomment when API pages are created
        // {
        //   type: 'docSidebar',
        //   sidebarId: 'apiSidebar',
        //   position: 'left',
        //   label: 'API Reference',
        // },
        {to: '/blog', label: 'Blog', position: 'left'},
        {
          href: 'https://github.com/davidamacey/OpenTranscribe',
          label: 'GitHub',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Documentation',
          items: [
            {
              label: 'Getting Started',
              to: '/docs/getting-started/introduction',
            },
            {
              label: 'Installation',
              to: '/docs/installation/docker-compose',
            },
            {
              label: 'FAQ',
              to: '/docs/faq',
            },
            // TODO: Add when pages are created
            // {
            //   label: 'User Guide',
            //   to: '/docs/user-guide/uploading-files',
            // },
            // {
            //   label: 'API Reference',
            //   to: '/docs/api/authentication',
            // },
          ],
        },
        {
          title: 'Community',
          items: [
            {
              label: 'GitHub Discussions',
              href: 'https://github.com/davidamacey/OpenTranscribe/discussions',
            },
            {
              label: 'GitHub Issues',
              href: 'https://github.com/davidamacey/OpenTranscribe/issues',
            },
            {
              label: 'GitHub Repository',
              href: 'https://github.com/davidamacey/OpenTranscribe',
            },
            // TODO: Add when page is created
            // {
            //   label: 'Contributing',
            //   to: '/docs/developer-guide/contributing',
            // },
          ],
        },
        {
          title: 'More',
          items: [
            {
              label: 'Blog',
              to: '/blog',
            },
            {
              label: 'GitHub',
              href: 'https://github.com/davidamacey/OpenTranscribe',
            },
            {
              label: 'Docker Hub',
              href: 'https://hub.docker.com/u/davidamacey',
            },
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} OpenTranscribe. Open Source under MIT License.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
