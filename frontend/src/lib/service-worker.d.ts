/// <reference no-default-lib="true"/>
/// <reference lib="es2015" />
/// <reference lib="webworker" />

declare const self: ServiceWorkerGlobalScope;

// Extend the global scope with service worker types
declare global {
  interface ServiceWorkerGlobalScope {
    __WB_MANIFEST: string[];
    skipWaiting(): void;
  }

  interface ExtendableEvent extends Event {
    waitUntil(promise: Promise<any>): void;
  }

  interface FetchEvent extends Event {
    readonly request: Request;
    respondWith(response: Promise<Response> | Response): void;
  }
}

// This makes TypeScript aware of the global types
export {};
