import type {ReactNode} from 'react';
import clsx from 'clsx';
import Heading from '@theme/Heading';
import styles from './styles.module.css';

type FeatureItem = {
  title: string;
  emoji: string;
  description: ReactNode;
};

const FeatureList: FeatureItem[] = [
  {
    title: 'High-Accuracy Transcription',
    emoji: '🎧',
    description: (
      <>
        Powered by WhisperX with word-level timestamps and 70x realtime speed on GPU.
        Supports 50+ languages with automatic English translation.
      </>
    ),
  },
  {
    title: 'Smart Speaker Detection',
    emoji: '👥',
    description: (
      <>
        Automatic speaker diarization with PyAnnote.audio. Cross-video speaker
        recognition with voice fingerprinting and AI-powered identification.
      </>
    ),
  },
  {
    title: 'AI-Powered Insights',
    emoji: '🤖',
    description: (
      <>
        Generate BLUF summaries, extract action items, and analyze speaker patterns
        using multiple LLM providers (OpenAI, Claude, vLLM, Ollama).
      </>
    ),
  },
  {
    title: 'Hybrid Search',
    emoji: '🔍',
    description: (
      <>
        Lightning-fast full-text and semantic search with OpenSearch 3.3.1.
        9.5x faster vector search and 25% faster queries.
      </>
    ),
  },
  {
    title: 'Privacy-First',
    emoji: '🔒',
    description: (
      <>
        Self-hosted solution where all data stays on your infrastructure.
        Works completely offline. Perfect for sensitive content.
      </>
    ),
  },
  {
    title: 'Production-Ready',
    emoji: '⚡',
    description: (
      <>
        Docker-based deployment with GPU acceleration, multi-worker architecture,
        and comprehensive monitoring. Scales from laptop to datacenter.
      </>
    ),
  },
];

function Feature({title, emoji, description}: FeatureItem) {
  return (
    <div className={clsx('col col--4')}>
      <div className="text--center padding-horiz--md">
        <div className={styles.featureEmoji}>{emoji}</div>
        <Heading as="h3">{title}</Heading>
        <p>{description}</p>
      </div>
    </div>
  );
}

export default function HomepageFeatures(): ReactNode {
  return (
    <section className={styles.features}>
      <div className="container">
        <Heading as="h2" className="text--center margin-bottom--lg">
          Why OpenTranscribe?
        </Heading>
        <div className="row">
          {FeatureList.map((props, idx) => (
            <Feature key={idx} {...props} />
          ))}
        </div>
      </div>
    </section>
  );
}
