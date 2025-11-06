import type {ReactNode} from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import Layout from '@theme/Layout';
import HomepageFeatures from '@site/src/components/HomepageFeatures';
import Heading from '@theme/Heading';

import styles from './index.module.css';

function HomepageHeader() {
  const {siteConfig} = useDocusaurusContext();
  return (
    <header className={clsx('hero hero--primary', styles.heroBanner)}>
      <div className="container">
        <Heading as="h1" className="hero__title">
          {siteConfig.title}
        </Heading>
        <p className="hero__subtitle">{siteConfig.tagline}</p>

        <div style={{textAlign: 'center', margin: '1.5rem auto', maxWidth: '600px'}}>
          <img
            src="/img/opentranscribe-workflow.gif"
            alt="OpenTranscribe Complete Workflow"
            style={{
              maxWidth: '100%',
              width: '100%',
              borderRadius: '8px',
              boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)'
            }}
          />
          <p style={{marginTop: '0.5rem', fontSize: '0.9rem', fontStyle: 'italic', opacity: 0.8}}>
            Complete workflow: Login → Upload → Process → Transcribe → Speaker Identification → AI Tags & Collections
          </p>
        </div>

        <p className={styles.heroDescription}>
          Self-hosted, open-source AI transcription with speaker identification,
          AI summarization, and powerful search. Privacy-first, production-ready, and 70x realtime speed.
        </p>
        <div className={styles.buttons}>
          <Link
            className="button button--primary button--lg margin-right--md margin-bottom--md"
            to="/docs/getting-started/quick-start">
            Get Started - 5 min ⚡
          </Link>
          <Link
            className="button button--secondary button--lg margin-bottom--md"
            to="/docs/getting-started/introduction">
            Learn More 📖
          </Link>
        </div>
        <div className={styles.quickInstall}>
          <pre className={styles.installCommand}>
            <code>curl -fsSL https://raw.githubusercontent.com/davidamacey/OpenTranscribe/master/setup-opentranscribe.sh | bash</code>
          </pre>
        </div>
      </div>
    </header>
  );
}


function HomepageStats() {
  return (
    <section className={styles.stats}>
      <div className="container">
        <div className="row">
          <div className="col col--3">
            <div className={styles.stat}>
              <div className={styles.statNumber}>70x</div>
              <div className={styles.statLabel}>Realtime Speed</div>
            </div>
          </div>
          <div className="col col--3">
            <div className={styles.stat}>
              <div className={styles.statNumber}>50+</div>
              <div className={styles.statLabel}>Languages</div>
            </div>
          </div>
          <div className="col col--3">
            <div className={styles.stat}>
              <div className={styles.statNumber}>100%</div>
              <div className={styles.statLabel}>Local & Private</div>
            </div>
          </div>
          <div className="col col--3">
            <div className={styles.stat}>
              <div className={styles.statNumber}>MIT</div>
              <div className={styles.statLabel}>Open Source</div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function HomepageCTA() {
  return (
    <section className={styles.cta}>
      <div className="container">
        <div className="text--center">
          <Heading as="h2" className="margin-bottom--md">
            Ready to Get Started?
          </Heading>
          <p className="margin-bottom--lg">
            Install OpenTranscribe in less than 5 minutes with our one-line installer.
          </p>
          <Link
            className="button button--primary button--lg"
            to="/docs/getting-started/quick-start">
            Install Now →
          </Link>
        </div>
      </div>
    </section>
  );
}

export default function Home(): ReactNode {
  const {siteConfig} = useDocusaurusContext();
  return (
    <Layout
      title="Home"
      description="AI-Powered Transcription and Media Analysis Platform - Self-hosted, open-source, privacy-first">
      <HomepageHeader />
      <main>
        <HomepageStats />
        <HomepageFeatures />
        <HomepageCTA />
      </main>
    </Layout>
  );
}
