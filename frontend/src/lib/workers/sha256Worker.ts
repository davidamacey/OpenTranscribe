// SHA-256 hash Web Worker — keeps the main thread responsive while hashing
// large files. Phase 2 of the timing audit plan (uploadService.ts:339 used
// to stall the UI for 5-15s on 2-5 GB files).
//
// Vite's ?worker import syntax picks this up transparently; see
// lib/services/sha256Hasher.ts for the client wrapper.

export type HashRequest = {
  id: string;
  file: File | Blob;
};

export type HashResponse =
  | { id: string; ok: true; hash: string }
  | { id: string; ok: false; error: string };

async function digestHex(data: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', data);
  const bytes = new Uint8Array(digest);
  let out = '';
  for (const b of bytes) {
    out += b.toString(16).padStart(2, '0');
  }
  return out;
}

self.addEventListener('message', async (event: MessageEvent<HashRequest>) => {
  const { id, file } = event.data;
  try {
    const buf = await file.arrayBuffer();
    const hash = await digestHex(buf);
    (self as unknown as DedicatedWorkerGlobalScope).postMessage({
      id,
      ok: true,
      hash,
    } satisfies HashResponse);
  } catch (err) {
    (self as unknown as DedicatedWorkerGlobalScope).postMessage({
      id,
      ok: false,
      error: err instanceof Error ? err.message : String(err),
    } satisfies HashResponse);
  }
});

// Vite picks up the default export for ?worker imports on some setups;
// the empty module ensures this file is treated as an ES module.
export {};
