/**
 * API client for AI suggestions (tags and collections)
 */
import axiosInstance from '../axios';

export interface TagSuggestion {
  name: string;
  confidence: number;
  rationale?: string;
}

export interface CollectionSuggestion {
  name: string;
  confidence: number;
  rationale?: string;
  description?: string;
}

export interface AISuggestions {
  tags: TagSuggestion[];
  collections: CollectionSuggestion[];
  status: 'pending' | 'accepted' | 'rejected';
  suggestion_id?: number;
}

/**
 * Get AI suggestions for a file (tags and collections)
 */
export async function getAISuggestions(fileId: string): Promise<AISuggestions | null> {
  try {
    const response = await axiosInstance.get(`/api/files/${fileId}/suggestions`);

    if (!response.data) {
      return null;
    }

    const data = response.data;

    // Extract tags and collections from the response
    const tags: TagSuggestion[] = (data.suggested_tags || []).map((tag: any) => ({
      name: tag.name,
      confidence: tag.confidence || 0.5,
      rationale: tag.rationale
    }));

    const collections: CollectionSuggestion[] = (data.suggested_collections || []).map((col: any) => ({
      name: col.name,
      confidence: col.confidence || 0.5,
      rationale: col.rationale,
      description: col.description
    }));

    return {
      tags,
      collections,
      status: data.status || 'pending',
      suggestion_id: data.id || data.suggestion_id
    };
  } catch (error: any) {
    if (error.response?.status === 404) {
      // No suggestions yet
      return null;
    }
    console.error('Error fetching AI suggestions:', error);
    throw error;
  }
}

/**
 * Trigger AI suggestion extraction for a file
 */
export async function extractAISuggestions(fileId: string, forceRegenerate: boolean = false): Promise<void> {
  await axiosInstance.post(`/api/files/${fileId}/extract`, { force_regenerate: forceRegenerate });
}

/**
 * Dismiss AI suggestions for a file
 */
export async function dismissAISuggestions(fileId: string): Promise<void> {
  await axiosInstance.post(`/api/files/${fileId}/suggestions/dismiss`);
}
