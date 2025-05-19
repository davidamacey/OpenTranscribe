/**
 * Service Worker registration and unregistration functions
 * This file should be imported in your main application file
 */

export function register(): void {
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker
        .register('/service-worker.js')
        .then((registration) => {
          console.log('ServiceWorker registration successful with scope: ', registration.scope);
        })
        .catch((error) => {
          console.error('ServiceWorker registration failed: ', error);
        });
    });
  }
}

export function unregister(): void {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.ready.then((registration) => {
      registration.unregister();
    });
  }
}

// Export a default object for backward compatibility
const serviceWorkerRegistration = {
  register,
  unregister,
};

export default serviceWorkerRegistration;
