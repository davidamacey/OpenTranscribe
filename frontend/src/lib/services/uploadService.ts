import { get } from 'svelte/store';
import axiosInstance from '$lib/axios';
import { authStore } from '$stores/auth';
import { toastStore } from '$stores/toast';
import axios, { type AxiosProgressEvent } from 'axios';

// Upload item types
export type UploadType = 'file' | 'url' | 'recording';
export type UploadStatus = 'queued' | 'preparing' | 'uploading' | 'processing' | 'completed' | 'failed' | 'cancelled';

export interface UploadItem {
  id: string;
  type: UploadType;
  source: File | string | Blob;
  name: string;
  size?: number;
  status: UploadStatus;
  progress: number;
  error?: string;
  fileId?: number;
  retryCount: number;
  startTime?: number;
  estimatedTime?: string;
  isDuplicate?: boolean;
  cancelToken?: any;
}

// Upload configuration constants
const MAX_RETRIES = 3;
const RETRY_BASE_DELAY_MS = 1000;
const MAX_CONCURRENT_UPLOADS = 3;
const UPLOAD_TIMEOUT_MS = 300000; // 5 minutes
const QUEUE_PROCESS_DELAY_MS = 100;


// Event types for upload lifecycle
export type UploadEventType = 'added' | 'started' | 'progress' | 'completed' | 'failed' | 'cancelled' | 'retry';

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
  const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
  return hashHex;
}

class UploadService {
  private uploads: Map<string, UploadItem> = new Map();
  private eventListeners: ((event: UploadEvent) => void)[] = [];
  private processingQueue: string[] = [];
  private activeUploads: Set<string> = new Set();

  constructor() {
    this.loadPersistedUploads();
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
    this.eventListeners.forEach(listener => listener(event));
  }

  // Queue management
  addUpload(type: UploadType, source: File | string | Blob, name?: string): string {
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
    };

    this.uploads.set(id, upload);
    this.processingQueue.push(id);
    this.persistUploads();
    
    this.emit('added', id, upload);
    
    // Start processing if we have capacity
    this.processQueue();
    
