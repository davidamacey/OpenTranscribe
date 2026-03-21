/**
 * Shared media file types used across gallery components.
 */

export interface MediaFile {
  uuid: string;
  filename: string;
  status:
    | 'pending'
    | 'processing'
    | 'completed'
    | 'error'
    | 'cancelling'
    | 'cancelled'
    | 'orphaned';
  upload_time: string;
  duration?: number;
  file_size?: number;
  content_type?: string;
  tags?: string[];
  summary?: string;
  file_hash?: string;
  thumbnail_url?: string;
  last_error_message?: string;

  // Formatted fields from backend
  formatted_duration?: string;
  formatted_upload_date?: string;
  formatted_file_age?: string;
  formatted_file_size?: string;
  display_status?: string;
  status_badge_class?: string;

  // Error handling fields from backend
  error_category?: string;
  error_suggestions?: string[];
  user_message?: string;
  is_retryable?: boolean;

  // Technical metadata
  media_format?: string;
  codec?: string;
  resolution_width?: number;
  resolution_height?: number;
  frame_rate?: number;
  frame_count?: number;
  aspect_ratio?: string;

  // Audio specs
  audio_channels?: number;
  audio_sample_rate?: number;
  audio_bit_depth?: number;

  // Creation info
  creation_date?: string;
  last_modified_date?: string;
  device_make?: string;
  device_model?: string;

  // Content info
  title?: string;
  author?: string;
  description?: string;

  // Speaker summary from backend
  speaker_summary?: {
    count: number;
    primary_speakers: string[];
  };

  // Diarization
  diarization_disabled?: boolean;
}

export interface DurationRange {
  min: number | null;
  max: number | null;
}

export interface DateRange {
  from: Date | null;
  to: Date | null;
}
