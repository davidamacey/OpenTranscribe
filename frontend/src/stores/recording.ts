import { writable, derived } from 'svelte/store';

// Recording state interface
export interface RecordingState {
  isRecording: boolean;
  isPaused: boolean;
  recordedBlob: Blob | null;
  recordingDuration: number;
  recordingError: string;
  recordingSupported: boolean;
  audioDevices: MediaDeviceInfo[];
  selectedDeviceId: string;
  audioLevel: number;
  recordingStartTime: number | null;
  hasActiveRecording: boolean;
  showRecordingWarningModal: boolean;
  pendingNavigationAction: (() => void) | null;
}

// Initial state
const initialState: RecordingState = {
  isRecording: false,
  isPaused: false,
  recordedBlob: null,
  recordingDuration: 0,
  recordingError: '',
  recordingSupported: false,
  audioDevices: [],
  selectedDeviceId: '',
  audioLevel: 0,
  recordingStartTime: null,
  hasActiveRecording: false,
  showRecordingWarningModal: false,
  pendingNavigationAction: null,
};

// Global recording state store
export const recordingStore = writable<RecordingState>(initialState);

// Derived stores for specific values
export const isRecording = derived(recordingStore, $store => $store.isRecording);
export const hasActiveRecording = derived(recordingStore, $store => $store.hasActiveRecording);
export const recordingDuration = derived(recordingStore, $store => $store.recordingDuration);
export const audioLevel = derived(recordingStore, $store => $store.audioLevel);
export const recordingStartTime = derived(recordingStore, $store => $store.recordingStartTime);

// Global recording manager class
export class RecordingManager {
  private static instance: RecordingManager;
  private mediaRecorder: MediaRecorder | null = null;
  private audioStream: MediaStream | null = null;
  private audioContext: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private animationFrame: number | null = null;
  private durationInterval: NodeJS.Timeout | null = null;
  private recordedChunks: Blob[] = [];

  // Recording configuration
  private readonly RECORDING_OPTIONS = {
    mimeType: 'audio/webm;codecs=opus',
    audioBitsPerSecond: 128000
  };

  private constructor() {
    this.initializeRecordingSupport();
  }

  public static getInstance(): RecordingManager {
    if (!RecordingManager.instance) {
      RecordingManager.instance = new RecordingManager();
    }
    return RecordingManager.instance;
  }

  private async initializeRecordingSupport(): Promise<void> {
    try {
      if (typeof window !== 'undefined' &&
          typeof navigator !== 'undefined' &&
          navigator.mediaDevices &&
          typeof navigator.mediaDevices.getUserMedia === 'function') {
        recordingStore.update(state => ({ ...state, recordingSupported: true }));
        await this.loadAudioDevices();
      }
    } catch (error) {
      // Recording initialization failed - recordingSupported will remain false
    }
  }