    return id;
  }

  addMultipleFiles(files: File[]): string[] {
    const uploadIds: string[] = [];
    
    files.forEach(file => {
      const id = this.addUpload('file', file);
      uploadIds.push(id);
    });

    return uploadIds;
  }

  // Process upload queue
  private async processQueue() {
    if (this.activeUploads.size >= MAX_CONCURRENT_UPLOADS) {
      return;
    }

    const nextUploadId = this.processingQueue.find(id => 
      !this.activeUploads.has(id) && 
      this.uploads.get(id)?.status === 'queued'
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
      // Set status to preparing
      this.updateUpload(uploadId, { status: 'preparing', startTime: Date.now() });
      this.emit('started', uploadId);

      let result;
      switch (upload.type) {
        case 'file':
        case 'recording':
          result = await this.uploadFile(uploadId, upload.source as File);
          break;
        case 'url':
          result = await this.processUrl(uploadId, upload.source as string);
          break;
        default:
          throw new Error(`Unknown upload type: ${upload.type}`);
      }

      this.updateUpload(uploadId, {
        status: 'completed',
        progress: 100,
        fileId: result.id,
        isDuplicate: result.isDuplicate
      });

      this.emit('completed', uploadId, result);
      
      // Show success toast
      toastStore.success(
        upload.isDuplicate 
          ? `File already exists: ${upload.name}`
          : `Upload completed: ${upload.name}`
      );

    } catch (error: any) {
      // Log error through proper error handling below
      
      const errorMessage = this.getErrorMessage(error);
      this.updateUpload(uploadId, {
        status: 'failed',
        error: errorMessage
      });

      this.emit('failed', uploadId, { error: errorMessage });
      
      // Handle retry logic
      if (upload.retryCount < MAX_RETRIES && !axios.isCancel(error)) {
        setTimeout(() => {
          this.retryUpload(uploadId);
        }, RETRY_BASE_DELAY_MS * Math.pow(2, upload.retryCount));
      } else {
        toastStore.error(`Upload failed: ${upload.name} - ${errorMessage}`);
      }
    }

    this.persistUploads();
  }

  private async uploadFile(uploadId: string, file: File | Blob): Promise<any> {
    const upload = this.uploads.get(uploadId)!;
    
    // Create cancel token
    const cancelToken = axios.CancelToken.source();
    this.updateUpload(uploadId, { cancelToken });

    // Calculate file hash for duplicate detection
    let fileHash = null;
    if (file instanceof File) {
      try {
        this.updateUpload(uploadId, { status: 'preparing' });
        fileHash = await calculateFileHash(file);
      } catch (err) {
        // File hash calculation is optional, continue without it
      }
    }

    // Step 1: Prepare the upload
    const prepareResponse = await axiosInstance.post('/files/prepare', {
      filename: upload.name,
      file_size: file.size,
      content_type: file instanceof File ? file.type : 'audio/webm',
      file_hash: fileHash
    });

    const { file_id: fileId, is_duplicate } = prepareResponse.data;

    if (is_duplicate) {
      return { id: fileId, isDuplicate: true };
    }

    // Step 2: Upload the file
    this.updateUpload(uploadId, { status: 'uploading', fileId });

    const formData = new FormData();
    formData.append('file', file);

    await axiosInstance.post('/files', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
        'X-File-ID': fileId.toString(),
        'X-File-Hash': fileHash || '',
      },
      timeout: UPLOAD_TIMEOUT_MS,
      cancelToken: cancelToken.token,
      onUploadProgress: (progressEvent: AxiosProgressEvent) => {
        if (progressEvent.total) {
          const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          this.updateUpload(uploadId, { progress });
          this.emit('progress', uploadId, { progress });
          
          // Calculate estimated time remaining
          const elapsed = Date.now() - (upload.startTime || Date.now());
          const rate = progressEvent.loaded / elapsed;
          const remaining = (progressEvent.total - progressEvent.loaded) / rate;
          const estimatedTime = this.formatTimeRemaining(remaining);
          this.updateUpload(uploadId, { estimatedTime });
        }
      }
    });

    return { id: fileId, isDuplicate: false };
  }

  private async processUrl(uploadId: string, url: string): Promise<any> {
    
    // Create cancel token
    const cancelToken = axios.CancelToken.source();
    this.updateUpload(uploadId, { 
      cancelToken, 
      status: 'processing'
    });

    const response = await axiosInstance.post('/files/process-url', {
      url: url.trim()
    }, {
      timeout: UPLOAD_TIMEOUT_MS,
      cancelToken: cancelToken.token,
      onUploadProgress: (progressEvent: AxiosProgressEvent) => {
        if (progressEvent.total) {
          const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          this.updateUpload(uploadId, { progress });
          this.emit('progress', uploadId, { progress });
        }
      }
    });

    return { id: response.data.id, isDuplicate: false };
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
      cancelToken: undefined
    });

    this.processingQueue.push(uploadId);
    this.emit('retry', uploadId);
    this.processQueue();
    this.persistUploads();
  }

  cancelUpload(uploadId: string) {
    const upload = this.uploads.get(uploadId);
    if (!upload) return;

    // Cancel the request if it has a cancel token
    if (upload.cancelToken) {
      upload.cancelToken.cancel('Upload cancelled by user');
    }

    this.updateUpload(uploadId, {
      status: 'cancelled',
      error: 'Cancelled by user'
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

    completedIds.forEach(id => this.uploads.delete(id));
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
    return this.getAllUploads().filter(upload => 
      upload.status === 'uploading' || 
      upload.status === 'processing' || 
      upload.status === 'preparing'
    );
  }

  getQueuedUploads(): UploadItem[] {
    return this.getAllUploads().filter(upload => upload.status === 'queued');
  }

  // Helper methods
  private updateUpload(uploadId: string, updates: Partial<UploadItem>) {
    const upload = this.uploads.get(uploadId);
    if (!upload) return;

    Object.assign(upload, updates);
    this.uploads.set(uploadId, upload);
  }

  private generateId(): string {
    return Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
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
          cancelToken: undefined
        }
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