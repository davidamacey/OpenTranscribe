import { writable } from 'svelte/store';

export interface ToastMessage {
  id: string;
  message: string;
  type: 'success' | 'error' | 'info' | 'warning';
  duration?: number;
}

let toastCounter = 0;

function createToastStore() {
  const { subscribe, update } = writable<ToastMessage[]>([]);

  return {
    subscribe,

    show(message: string, type: ToastMessage['type'] = 'success', duration = 3000) {
      const id = `${Date.now()}-${++toastCounter}`;
      const toast: ToastMessage = { id, message, type, duration };

      update((toasts) => [...toasts, toast]);

      // Auto-remove after duration
      if (duration > 0) {
        setTimeout(() => {
          this.dismiss(id);
        }, duration);
      }
    },

    dismiss(id: string) {
      update((toasts) => toasts.filter((t) => t.id !== id));
    },

    success(message: string, duration?: number) {
      this.show(message, 'success', duration);
    },

    error(message: string, duration?: number) {
      // Errors get longer duration (8 seconds) to allow reading
      this.show(message, 'error', duration ?? 8000);
    },

    warning(message: string, duration?: number) {
      this.show(message, 'warning', duration);
    },

    info(message: string, duration?: number) {
      this.show(message, 'info', duration);
    },
  };
}

export const toastStore = createToastStore();
