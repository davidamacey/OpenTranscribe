import { get } from 'svelte/store';
import axiosInstance from '$lib/axios';
import { toastStore } from '$stores/toast';
import { t } from '$stores/locale';
import axios, { type AxiosProgressEvent } from 'axios';
import * as tus from 'tus-js-client';

// Upload item types
export type UploadType = 'file' | 'url' | 'recording' | 'extracted-audio';
export type UploadStatus =
  | 'queued'
  | 'preparing'
  | 'uploading'
  | 'paused'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface UploadItem {
  id: string;
  type: UploadType;
  source: File | string | Blob;
  name: string;
  size?: number;
  status: UploadStatus;
  progress: number;
  error?: string;
  fileId?: string; // UUID
  retryCount: number;
  startTime?: number;
  estimatedTime?: string;
  isDuplicate?: boolean;
  cancelToken?: any;
  // Extraction metadata (for extracted-audio type)
  extractionMetadata?: any; // ExtractedAudioMetadata from audio extraction
  compressionRatio?: number; // Percentage for display (0-100)
  // Speaker diarization parameters
  minSpeakers?: number | null;
  maxSpeakers?: number | null;
  numSpeakers?: number | null;
  // Organization parameters
  collectionIds?: string[];
  tagNames?: string[];
}

// Upload configuration constants
const MAX_RETRIES = 3;
const RETRY_BASE_DELAY_MS = 1000;
const MAX_CONCURRENT_UPLOADS = 3;
const UPLOAD_TIMEOUT_MS = 300000; // 5 minutes
const QUEUE_PROCESS_DELAY_MS = 100;

// Event types for upload lifecycle
export type UploadEventType =
  | 'added'
  | 'started'
  | 'progress'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'retry';

export interface UploadEvent {
  type: UploadEventType;
  uploadId: string;
  data?: any;
}

