/// <reference types="@sveltejs/kit" />

// See https://kit.svelte.dev/docs/types#app
// for information about these interfaces
declare namespace App {
  // interface Error {}
  // interface Locals {}
  // interface PageData {}
  // interface Platform {}
}

// Vite environment variables
declare namespace NodeJS {
  interface ProcessEnv {
    readonly NODE_ENV: 'development' | 'production' | 'test';
  }
}

interface ImportMetaEnv {
  readonly PROD: boolean;
  readonly DEV: boolean;
  // Add other environment variables as needed
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
