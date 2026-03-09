/**
 * Consistent ID generation utilities.
 *
 * Replaces inconsistent Math.random() and Date.now() patterns
 * scattered across upload and extraction services.
 */

/**
 * Generate a unique ID with an optional prefix.
 *
 * Uses crypto.randomUUID() when available, with a fallback
 * for environments that don't support it.
 */
export function generateId(prefix?: string): string {
  const id =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).substring(2, 15)}`;

  return prefix ? `${prefix}-${id}` : id;
}
