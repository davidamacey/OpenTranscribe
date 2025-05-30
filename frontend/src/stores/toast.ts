import { writable } from 'svelte/store';

export interface ToastMessage {
  id: string;
  message: string;
  type: 'success' | 'error' | 'info' | 'warning';
  duration?: number;
}

function createToastStore() {
  const { subscribe, update } = writable<ToastMessage[]>([]);

  return {
    subscribe,
    
    show(message: string, type: ToastMessage['type'] = 'success', duration = 3000) {
      const id = Date.now().toString();
      const toast: ToastMessage = { id, message, type, duration };
      
      update(toasts => [...toasts, toast]);
      
      // Auto-remove after duration
      if (duration > 0) {
        setTimeout(() => {
          this.dismiss(id);
        }, duration);
      }
    },
    
    dismiss(id: string) {
      update(toasts => toasts.filter(t => t.id !== id));
    },
    
    success(message: string, duration?: number) {
      this.show(message, 'success', duration);
    },
    
    error(message: string, duration?: number) {
      this.show(message, 'error', duration);
    },
    
    warning(message: string, duration?: number) {
      this.show(message, 'warning', duration);
    },
    
    info(message: string, duration?: number) {
      this.show(message, 'info', duration);
    }
  };
}

export const toastStore = createToastStore();