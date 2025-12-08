/**
 * API client for speaker operations
 */
import axiosInstance from '../axios';

/**
 * Merge a source speaker into a target speaker
 * @param sourceUuid - UUID of the speaker to merge (will be deleted)
 * @param targetUuid - UUID of the speaker to keep (will receive all segments)
 * @returns Updated target speaker
 */
export async function mergeSpeakers(sourceUuid: string, targetUuid: string): Promise<any> {
  try {
    const response = await axiosInstance.post(`/speakers/${sourceUuid}/merge/${targetUuid}`);
    return response.data;
  } catch (error: any) {
    console.error('Error merging speakers:', error);
    throw error;
  }
}