// Hash calculation for duplicate detection
async function calculateFileHash(file: File): Promise<string> {
  const arrayBuffer = await file.arrayBuffer();
  const hashBuffer = await crypto.subtle.digest('SHA-256', arrayBuffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  const hashHex = hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
  return hashHex;
}

function getAuthToken(): string {
  try {
    const auth = localStorage.getItem('auth_store');
    if (auth) {
      const parsed = JSON.parse(auth);
      return parsed.token || parsed.access_token || '';
    }
  } catch {
    // fallback
  }
  return '';
}

async function getOrRefreshToken(): Promise<string> {
  // Use the existing auth store to get current token
  // If expired, the auth store handles refresh
  return getAuthToken();
}

class UploadService {
  private uploads: Map<string, UploadItem> = new Map();
  private eventListeners: ((event: UploadEvent) => void)[] = [];
  private processingQueue: string[] = [];
  private activeUploads: Set<string> = new Set();
  private _tusUploads = new Map<string, tus.Upload>();

  constructor() {
    this.loadPersistedUploads();
    // Warn users before closing the tab with active uploads
    if (typeof window !== 'undefined') {
      window.addEventListener('beforeunload', (e: BeforeUnloadEvent) => {
        const hasActive =
          this.getActiveUploads().length > 0 || Array.from(this._tusUploads.keys()).length > 0;
        if (hasActive) {
          e.preventDefault();
          e.returnValue = '';
        }
      });
    }
  }

  // Event system
  addEventListener(listener: (event: UploadEvent) => void) {
    this.eventListeners.push(listener);
    return () => {
      const index = this.eventListeners.indexOf(listener);
      if (index > -1) {
        this.eventListeners.splice(index, 1);
      }
    };
  }

  private emit(type: UploadEventType, uploadId: string, data?: any) {
    const event: UploadEvent = { type, uploadId, data };
    this.eventListeners.forEach((listener) => listener(event));
  }

  // Queue management
  addUpload(
    type: UploadType,
    source: File | string | Blob,
    name?: string,
    speakerParams?: {
      minSpeakers?: number | null;
      maxSpeakers?: number | null;
      numSpeakers?: number | null;
    },
    collectionIds?: string[],
    tagNames?: string[]
  ): string {
    const id = this.generateId();
    const uploadName = name || this.getSourceName(source);

    const upload: UploadItem = {
      id,
      type,
      source,
      name: uploadName,
      size: source instanceof File ? source.size : undefined,
      status: 'queued',
      progress: 0,
      retryCount: 0,
      minSpeakers: speakerParams?.minSpeakers,
      maxSpeakers: speakerParams?.maxSpeakers,
      numSpeakers: speakerParams?.numSpeakers,
      collectionIds,
      tagNames,
    };

    this.uploads.set(id, upload);
    this.processingQueue.push(id);
    this.persistUploads();

    this.emit('added', id, upload);

    // Start processing if we have capacity
    this.processQueue();

    return id;
  }

  addMultipleFiles(files: File[], collectionIds?: string[], tagNames?: string[]): string[] {
    const uploadIds: string[] = [];

    files.forEach((file) => {
      const id = this.addUpload('file', file, undefined, undefined, collectionIds, tagNames);
      uploadIds.push(id);
    });

    return uploadIds;
  }

  addExtractedAudio(
    audioBlob: Blob,
    filename: string,
    extractionMetadata: any,
    compressionRatio: number
  ): string {
    const id = this.generateId();

    const upload: UploadItem = {
      id,
      type: 'extracted-audio',
      source: audioBlob,
      name: filename,
      size: audioBlob.size,
      status: 'queued',
      progress: 0,
      retryCount: 0,
      extractionMetadata,
      compressionRatio,
    };

    this.uploads.set(id, upload);
    this.processingQueue.push(id);
    this.persistUploads();

    this.emit('added', id, upload);

    // Start processing if we have capacity
    this.processQueue();

    return id;
  }

  // Process upload queue
  private async processQueue() {
    if (this.activeUploads.size >= MAX_CONCURRENT_UPLOADS) {
      return;
    }

    const nextUploadId = this.processingQueue.find(
      (id) => !this.activeUploads.has(id) && this.uploads.get(id)?.status === 'queued'
    );

    if (!nextUploadId) {
      return;
    }

    this.activeUploads.add(nextUploadId);
    const queueIndex = this.processingQueue.indexOf(nextUploadId);
    if (queueIndex > -1) {
      this.processingQueue.splice(queueIndex, 1);
    }

    try {
      await this.processUpload(nextUploadId);
    } catch (error) {
      // Error is handled in processUpload method
    } finally {
      this.activeUploads.delete(nextUploadId);
      // Continue processing queue
      setTimeout(() => this.processQueue(), QUEUE_PROCESS_DELAY_MS);
    }
  }

  private async processUpload(uploadId: string) {
    const upload = this.uploads.get(uploadId);
    if (!upload) return;

    try {
      // Set status to preparing with 0% progress
      this.updateUpload(uploadId, {
        status: 'preparing',
        startTime: Date.now(),
        progress: 0,
        estimatedTime: undefined,
      });
      this.emit('started', uploadId);

      let result;
      switch (upload.type) {
        case 'file':
        case 'recording':
          result = await this.uploadFile(uploadId, upload.source as File);
          break;
        case 'extracted-audio':
          result = await this.uploadExtractedAudio(
            uploadId,
            upload.source as Blob,
            upload.extractionMetadata
          );
          break;
        case 'url':
          result = await this.processUrl(uploadId, upload.source as string);
          break;
        default:
          throw new Error(get(t)('upload.unknownType', { type: upload.type }));
      }

      // Upload completed successfully - show 100% with green checkmark
      this.updateUpload(uploadId, {
        status: 'completed',
        progress: 100,
        fileId: result.uuid,
        isDuplicate: result.isDuplicate,
        estimatedTime: undefined,
      });

      this.emit('completed', uploadId, result);

      // Show appropriate toast based on duplicate status
      if (result.isDuplicate) {
        toastStore.warning(get(t)('upload.fileAlreadyExists', { name: upload.name }));
      } else {
        toastStore.success(get(t)('upload.uploadCompleted', { name: upload.name }));
      }
    } catch (error: any) {
      // Log error through proper error handling below

      const errorMessage = this.getErrorMessage(error);
      this.updateUpload(uploadId, {
        status: 'failed',
        error: errorMessage,
      });

      this.emit('failed', uploadId, { error: errorMessage });

      // Handle retry logic
      if (upload.retryCount < MAX_RETRIES && !axios.isCancel(error)) {
        setTimeout(
          () => {
            this.retryUpload(uploadId);
          },
          RETRY_BASE_DELAY_MS * Math.pow(2, upload.retryCount)
        );
      } else {
        toastStore.error(
          get(t)('upload.uploadFailed', {
            name: upload.name,
            error: errorMessage,
          })
        );
      }
    }

    this.persistUploads();
  }

  private async uploadFile(uploadId: string, file: File | Blob): Promise<any> {
    const upload = this.uploads.get(uploadId)!;

    // Calculate file hash for duplicate detection
    let fileHash = '';
    if (file instanceof File) {
      try {
        this.updateUpload(uploadId, {
          status: 'preparing',
          progress: 0,
          estimatedTime: get(t)('upload.calculatingHash'),
        });
        fileHash = await calculateFileHash(file);
      } catch {
        // File hash calculation is optional
      }
    }

    // Step 1: Prepare the upload (unchanged)
    const prepareResponse = await axiosInstance.post('/files/prepare', {
      filename: upload.name,
      file_size: file.size,
      content_type: file instanceof File ? file.type : 'audio/webm',
      file_hash: fileHash || null,
      collection_ids: upload.collectionIds || undefined,
      tag_names: upload.tagNames || undefined,
    });

    const { file_id: fileId, is_duplicate } = prepareResponse.data;

    if (is_duplicate) {
      return { uuid: fileId, isDuplicate: true };
    }

    // Step 2: Upload via TUS (replaces direct Axios POST /files)
    this.updateUpload(uploadId, {
      status: 'uploading',
      fileId,
      progress: 0,
      estimatedTime: 'Uploading...',
    });

    await this._tusUpload(
      uploadId,
      file instanceof File ? file : new File([file], upload.name),
      fileId,
      fileHash,
      upload.minSpeakers ?? undefined,
      upload.maxSpeakers ?? undefined,
      upload.numSpeakers ?? undefined
    );

    return { uuid: fileId, isDuplicate: false };
  }

  private async uploadExtractedAudio(
    uploadId: string,
    audioBlob: Blob,
    extractionMetadata: any
  ): Promise<any> {
    const upload = this.uploads.get(uploadId)!;

    const originalFileHash = extractionMetadata?.originalFileHash || null;

    // Step 1: Prepare
    const prepareResponse = await axiosInstance.post('/files/prepare', {
      filename: upload.name,
      file_size: audioBlob.size,
      content_type: audioBlob.type || 'audio/opus',
      file_hash: originalFileHash,
      extracted_from_video: extractionMetadata?.videoMetadata || null,
      collection_ids: upload.collectionIds || undefined,
      tag_names: upload.tagNames || undefined,
    });

    const { file_id: fileId, is_duplicate } = prepareResponse.data;

    if (is_duplicate) {
      return { uuid: fileId, isDuplicate: true };
    }

    // Step 2: Upload via TUS
    this.updateUpload(uploadId, {
      status: 'uploading',
      fileId,
      progress: 0,
      estimatedTime: 'Uploading extracted audio...',
    });

    await this._tusUpload(
      uploadId,
      new File([audioBlob], upload.name, { type: audioBlob.type || 'audio/opus' }),
      fileId,
      originalFileHash || '',
      undefined,
      undefined,
      undefined,
      extractionMetadata?.videoMetadata || undefined
    );

    return { uuid: fileId, isDuplicate: false };
  }

  private async processUrl(uploadId: string, url: string): Promise<any> {
    const upload = this.uploads.get(uploadId)!;

    // Create cancel token
    const cancelToken = axios.CancelToken.source();
    this.updateUpload(uploadId, {
      cancelToken,
      status: 'processing',
    });

    const response = await axiosInstance.post(
      '/files/process-url',
      {
        url: url.trim(),
        collection_ids: upload.collectionIds || undefined,
        tag_names: upload.tagNames || undefined,
      },
      {
        timeout: UPLOAD_TIMEOUT_MS,
        cancelToken: cancelToken.token,
        onUploadProgress: (progressEvent: AxiosProgressEvent) => {
          if (progressEvent.total) {
            const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            this.updateUpload(uploadId, { progress });
            this.emit('progress', uploadId, { progress });
          }
        },
      }
    );

    return { uuid: response.data.uuid, isDuplicate: false };
  }

  // Upload management
  retryUpload(uploadId: string) {
    const upload = this.uploads.get(uploadId);
    if (!upload) return;

    this.updateUpload(uploadId, {
      status: 'queued',
      progress: 0,
      error: undefined,
      retryCount: upload.retryCount + 1,
      cancelToken: undefined,
    });

    this.processingQueue.push(uploadId);
    this.emit('retry', uploadId);
    this.processQueue();
    this.persistUploads();
  }

  private async _tusUpload(
    uploadId: string,
    file: File,
    fileId: string,
    fileHash: string,
    minSpeakers?: number,
    maxSpeakers?: number,
    numSpeakers?: number,
    extractedFromVideo?: object
  ): Promise<void> {
    const encode = (v: string) => btoa(unescape(encodeURIComponent(v)));
    const metadata: Record<string, string> = {
      filename: encode(file.name),
      filetype: encode(file.type || 'application/octet-stream'),
      fileId: encode(fileId),
      fileHash: encode(fileHash || ''),
    };
    if (minSpeakers != null) metadata.minSpeakers = encode(String(minSpeakers));
    if (maxSpeakers != null) metadata.maxSpeakers = encode(String(maxSpeakers));
    if (numSpeakers != null) metadata.numSpeakers = encode(String(numSpeakers));
    if (extractedFromVideo) {
      metadata.extractedFromVideo = encode(JSON.stringify(extractedFromVideo));
    }

    return new Promise<void>((resolve, reject) => {
      const upload = new tus.Upload(file, {
        endpoint: `/api/files/tus`,
        chunkSize: 10 * 1024 * 1024, // 10MB chunks
        retryDelays: [1000, 2000, 4000, 8000, 16000],
        storeFingerprintForResuming: true,
        fingerprint: async (_f: File, _opts: any) => `tus-${file.name}-${file.size}-${fileHash}`,
        metadata,
        headers: { Authorization: `Bearer ${getAuthToken()}` },
        onBeforeRequest: async (req: any) => {
          const token = await getOrRefreshToken();
          req.setHeader('Authorization', `Bearer ${token}`);
        },
        onProgress: (bytesUploaded: number, bytesTotal: number) => {
          const progress = Math.round((bytesUploaded / bytesTotal) * 99);
          this.updateUpload(uploadId, { progress, status: 'uploading' });
          this.emit('progress', uploadId, { progress });
        },
        onSuccess: () => {
          this._tusUploads.delete(uploadId);
          resolve();
        },
        onError: (error: any) => {
          if (error.originalResponse?.getStatus() === 401) {
            // Token refresh handled by onBeforeRequest — retry will occur
            return;
          }
          this._tusUploads.delete(uploadId);
          reject(error);
        },
      });

      this._tusUploads.set(uploadId, upload);

      // Resume from previous upload if exists in localStorage
      upload.findPreviousUploads().then((previous: any[]) => {
        if (previous.length > 0) {
          upload.resumeFromPreviousUpload(previous[0]);
          this.emit('progress', uploadId, { resumed: true });
        }
        upload.start();
      });
    });
  }

  pauseUpload(uploadId: string): void {
    const tusUpload = this._tusUploads.get(uploadId);
    if (tusUpload) {
      tusUpload.abort();
      this.updateUpload(uploadId, { status: 'paused' });
      this.persistUploads();
    }
  }

  resumeTusUpload(uploadId: string): void {
    const tusUpload = this._tusUploads.get(uploadId);
    if (tusUpload) {
      tusUpload.start();
      this.updateUpload(uploadId, { status: 'uploading' });
      this.persistUploads();
    }
  }

  cancelUpload(uploadId: string) {
    const upload = this.uploads.get(uploadId);
    if (!upload) return;

    // Cancel the request if it has a cancel token
    if (upload.cancelToken) {
      upload.cancelToken.cancel('Upload cancelled by user');
    }

    // Abort TUS upload if active (sends TUS DELETE to server)
    const tusUpload = this._tusUploads.get(uploadId);
    if (tusUpload) {
      tusUpload.abort(true); // true = send TUS DELETE request
      this._tusUploads.delete(uploadId);
    }

    this.updateUpload(uploadId, {
      status: 'cancelled',
      error: 'Cancelled by user',
    });

    // Remove from active uploads and queue
    this.activeUploads.delete(uploadId);
    const queueIndex = this.processingQueue.indexOf(uploadId);
    if (queueIndex > -1) {
      this.processingQueue.splice(queueIndex, 1);
    }

    this.emit('cancelled', uploadId);
    this.persistUploads();

    // Continue processing queue
    this.processQueue();
  }

  removeUpload(uploadId: string) {
    const upload = this.uploads.get(uploadId);
    if (!upload) return;

    // Cancel if still active
    if (upload.status === 'uploading' || upload.status === 'processing') {
      this.cancelUpload(uploadId);
    }

    this.uploads.delete(uploadId);
    this.persistUploads();
  }

  clearCompleted() {
    const completedIds = Array.from(this.uploads.entries())
      .filter(([_, upload]) => upload.status === 'completed')
      .map(([id, _]) => id);

    completedIds.forEach((id) => this.uploads.delete(id));
    this.persistUploads();
  }

  // Getters
  getUpload(uploadId: string): UploadItem | undefined {
    return this.uploads.get(uploadId);
  }

  getAllUploads(): UploadItem[] {
    return Array.from(this.uploads.values());
  }

  getActiveUploads(): UploadItem[] {
    return this.getAllUploads().filter(
      (upload) =>
        upload.status === 'uploading' ||
        upload.status === 'processing' ||
        upload.status === 'preparing' ||
        upload.status === 'paused'
    );
  }

  getQueuedUploads(): UploadItem[] {
    return this.getAllUploads().filter((upload) => upload.status === 'queued');
  }

  // Helper methods
  private updateUpload(uploadId: string, updates: Partial<UploadItem>) {
    const upload = this.uploads.get(uploadId);
    if (!upload) return;

    Object.assign(upload, updates);
    this.uploads.set(uploadId, upload);
  }

  private generateId(): string {
    return (
      Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15)
    );
  }

  private getSourceName(source: File | string | Blob): string {
    if (source instanceof File) {
      return source.name;
    } else if (typeof source === 'string') {
      try {
        const url = new URL(source);
        // Try to extract YouTube video title or use a more descriptive name
        if (url.hostname.includes('youtube.com') || url.hostname.includes('youtu.be')) {
          return 'YouTube Video';
        }
        return url.pathname.split('/').pop() || 'Video URL';
      } catch {
        return 'Video URL';
      }
    } else {
      // Blob (recording)
      return `recording_${new Date().toISOString().replace(/[:.]/g, '-')}.webm`;
    }
  }

  private getErrorMessage(error: any): string {
    if (axios.isCancel(error)) {
      return 'Upload cancelled';
    }

    if (error?.response?.data?.detail) {
      return error.response.data.detail;
    }

    if (error?.message) {
      return error.message;
    }

    return 'Unknown error occurred';
  }

  private formatTimeRemaining(ms: number): string {
    if (!ms || ms <= 0) return '';

    const seconds = Math.ceil(ms / 1000);
    if (seconds < 60) return `${seconds}s`;

    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;

    if (minutes < 60) {
      return remainingSeconds > 0 ? `${minutes}m ${remainingSeconds}s` : `${minutes}m`;
    }

    const hours = Math.floor(minutes / 60);
    const remainingMinutes = minutes % 60;
    return `${hours}h ${remainingMinutes}m`;
  }

  // Persistence
  private persistUploads() {
    try {
      const uploadsData = Array.from(this.uploads.entries()).map(([id, upload]) => [
        id,
        {
          ...upload,
          // Don't persist source data or cancel tokens
          source: upload.type === 'url' ? upload.source : null,
          cancelToken: undefined,
        },
      ]);
      localStorage.setItem('upload_queue', JSON.stringify(uploadsData));
    } catch (error) {
      // localStorage persistence is optional
    }
  }

  private loadPersistedUploads() {
    try {
      const stored = localStorage.getItem('upload_queue');
      if (stored) {
        const uploadsData = JSON.parse(stored);
        uploadsData.forEach(([id, upload]: [string, UploadItem]) => {
          // Only restore queued or failed uploads that can be retried
          if (upload.status === 'queued' || upload.status === 'failed') {
            // Reset to queued state for retry
            upload.status = 'queued';
            upload.progress = 0;
            upload.error = undefined;
            this.uploads.set(id, upload);

            // Only add URL uploads back to queue (files would need re-selection)
            if (upload.type === 'url' && upload.source) {
              this.processingQueue.push(id);
            }
          }
        });

        // Start processing any restored uploads
        if (this.processingQueue.length > 0) {
          setTimeout(() => this.processQueue(), 1000);
        }
      }
    } catch (error) {
      // localStorage loading is optional
    }
  }
}

// Export singleton instance
export const uploadService = new UploadService();
