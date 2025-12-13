/**
 * TypeScript types for Speaker-related operations
 */

/**
 * Speaker entity representing a speaker instance in a media file
 */
export interface Speaker {
  uuid: string;
  id?: string; // Same as uuid, kept for backward compatibility
  name: string; // Original speaker ID (e.g., "SPEAKER_01")
  display_name?: string; // User-assigned display name
  verified?: boolean;
  confidence?: number;
  segment_count?: number; // Number of segments assigned to this speaker
  profile?: {
    id: string;
    name: string;
    description?: string;
  };
  // Backend computed fields
  computed_status?: string;
  status_text?: string;
  status_color?: string;
  resolved_display_name?: string;
}

/**
 * Transcript segment with speaker information
 */
export interface Segment {
  uuid?: string;
  id: number | string;
  start_time: number;
  end_time: number;
  text: string;
  speaker_id?: string; // UUID
  speaker_label?: string;
  resolved_speaker_name?: string;
  speaker?: {
    id: string; // UUID
    uuid?: string;
    name: string;
    display_name?: string;
  };
  formatted_timestamp?: string;
  display_timestamp?: string;
}

/**
 * Result of a merge operation for a single speaker
 */
export interface MergeResult {
  speaker: Speaker;
  success: boolean;
  error?: string;
}

/**
 * Response from the merge speakers API
 */
export interface MergeSpeakersResponse {
  uuid: string;
  name: string;
  display_name?: string;
  verified: boolean;
  segment_count: number;
}