  private async loadAudioDevices(): Promise<void> {
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const audioDevices = devices.filter(device => device.kind === 'audioinput');
      
      recordingStore.update(state => ({
        ...state,
        audioDevices,
        selectedDeviceId: audioDevices[0]?.deviceId || ''
      }));
    } catch (error) {
      // Audio device enumeration failed - will use default device
    }
  }

  public async startRecording(): Promise<void> {
    let currentState: RecordingState;
    const unsubscribe = recordingStore.subscribe(state => currentState = state);
    unsubscribe();

    if (!currentState!.recordingSupported || currentState!.isRecording) {
      return;
    }

    try {
      this.recordedChunks = [];
      
      recordingStore.update(state => ({
        ...state,
        recordingError: '',
        recordingDuration: 0,
        recordingStartTime: Date.now(),
        hasActiveRecording: true,
        isPaused: false,
        isRecording: true
      }));

      // Get user media
      const constraints = {
        audio: currentState!.selectedDeviceId ? 
          { deviceId: { exact: currentState!.selectedDeviceId } } : 
          true
      };

      this.audioStream = await navigator.mediaDevices.getUserMedia(constraints);

      // Set up audio context for visualization
      this.audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
      
      if (this.audioContext.state === 'suspended') {
        await this.audioContext.resume();
      }

      const source = this.audioContext.createMediaStreamSource(this.audioStream);
      this.analyser = this.audioContext.createAnalyser();
      this.analyser.fftSize = 2048;
      this.analyser.smoothingTimeConstant = 0.8;
      source.connect(this.analyser);

      // Start audio level monitoring
      recordingStore.update(state => ({ ...state, audioLevel: 0 }));
      
      // Wait a moment for everything to be set up before starting audio monitoring
      setTimeout(() => {
        this.updateAudioLevel();
      }, 100);

      // Create MediaRecorder
      this.mediaRecorder = new MediaRecorder(this.audioStream, this.RECORDING_OPTIONS);
      
      this.mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          this.recordedChunks.push(event.data);
        }
      };

      this.mediaRecorder.onstop = () => {
        const recordedBlob = new Blob(this.recordedChunks, { type: 'audio/webm' });
        recordingStore.update(state => ({
          ...state,
          recordedBlob,
          isRecording: false,
          isPaused: false
        }));
      };

      this.mediaRecorder.start();

      // Start duration tracking
      this.durationInterval = setInterval(() => {
        recordingStore.update(state => {
          // Only increment duration if recording and not paused
          if (state.isRecording && !state.isPaused) {
            const newDuration = state.recordingDuration + 1;
            return {
              ...state,
              recordingDuration: newDuration
            };
          }
          return state; // No change if paused
        });
      }, 1000);

    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to start recording';
      recordingStore.update(state => ({
        ...state,
        recordingError: errorMessage,
        hasActiveRecording: false,
        recordingStartTime: null
      }));
      // Recording error is already stored in recordingError state
      this.cleanupRecording();
    }
  }

  public stopRecording(): void {
    if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
      this.mediaRecorder.stop();
    }

    if (this.durationInterval) {
      clearInterval(this.durationInterval);
      this.durationInterval = null;
    }

    recordingStore.update(state => ({
      ...state,
      isRecording: false,
      isPaused: false,
      audioLevel: 0
    }));

    // Keep hasActiveRecording true until user decides what to do with the recording
  }

  public clearRecording(): void {
    recordingStore.update(state => ({
      ...state,
      recordedBlob: null,
      recordingDuration: 0,
      recordingError: '',
      hasActiveRecording: false,
      recordingStartTime: null,
      audioLevel: 0
    }));
    
    this.cleanupRecording();
  }

  private cleanupRecording(): void {
    if (this.animationFrame) {
      cancelAnimationFrame(this.animationFrame);
      this.animationFrame = null;
    }

    if (this.audioStream) {
      this.audioStream.getTracks().forEach((track) => track.stop());
      this.audioStream = null;
    }

    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
    }

    this.analyser = null;
    this.recordedChunks = [];
  }

  private updateAudioLevel(): void {
    if (!this.analyser || !this.audioContext) {
      return;
    }

    let currentState: RecordingState;
    const unsubscribe = recordingStore.subscribe(state => currentState = state);
    unsubscribe();

    if (!currentState!.isRecording || currentState!.isPaused) {
      return;
    }

    try {
      const bufferLength = this.analyser.frequencyBinCount;
      const frequencyData = new Uint8Array(bufferLength);
      const timeData = new Uint8Array(this.analyser.fftSize);
      
      this.analyser.getByteFrequencyData(frequencyData);
      this.analyser.getByteTimeDomainData(timeData);
      
      // Calculate RMS level
      let rmsSum = 0;
      for (let i = 0; i < timeData.length; i++) {
        const normalized = (timeData[i] - 128) / 128;
        rmsSum += normalized * normalized;
      }
      const rmsLevel = Math.sqrt(rmsSum / timeData.length) * 100;
      
      // Calculate frequency energy
      let freqSum = 0;
      const voiceRange = Math.min(Math.floor(bufferLength / 4), bufferLength);
      for (let i = 0; i < voiceRange; i++) {
        freqSum += frequencyData[i];
      }
      const freqLevel = (freqSum / voiceRange) * (100 / 255);
      
      // Combine metrics for final audio level
      const audioLevel = Math.min(Math.max(rmsLevel + freqLevel * 0.5, 0), 100);
      
      recordingStore.update(state => ({ ...state, audioLevel }));
      
      this.animationFrame = requestAnimationFrame(() => this.updateAudioLevel());
    } catch (error) {
      // Audio level update failed - not critical for recording functionality
    }
  }

  public pauseRecording(): void {
    if (this.mediaRecorder && this.mediaRecorder.state === 'recording') {
      this.mediaRecorder.pause();
      recordingStore.update(state => ({ ...state, isPaused: true }));
    }
  }

  public resumeRecording(): void {
    if (this.mediaRecorder && this.mediaRecorder.state === 'paused') {
      this.mediaRecorder.resume();
      recordingStore.update(state => ({ ...state, isPaused: false }));
      this.updateAudioLevel();
    }
  }

  public getRecordedBlob(): Blob | null {
    let currentState: RecordingState;
    const unsubscribe = recordingStore.subscribe(state => currentState = state);
    unsubscribe();
    return currentState!.recordedBlob;
  }
}

// Export singleton instance
export const recordingManager = RecordingManager.getInstance();