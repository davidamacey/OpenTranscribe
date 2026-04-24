// Thin client wrapper for the SHA-256 Web Worker. Falls back to the
// main-thread crypto.subtle API when Workers are unavailable (old
// browsers, jsdom test environments, SSR).

import type { HashRequest, HashResponse } from '$lib/workers/sha256Worker';

type Resolver = (hash: string) => void;
type Rejector = (err: Error) => void;

let workerPromise: Promise<Worker | null> | null = null;
let nextRequestId = 0;
const inflight = new Map<string, { resolve: Resolver; reject: Rejector }>();

function fallbackHash(file: File | Blob): Promise<string> {
  // Main-thread fallback — only used when the Worker isn't available.
  return file
    .arrayBuffer()
    .then((buf) => crypto.subtle.digest('SHA-256', buf))
    .then((digest) => {
      const bytes = new Uint8Array(digest);
      let out = '';
      for (const b of bytes) {
        out += b.toString(16).padStart(2, '0');
      }
      return out;
    });
}

async function getWorker(): Promise<Worker | null> {
  if (typeof Worker === 'undefined') {
    return null;
  }
  if (!workerPromise) {
    workerPromise = (async () => {
      try {
        // Vite ?worker import gives us a Worker constructor. Using dynamic
        // import keeps SSR-safe (no Worker access at module load time).
        const mod = await import('$lib/workers/sha256Worker?worker');
        const WorkerCtor = (mod as unknown as { default: new () => Worker }).default;
        const w = new WorkerCtor();
        w.addEventListener('message', (event: MessageEvent<HashResponse>) => {
          const payload = event.data as HashResponse;
          const waiter = inflight.get(payload.id);
          if (!waiter) return;
          inflight.delete(payload.id);
          if (payload.ok === true) {
            waiter.resolve((payload as { hash: string }).hash);
          } else {
            waiter.reject(new Error((payload as { error: string }).error));
          }
        });
        w.addEventListener('error', (event) => {
          for (const waiter of inflight.values()) {
            waiter.reject(new Error(event.message || 'sha256 worker error'));
          }
          inflight.clear();
        });
        return w;
      } catch {
        return null;
      }
    })();
  }
  return workerPromise;
}

/**
 * Compute the SHA-256 hash of a File/Blob. Uses a dedicated Web Worker to
 * keep the main thread responsive on multi-GB inputs; falls back to the
 * main-thread implementation if a Worker can't be spawned.
 */
export async function hashFileSHA256(file: File | Blob): Promise<string> {
  const worker = await getWorker();
  if (!worker) {
    return fallbackHash(file);
  }
  const id = `h${++nextRequestId}`;
  return new Promise<string>((resolve, reject) => {
    inflight.set(id, { resolve, reject });
    const msg: HashRequest = { id, file };
    worker.postMessage(msg);
  });
}
