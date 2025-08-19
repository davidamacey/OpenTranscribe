/**
 * Utility functions for highlighting search matches in transcript text
 */

export interface SearchMatch {
  segmentIndex: number;
  start: number;
  length: number;
  type: 'text' | 'speaker';
}

/**
 * Highlights search matches in a text string
 * @param text - The original text
 * @param query - The search query
 * @param isCurrentMatch - Whether this is the currently selected match
 * @returns HTML string with highlighted matches
 */
export function highlightText(text: string, query: string, isCurrentMatch: boolean = false): string {
  if (!text || !query?.trim()) {
    return escapeHtml(text || '');
  }
  
  const normalizedQuery = query.toLowerCase();
  const normalizedText = text.toLowerCase();
  
  let result = '';
  let lastIndex = 0;
  
  // Find all matches
  let index = normalizedText.indexOf(normalizedQuery);
  while (index !== -1) {
    // Add text before the match
    result += escapeHtml(text.substring(lastIndex, index));
    
    // Add highlighted match
    const matchText = text.substring(index, index + query.length);
    const highlightClass = isCurrentMatch ? 'transcript-search-highlight current' : 'transcript-search-highlight';
    result += `<span class="${highlightClass}">${escapeHtml(matchText)}</span>`;
    
    lastIndex = index + query.length;
    index = normalizedText.indexOf(normalizedQuery, lastIndex);
  }
  
  // Add remaining text
  result += escapeHtml(text.substring(lastIndex));
  
  return result;
}

/**
 * Checks if a text contains a search query
 * @param text - The text to search in
 * @param query - The search query
 * @returns Whether the text contains the query
 */
export function textContainsQuery(text: string, query: string): boolean {
  if (!text || !query?.trim()) return false;
  return text.toLowerCase().includes(query.toLowerCase());
}

/**
 * Escapes HTML special characters to prevent XSS
 * @param text - The text to escape
 * @returns HTML-safe text
 */
function escapeHtml(text: string): string {
  if (!text) return '';
  if (typeof window === 'undefined') return text; // SSR safety
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

/**
 * Gets the index of the current match for a specific segment
 * @param segmentIndex - Index of the segment
 * @param matches - Array of all search matches
 * @param currentMatchIndex - Index of the currently selected match
 * @returns The match index within this segment, or -1 if not current
 */
export function getCurrentMatchInSegment(
  segmentIndex: number, 
  matches: SearchMatch[], 
  currentMatchIndex: number
): number {
  if (currentMatchIndex < 0 || currentMatchIndex >= matches.length) {
    return -1;
  }
  
  const currentMatch = matches[currentMatchIndex];
  if (currentMatch.segmentIndex !== segmentIndex) {
    return -1;
  }
  
  // Find which match in this segment is the current one
  const segmentMatches = matches.filter(m => m.segmentIndex === segmentIndex);
  return segmentMatches.findIndex(m => m === currentMatch);
}

/**
 * Highlights text with multiple matches, marking one as current
 * @param text - The original text
 * @param query - The search query
 * @param segmentIndex - Index of the current segment
 * @param matches - Array of all search matches
 * @param currentMatchIndex - Index of the currently selected match
 * @returns HTML string with highlighted matches
 */
export function highlightTextWithMatches(
  text: string,
  query: string,
  segmentIndex: number,
  matches: SearchMatch[],
  currentMatchIndex: number
): string {
  if (!query.trim()) {
    return escapeHtml(text);
  }
  
  // Get matches for this specific segment
  const segmentMatches = matches.filter(m => 
    m.segmentIndex === segmentIndex && m.type === 'text'
  ).sort((a, b) => a.start - b.start);
  
  if (segmentMatches.length === 0) {
    return escapeHtml(text);
  }
  
  // Determine which match is current
  const currentMatch = currentMatchIndex >= 0 && currentMatchIndex < matches.length 
    ? matches[currentMatchIndex] 
    : null;
  
  let result = '';
  let lastIndex = 0;
  
  segmentMatches.forEach((match) => {
    // Add text before the match
    result += escapeHtml(text.substring(lastIndex, match.start));
    
    // Add highlighted match
    const matchText = text.substring(match.start, match.start + match.length);
    const isCurrentMatch = currentMatch && 
      match.segmentIndex === currentMatch.segmentIndex && 
      match.start === currentMatch.start &&
      match.type === currentMatch.type;
    
    const highlightClass = isCurrentMatch ? 'transcript-search-highlight current' : 'transcript-search-highlight';
    result += `<span class="${highlightClass}">${escapeHtml(matchText)}</span>`;
    
    lastIndex = match.start + match.length;
  });
  
  // Add remaining text
  result += escapeHtml(text.substring(lastIndex));
  
  return result;
}

/**
 * Highlights speaker names with search matches
 * @param speakerName - The speaker name to highlight
 * @param query - The search query
 * @param segmentIndex - Index of the current segment
 * @param matches - Array of all search matches
 * @param currentMatchIndex - Index of the currently selected match
 * @returns HTML string with highlighted speaker name
 */
export function highlightSpeakerName(
  speakerName: string,
  query: string,
  segmentIndex: number,
  matches: SearchMatch[],
  currentMatchIndex: number
): string {
  if (!query.trim()) {
    return escapeHtml(speakerName);
  }
  
  // Check if there's a speaker match for this segment
  const speakerMatch = matches.find(m => 
    m.segmentIndex === segmentIndex && m.type === 'speaker'
  );
  
  if (!speakerMatch) {
    return escapeHtml(speakerName);
  }
  
  // Determine if this is the current match
  const currentMatch = currentMatchIndex >= 0 && currentMatchIndex < matches.length 
    ? matches[currentMatchIndex] 
    : null;
  
  const isCurrentMatch = !!(currentMatch && 
    speakerMatch.segmentIndex === currentMatch.segmentIndex && 
    speakerMatch.type === currentMatch.type);
  
  return highlightText(speakerName, query, isCurrentMatch);
}