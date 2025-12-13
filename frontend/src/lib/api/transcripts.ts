/**
 * API client for transcript operations
 */
import axiosInstance from "../axios";
import type { Segment } from "$lib/types/speaker";

/**
 * Update the speaker assignment for a transcript segment
 * @param segmentUuid - UUID of the transcript segment to update
 * @param speakerUuid - UUID of the speaker to assign (or null to unassign)
 * @returns Updated transcript segment with speaker information
 */
export async function updateSegmentSpeaker(
  segmentUuid: string,
  speakerUuid: string | null,
): Promise<Segment> {
  try {
    const response = await axiosInstance.put(
      `/transcripts/segments/${segmentUuid}/speaker`,
      {
        speaker_uuid: speakerUuid,
      },
    );
    return response.data;
  } catch (error: unknown) {
    console.error("Error updating segment speaker:", error);
    throw error;
  }
}
