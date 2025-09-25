/**
 * Enhanced clipboard utility that works reliably across localhost and IP addresses
 * Provides fallback methods for secure/non-secure contexts
 */

export interface CopyResult {
  success: boolean;
  error?: string;
}

/**
 * Copy text to clipboard with IP address and non-secure context support
 * @param text - Text to copy to clipboard
 * @param onSuccess - Callback for successful copy
 * @param onError - Callback for copy failure
 */
export async function copyToClipboard(
  text: string,
  onSuccess?: () => void,
  onError?: (error: string) => void
): Promise<CopyResult> {
  if (!text) {
    const error = 'No content to copy';
    onError?.(error);
    return { success: false, error };
  }

  // Check if we're on IP address or non-localhost and use fallback immediately
  const isIPAddress = /^\d+\.\d+\.\d+\.\d+/.test(window.location.hostname);
  const isNonSecureContext = !window.isSecureContext;

  if (isIPAddress || isNonSecureContext || !navigator.clipboard) {
    return copyWithFallback(text, onSuccess, onError);
  }

  // Try modern clipboard API first
  try {
    await navigator.clipboard.writeText(text);
    onSuccess?.();
    return { success: true };
  } catch (err) {
    return copyWithFallback(text, onSuccess, onError);
  }
}

/**
 * Fallback copy method using execCommand for non-secure contexts
 */
function copyWithFallback(
  text: string,
  onSuccess?: () => void,
  onError?: (error: string) => void
): CopyResult {
  try {
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.left = '-999999px';
    textArea.style.top = '-999999px';
    textArea.style.opacity = '0';
    textArea.style.pointerEvents = 'none';
    textArea.setAttribute('readonly', '');
    document.body.appendChild(textArea);

    // Select the text
    textArea.focus();
    textArea.select();
    textArea.setSelectionRange(0, textArea.value.length);

    // Execute copy command
    const successful = document.execCommand('copy');
    document.body.removeChild(textArea);

    if (successful) {
      onSuccess?.();
      return { success: true };
    } else {
      throw new Error('execCommand copy failed');
    }
  } catch (fallbackError) {
    const error = 'Copy operation failed';
    onError?.(error);
    return { success: false, error };
  }
}

/**
 * Show manual copy modal as final fallback
 */
export function showManualCopyModal(text: string, title: string = 'Copy Content'): void {
  const modal = document.createElement('div');
  modal.style.cssText = `
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0,0,0,0.8);
    z-index: 10000;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
  `;

  const content = document.createElement('div');
  content.style.cssText = `
    background: white;
    border-radius: 8px;
    padding: 20px;
    max-width: 80%;
    max-height: 80%;
    overflow: auto;
  `;

  const titleElement = document.createElement('h3');
  titleElement.textContent = title;
  titleElement.style.marginTop = '0';

  const instructions = document.createElement('p');
  instructions.textContent = 'Select all text below and copy manually:';

  const textArea = document.createElement('textarea');
  textArea.value = text;
  textArea.style.cssText = `
    width: 100%;
    height: 300px;
    font-family: monospace;
    font-size: 12px;
    border: 1px solid #ccc;
    padding: 10px;
  `;
  textArea.select();

  const closeButton = document.createElement('button');
  closeButton.textContent = 'Close';
  closeButton.style.cssText = `
    margin-top: 10px;
    padding: 8px 16px;
    background: #007bff;
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
  `;

  closeButton.onclick = () => {
    document.body.removeChild(modal);
  };

  content.appendChild(titleElement);
  content.appendChild(instructions);
  content.appendChild(textArea);
  content.appendChild(closeButton);
  modal.appendChild(content);
  document.body.appendChild(modal);

  // Auto-select the text
  textArea.focus();
  textArea.select();
}