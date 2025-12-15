import { writable, derived } from "svelte/store";

export interface TranscriptSegment {
  uuid: string; // UUID identifier
  start_time: number;
  end_time: number;
  text: string;
  speaker_id?: string; // UUID
  speaker_label?: string;
  resolved_speaker_name?: string;
  speaker?: {
    uuid: string; // UUID
    name: string;
    display_name?: string;
  };
  formatted_timestamp?: string;
  display_timestamp?: string;
}

export interface SpeakerInfo {
  uuid: string; // UUID (public identifier)
  name: string; // Original speaker ID (e.g., "SPEAKER_01")
  display_name?: string; // User-assigned display name
  verified: boolean;
}

export interface TranscriptData {
  fileId: string | null; // UUID
  segments: TranscriptSegment[];
  speakers: SpeakerInfo[];
}

// Create the writable store
const createTranscriptStore = () => {
  const { subscribe, set, update } = writable<TranscriptData>({
    fileId: null,
    segments: [],
    speakers: [],
  });

  return {
    subscribe,
    // Load initial data for a file
    loadTranscriptData: (
      fileId: string,
      segments: TranscriptSegment[],
      speakers: SpeakerInfo[],
    ) => {
      set({
        fileId,
        segments: segments.map((segment) => ({ ...segment })),
        speakers: speakers.map((speaker) => ({ ...speaker })),
      });
    },

    // Update a speaker's display name
    updateSpeakerName: (speakerId: string, newDisplayName: string) => {
      update((data) => {
        // Update speaker in speakers array
        const updatedSpeakers = data.speakers.map((speaker) =>
          speaker.uuid === speakerId
            ? { ...speaker, display_name: newDisplayName }
            : speaker,
        );

        // Update all segments for this speaker
        const updatedSegments = data.segments.map((segment) => {
          if (segment.speaker_id === speakerId) {
            return {
              ...segment,
              resolved_speaker_name: newDisplayName,
              speaker: segment.speaker
                ? {
                    ...segment.speaker,
                    uuid: segment.speaker.uuid,
                    name: segment.speaker.name, // Keep original name for color consistency
                    display_name: newDisplayName,
                  }
                : {
                    uuid: speakerId,
                    name: segment.speaker_label || `SPEAKER_${speakerId}`,
                    display_name: newDisplayName,
                  },
            };
          }
          return segment;
        });

        return {
          ...data,
          speakers: updatedSpeakers,
          segments: updatedSegments,
        };
      });
    },

    // Clear store when navigating away
    clear: () => {
      set({
        fileId: null,
        segments: [],
        speakers: [],
      });
    },

    // Update segments (for text edits, etc.)
    updateSegments: (newSegments: TranscriptSegment[]) => {
      update((data) => ({
        ...data,
        segments: newSegments.map((segment) => ({ ...segment })),
      }));
    },

    // Update a specific segment's text while preserving ALL other data
    updateSegmentText: (segmentUuid: string, newText: string) => {
      update((data) => {
        const updatedSegments = data.segments.map((segment) => {
          if (segment.uuid === segmentUuid) {
            // Preserve ALL existing segment data, only update text
            return {
              ...segment, // Keep all existing properties
              text: newText, // Only update the text field
              // Preserve: speaker_id, speaker_label, speaker, resolved_speaker_name, etc.
            };
          }
          return segment;
        });

        return {
          ...data,
          segments: updatedSegments,
        };
      });
    },
  };
};

// Export the store instance
export const transcriptStore = createTranscriptStore();

// Derived store for processed segments suitable for TranscriptModal display
export const processedTranscriptSegments = derived(
  transcriptStore,
  ($transcriptStore) => {
    if (!$transcriptStore.segments.length) {
      return [];
    }

    // Sort segments by start_time
    const sortedSegments = [...$transcriptStore.segments].sort((a, b) => {
      const aStart = parseFloat(String(a.start_time || 0));
      const bStart = parseFloat(String(b.start_time || 0));
      return aStart - bStart;
    });

    // Group consecutive segments from the same speaker for display
    const groupedSegments = [];
    let currentSpeaker = null;
    let currentSpeakerLabel = null;
    let currentText = [];
    let currentStartTime = null;
    let currentEndTime = null;

    sortedSegments.forEach((segment) => {
      // Use the latest speaker display name from the store
      const speakerName =
        segment.resolved_speaker_name ||
        segment.speaker?.display_name ||
        segment.speaker?.name ||
        segment.speaker_label ||
        "Unknown Speaker";
      const speakerLabel =
        segment.speaker_label || segment.speaker?.name || "Unknown";
      const startTime = parseFloat(String(segment.start_time || 0));
      const endTime = parseFloat(String(segment.end_time || 0));

      if (speakerName !== currentSpeaker) {
        if (currentSpeaker && currentText.length > 0) {
          groupedSegments.push({
            speakerName: currentSpeaker,
            speaker_label: currentSpeakerLabel, // Original ID for color mapping
            text: currentText.join(" "),
            startTime: currentStartTime,
            endTime: currentEndTime,
          });
        }
        currentSpeaker = speakerName;
        currentSpeakerLabel = speakerLabel; // Store original speaker ID (e.g., "SPEAKER_01")
        currentText = [segment.text];
        currentStartTime = startTime;
        currentEndTime = endTime;
      } else {
        currentText.push(segment.text);
        currentEndTime = endTime; // Update end time to last segment
      }
    });

    // Add the last speaker block
    if (currentSpeaker && currentText.length > 0) {
      groupedSegments.push({
        speakerName: currentSpeaker,
        speaker_label: currentSpeakerLabel, // Preserve for color mapping
        text: currentText.join(" "),
        startTime: currentStartTime,
        endTime: currentEndTime,
      });
    }

    return groupedSegments;
  },
);
