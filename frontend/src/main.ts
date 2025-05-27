import App from './App.svelte';

// Register service worker in production
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/service-worker.js')
      .then(registration => {
        // ServiceWorker registration successful
      })
      .catch(error => {
        console.error('ServiceWorker registration failed: ', error);
      });
  });
}

const target = document.getElementById('app');

// Ensure the target element exists
if (!target) {
  throw new Error('Could not find #app element to mount the Svelte application');
}

const app = new App({ target });

export default app;
