<script lang="ts">
  import { fade, scale } from 'svelte/transition';
  import { onMount, onDestroy } from 'svelte';

  export let showModal = false;

  function closeModal() {
    showModal = false;
  }

  function handleBackdropClick(event: MouseEvent) {
    if (event.target === event.currentTarget) {
      closeModal();
    }
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      closeModal();
    }
  }

  // Disable body scroll when modal is open
  $: if (typeof window !== 'undefined') {
    if (showModal) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
  }

  // Focus management action
  function focusOnMount(node: HTMLElement) {
    node.focus();
    return {
      destroy() {
        // Cleanup if needed
      }
    };
  }

  // Cleanup on component destroy
  onDestroy(() => {
    if (typeof window !== 'undefined') {
      document.body.style.overflow = '';
    }
  });
</script>

{#if showModal}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-noninteractive-tabindex -->
  <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div
    class="modal-backdrop"
    role="dialog"
    aria-modal="true"
    tabindex="0"
    transition:fade={{ duration: 400 }}
    on:click={handleBackdropClick}
    on:keydown={handleKeydown}
  >
    <!-- svelte-ignore a11y-click-events-have-key-events -->
    <!-- svelte-ignore a11y-no-noninteractive-element-event-handlers -->
    <!-- svelte-ignore a11y-no-static-element-interactions -->
    <div
      class="modal-container"
      role="dialog"
      aria-labelledby="about-modal-title"
      aria-modal="true"
      tabindex="-1"
      transition:scale={{ duration: 350, start: 0.9 }}
      on:click|stopPropagation
      on:keydown|stopPropagation
      use:focusOnMount
    >
      <div class="modal-content">
        <div class="modal-header">
          <h2 id="about-modal-title">About OpenTranscribe</h2>
          <button
            class="modal-close"
            on:click={closeModal}
            aria-label="Close about dialog"
            title="Close about dialog"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>

        <div class="modal-body">
          <div class="about-content">
            <section class="intro-section">
              <p class="subtitle">AI-Powered Transcription & Media Management Platform</p>
              <p class="description">
                OpenTranscribe transforms your audio and video files into accurate, searchable transcripts using cutting-edge AI models. Built for professional workflows with an intuitive user experience.
              </p>
            </section>

            <section class="features-section">
              <h3>Key Features</h3>
              <div class="features-grid">
                <div class="feature-item">
                  <div class="feature-icon">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <circle cx="12" cy="12" r="10"></circle>
                      <circle cx="12" cy="12" r="6"></circle>
                      <circle cx="12" cy="12" r="2"></circle>
                    </svg>
                  </div>
                  <div>
                    <h4>AI Transcription</h4>
                    <p>WhisperX for highly accurate speech-to-text with word-level alignment.</p>
                  </div>
                </div>

                <div class="feature-item">
                  <div class="feature-icon">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                      <circle cx="9" cy="7" r="4"></circle>
                      <path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
                      <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
                    </svg>
                  </div>
                  <div>
                    <h4>Speaker Detection</h4>
                    <p>PyAnnote automatically identifies different speakers in conversations.</p>
                  </div>
                </div>

                <div class="feature-item">
                  <div class="feature-icon">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <circle cx="11" cy="11" r="8"></circle>
                      <path d="m21 21-4.35-4.35"></path>
                    </svg>
                  </div>
                  <div>
                    <h4>Full-Text Search</h4>
                    <p>OpenSearch integration enables powerful searching across all transcripts.</p>
                  </div>
                </div>

                <div class="feature-item">
                  <div class="feature-icon">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h4a2 2 0 0 1 2 2v1.28c.6.35 1 .98 1 1.72 0 .74-.4 1.38-1 1.72V15a2 2 0 0 1-2 2h-4v1.27c.6.35 1 .98 1 1.73a2 2 0 1 1-4 0c0-.75.4-1.38 1-1.73V17H7a2 2 0 0 1-2-2v-1.28C4.4 13.38 4 12.74 4 12c0-.74.4-1.37 1-1.72V9a2 2 0 0 1 2-2h4V5.73C10.4 5.39 10 4.74 10 4a2 2 0 0 1 2-2z"></path>
                    </svg>
                  </div>
                  <div>
                    <h4>LLM Summaries</h4>
                    <p>Generate intelligent summaries and extract action items with AI.</p>
                  </div>
                </div>

                <div class="feature-item">
                  <div class="feature-icon">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect>
                      <line x1="8" y1="21" x2="16" y2="21"></line>
                      <line x1="12" y1="17" x2="12" y2="21"></line>
                    </svg>
                  </div>
                  <div>
                    <h4>Progressive Web App</h4>
                    <p>Works seamlessly across desktop and mobile devices.</p>
                  </div>
                </div>

                <div class="feature-item">
                  <div class="feature-icon">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
                      <circle cx="12" cy="16" r="1"></circle>
                      <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
                    </svg>
                  </div>
                  <div>
                    <h4>Secure & Private</h4>
                    <p>Self-hosted with role-based access control and JWT authentication.</p>
                  </div>
                </div>
              </div>
            </section>

            <section class="workflow-section">
              <h3>How It Works</h3>
              <div class="workflow-steps">
                <div class="step">
                  <div class="step-number">1</div>
                  <div class="step-content">
                    <h4>Upload</h4>
                    <p>Upload audio/video files or record directly in the browser.</p>
                  </div>
                </div>

                <div class="step">
                  <div class="step-number">2</div>
                  <div class="step-content">
                    <h4>Process</h4>
                    <p>AI models transcribe speech and identify speakers automatically.</p>
                  </div>
                </div>

                <div class="step">
                  <div class="step-number">3</div>
                  <div class="step-content">
                    <h4>Enhance</h4>
                    <p>Generate summaries, extract action items with LLM features.</p>
                  </div>
                </div>

                <div class="step">
                  <div class="step-number">4</div>
                  <div class="step-content">
                    <h4>Explore</h4>
                    <p>Search, filter, and manage transcripts with powerful tools.</p>
                  </div>
                </div>
              </div>
            </section>

            <section class="credits-section">
              <h3>Built With</h3>
              <p class="credits-intro">OpenTranscribe is powered by these amazing open-source technologies:</p>

              <div class="credits-grid">
                <div class="credit-category">
                  <h4>AI & Machine Learning</h4>
                  <div class="credit-links">
                    <a href="https://github.com/m-bain/whisperX" target="_blank" rel="noopener noreferrer" class="credit-link">
                      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"></path>
                      </svg>
                      WhisperX - Fast ASR with word-level timestamps
                    </a>
                    <a href="https://github.com/SYSTRAN/faster-whisper" target="_blank" rel="noopener noreferrer" class="credit-link">
                      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"></path>
                      </svg>
                      faster-whisper - High-performance Whisper with CTranslate2
                    </a>
                    <a href="https://github.com/pyannote/pyannote-audio" target="_blank" rel="noopener noreferrer" class="credit-link">
                      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"></path>
                      </svg>
                      pyannote-audio - Speaker diarization toolkit
                    </a>
                  </div>
                </div>

                <div class="credit-category">
                  <h4>Backend & Infrastructure</h4>
                  <div class="credit-links">
                    <a href="https://github.com/python/cpython" target="_blank" rel="noopener noreferrer" class="credit-link">
                      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"></path>
                      </svg>
                      Python - Programming language
                    </a>
                    <a href="https://github.com/fastapi/fastapi" target="_blank" rel="noopener noreferrer" class="credit-link">
                      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"></path>
                      </svg>
                      FastAPI - Modern web framework for APIs
                    </a>
                    <a href="https://github.com/postgres/postgres" target="_blank" rel="noopener noreferrer" class="credit-link">
                      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"></path>
                      </svg>
                      PostgreSQL - Advanced database system
                    </a>
                  </div>
                </div>

                <div class="credit-category">
                  <h4>Frontend</h4>
                  <div class="credit-links">
                    <a href="https://github.com/sveltejs/svelte" target="_blank" rel="noopener noreferrer" class="credit-link">
                      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"></path>
                      </svg>
                      Svelte - Cybernetically enhanced web apps
                    </a>
                    <a href="https://github.com/microsoft/TypeScript" target="_blank" rel="noopener noreferrer" class="credit-link">
                      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"></path>
                      </svg>
                      TypeScript - Typed superset of JavaScript
                    </a>
                  </div>
                </div>

                <div class="credit-category">
                  <h4>Queue & Task Processing</h4>
                  <div class="credit-links">
                    <a href="https://github.com/celery/celery" target="_blank" rel="noopener noreferrer" class="credit-link">
                      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"></path>
                      </svg>
                      Celery - Distributed task queue
                    </a>
                    <a href="https://github.com/redis/redis" target="_blank" rel="noopener noreferrer" class="credit-link">
                      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"></path>
                      </svg>
                      Redis - In-memory data store & message broker
                    </a>
                    <a href="https://github.com/mher/flower" target="_blank" rel="noopener noreferrer" class="credit-link">
                      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"></path>
                      </svg>
                      Flower - Celery monitoring & management tool
                    </a>
                  </div>
                </div>
              </div>

              <p class="credits-footer">
                We're grateful to the open-source community for making OpenTranscribe possible.
                <a href="https://github.com/openai/whisper" target="_blank" rel="noopener noreferrer" class="inline-link">OpenAI Whisper</a>
                provides the foundation for our transcription capabilities.
              </p>
            </section>

            <section class="version-section">
              <p class="version-info">OpenTranscribe v2.0 - Built for professional transcription workflows</p>
            </section>
          </div>
        </div>
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    justify-content: center;
    align-items: center;
    z-index: 1000;
    padding: 1rem;
  }

  .modal-container {
    background: var(--surface-color);
    border-radius: 12px;
    box-shadow: 0 25px 50px rgba(0, 0, 0, 0.25);
    max-width: 800px;
    width: 100%;
    max-height: 90vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1.5rem 2rem;
    border-bottom: 1px solid var(--border-color);
  }

  .modal-header h2 {
    color: var(--primary-color);
    font-size: 1.5rem;
    font-weight: 600;
    margin: 0;
  }

  .modal-close {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--text-color);
    padding: 0.25rem;
    border-radius: 4px;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .modal-close:hover {
    background: var(--hover-color);
    color: var(--error-color);
  }

  .modal-body {
    flex: 1;
    overflow-y: auto;
    padding: 2rem;
    max-height: calc(90vh - 100px); /* Reserve space for header */
  }

  .about-content {
    display: flex;
    flex-direction: column;
    gap: 2rem;
  }

  .subtitle {
    font-size: 1.125rem;
    color: var(--primary-color);
    font-weight: 500;
    margin: 0 0 1rem 0;
  }

  .description {
    color: var(--text-secondary);
    line-height: 1.6;
    margin: 0;
  }

  .features-section h3,
  .workflow-section h3 {
    color: var(--text-color);
    font-size: 1.25rem;
    font-weight: 600;
    margin: 0 0 1rem 0;
  }

  .features-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 1rem;
  }

  .feature-item {
    display: flex;
    gap: 0.75rem;
    align-items: flex-start;
  }

  .feature-icon {
    font-size: 1.5rem;
    flex-shrink: 0;
  }

  .feature-item h4 {
    color: var(--text-color);
    font-size: 0.95rem;
    font-weight: 600;
    margin: 0 0 0.25rem 0;
  }

  .feature-item p {
    color: var(--text-secondary);
    font-size: 0.85rem;
    line-height: 1.5;
    margin: 0;
  }

  .workflow-steps {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .step {
    display: flex;
    align-items: flex-start;
    gap: 1rem;
  }

  .step-number {
    flex-shrink: 0;
    width: 32px;
    height: 32px;
    background: var(--primary-color);
    color: white;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 600;
    font-size: 0.875rem;
  }

  .step-content h4 {
    color: var(--text-color);
    font-size: 0.95rem;
    font-weight: 600;
    margin: 0 0 0.25rem 0;
  }

  .step-content p {
    color: var(--text-secondary);
    font-size: 0.85rem;
    line-height: 1.5;
    margin: 0;
  }

  .version-info {
    color: var(--text-secondary);
    font-size: 0.875rem;
    text-align: center;
    font-style: italic;
    margin: 0;
  }

  /* Credits Section Styles */
  .credits-section h3 {
    color: var(--text-color);
    font-size: 1.25rem;
    font-weight: 600;
    margin: 0 0 1rem 0;
  }

  .credits-intro {
    color: var(--text-secondary);
    line-height: 1.6;
    margin: 0 0 1.5rem 0;
  }

  .credits-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 1.5rem;
    margin-bottom: 2rem;
  }

  .credit-category h4 {
    color: var(--text-color);
    font-size: 1rem;
    font-weight: 600;
    margin: 0 0 0.75rem 0;
  }

  .credit-links {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .credit-link {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: var(--text-secondary);
    text-decoration: none;
    font-size: 0.9rem;
    line-height: 1.5;
    padding: 0.5rem 0.75rem;
    border-radius: 6px;
    transition: all 0.2s ease;
  }

  .credit-link:hover {
    color: var(--primary-color);
    background: var(--hover-color, rgba(59, 130, 246, 0.1));
    transform: translateX(4px);
  }

  .credit-link svg {
    flex-shrink: 0;
    opacity: 0.7;
  }

  .credit-link:hover svg {
    opacity: 1;
  }

  .credits-footer {
    color: var(--text-secondary);
    font-size: 0.9rem;
    line-height: 1.6;
    text-align: center;
    margin: 0;
  }

  .inline-link {
    color: var(--primary-color);
    text-decoration: none;
    font-weight: 500;
  }

  .inline-link:hover {
    text-decoration: underline;
  }

  /* Mobile responsive */
  @media (max-width: 768px) {
    .modal-backdrop {
      padding: 0.5rem;
    }

    .modal-header {
      padding: 1rem 1.5rem;
    }

    .modal-body {
      padding: 1.5rem;
      max-height: calc(100vh - 120px); /* Adjusted for mobile */
    }

    .features-grid {
      grid-template-columns: 1fr;
      gap: 1rem;
    }

    .step {
      flex-direction: column;
      text-align: center;
      gap: 0.5rem;
    }

    /* Credits responsive adjustments */
    .credits-grid {
      grid-template-columns: 1fr;
      gap: 1rem;
    }
  }
</style>