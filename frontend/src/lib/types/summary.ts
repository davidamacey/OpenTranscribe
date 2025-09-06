/**
 * TypeScript types for AI-generated summaries
 * 
 * Defines the structure for BLUF-format summaries and related data
 * used throughout the frontend application.
 */

export interface SpeakerInfo {
  name: string;
  talk_time_seconds: number;
  percentage: number;
  key_points: string[];
}

export interface ContentSection {
  time_range: string;
  topic: string;
  key_points: string[];
}

export interface MajorTopic {
  topic: string;
  importance: 'high' | 'medium' | 'low';
  key_points: string[];
  participants: string[];
}

export interface ActionItem {
  text: string;
  assigned_to: string | null;
  due_date: string | null;
  priority: 'high' | 'medium' | 'low';
  context: string;
  status?: 'pending' | 'completed' | 'cancelled';
}

export interface SummaryMetadata {
  provider: string;
  model: string;
  usage_tokens?: number;
  transcript_length: number;
  processing_time_ms?: number;
  confidence_score?: number;
  language?: string;
  error?: string;
}

export interface SummaryData {
  bluf: string;
  brief_summary: string;
  major_topics: MajorTopic[];
  action_items: ActionItem[];
  key_decisions: string[];
  follow_up_items: string[];
  metadata: SummaryMetadata;
}

export interface SummaryResponse {
  file_id: number;
  summary_data: SummaryData;
  source: 'opensearch' | 'postgresql';
  document_id?: string;
  created_at?: string;
  updated_at?: string;
}

export interface SummarySearchHit {
  document_id: string;
  score: number;
  file_id: number;
  bluf: string;
  brief_summary: string;
  created_at: string;
  provider: string;
  model: string;
  highlights?: {
    [field: string]: string[];
  };
}

export interface SummarySearchResponse {
  hits: SummarySearchHit[];
  total: number;
  max_score?: number;
  query: string;
  filters: Record<string, any>;
}

export interface SpeakerIdentificationResponse {
  message: string;
  task_id: string;
  file_id: number;
  speaker_count: number;
}

// UI-specific types
export interface SummaryModalState {
  isOpen: boolean;
  loading: boolean;
  error: string | null;
  summary: SummaryData | null;
}

export interface SummaryTask {
  task_id: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  progress?: number;
  error_message?: string;
}