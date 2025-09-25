/**
 * Speaker Color Store
 *
 * Reactive Svelte store that maintains consistent speaker-to-color mappings
 * across all components. This ensures that SPEAKER_01, SPEAKER_02, etc.
 * always have the same colors regardless of user-assigned labels.
 */

import { writable, get } from 'svelte/store';
import { getSpeakerColor } from '$lib/utils/speakerColors';

interface SpeakerColorMapping {
  [speakerId: string]: {
    bg: string;
    border: string;
    textLight: string;
    textDark: string;
  };
}

// Create the reactive store
const speakerColorMappings = writable<SpeakerColorMapping>({});

/**
 * Get consistent color for a speaker by their original ID
 * This function ensures colors are cached and consistent
 */
export function getSpeakerColorFromStore(speakerId: string) {
  // Get current mappings using get() to avoid memory leak
  const currentMappings = get(speakerColorMappings);

  // If we already have a color for this speaker, return it
  if (currentMappings[speakerId]) {
    return currentMappings[speakerId];
  }

  // Generate new color using the utility function
  const color = getSpeakerColor(speakerId);

  // Store the color for future consistency
  speakerColorMappings.update(mappings => ({
    ...mappings,
    [speakerId]: color
  }));

  return color;
}

/**
 * Clear all speaker color mappings (useful for testing or reset)
 */
export function clearSpeakerColorMappings() {
  speakerColorMappings.set({});
}

/**
 * Get the reactive store for components that need to subscribe to changes
 */
export { speakerColorMappings };

/**
 * Helper function to get speaker color from various data sources
 * Tries to find the original speaker ID from different object structures
 */
export function getSpeakerColorSmart(speakerData: any) {
  // Try different ways to get the original speaker ID
  const speakerId =
    speakerData?.speaker_label ||  // For transcript segments (now contains original ID)
    speakerData?.name ||           // For speaker objects
    speakerData?.speaker?.name ||  // For nested speaker objects
    speakerData ||                 // If speakerData is just a string
    'Unknown';

  return getSpeakerColorFromStore(speakerId);
}