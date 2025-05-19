import { format } from 'date-fns';

/**
 * Formats a duration in seconds into a HH:MM:SS or MM:SS string.
 * @param {number} totalSeconds - The duration in seconds.
 * @returns {string} The formatted duration string.
 */
export function formatDuration(totalSeconds: number): string {
  if (isNaN(totalSeconds) || totalSeconds < 0) {
    return '00:00';
  }

  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = Math.floor(totalSeconds % 60);

  const paddedMinutes = String(minutes).padStart(2, '0');
  const paddedSeconds = String(seconds).padStart(2, '0');

  if (hours > 0) {
    const paddedHours = String(hours).padStart(2, '0');
    return `${paddedHours}:${paddedMinutes}:${paddedSeconds}`;
  } else {
    return `${paddedMinutes}:${paddedSeconds}`;
  }
}

/**
 * Formats a timestamp (Date object, string, or number) into YYYY-MM-DD HH:MM:SS.mmm format.
 * @param {string | number | Date} timestamp - The timestamp to format.
 * @returns {string} The formatted timestamp string with milliseconds.
 */
export function formatTimestampWithMillis(timestamp: string | number | Date): string {
  try {
    const date = new Date(timestamp);
    if (isNaN(date.getTime())) {
      return 'Invalid Date';
    }
    const mainPart = format(date, 'yyyy-MM-dd HH:mm:ss');
    const milliseconds = String(date.getMilliseconds()).padStart(3, '0');
    return `${mainPart}.${milliseconds}`;
  } catch (error) {
    console.error("Error formatting timestamp:", error);
    return 'Invalid Date';
  }
}
