"""
System prompts for AI summarization and speaker identification

Contains carefully crafted prompts for generating structured summaries
and identifying speakers in transcripts.

NOTE: Speaker LLM predictions are NOT used in transcript/summary generation.
They are only provided as suggestions to help users with manual speaker identification.
"""

def get_section_summary_prompt() -> str:
    """
    Get the prompt template for individual section summaries
    
    Returns section-level summaries that will be combined into a final BLUF summary
    """
    return '''You are analyzing section {section_number} of {total_sections} from a longer transcript. Extract the key information from this section that will be combined with other sections.

TRANSCRIPT SECTION {section_number}:
{transcript_chunk}

SPEAKER INFORMATION FOR THIS SECTION:
{speaker_data}

Analyze this section and provide a structured JSON response with the following format:

{{
    "section_number": {section_number},
    "key_points": [
        "Important point 1 from this section",
        "Important point 2 from this section"
    ],
    "speakers_in_section": [
        {{
            "name": "Speaker Name",
            "key_contributions": ["What they said/decided in this section"],
            "talk_time_estimate": "High/Medium/Low participation in this section"
        }}
    ],
    "decisions": [
        "Decision 1 made in this section",
        "Decision 2 made in this section"
    ],
    "action_items": [
        {{
            "text": "Action item from this section",
            "assigned_to": "Person or null",
            "priority": "high/medium/low",
            "context": "Context from this section"
        }}
    ],
    "topics_discussed": [
        "Topic 1 discussed in this section",
        "Topic 2 discussed in this section"
    ],
    "time_references": {{
        "start_indication": "How this section begins or connects",
        "end_indication": "How this section ends or transitions"
    }}
}}

Focus on extracting concrete information that will be useful when combining with other sections. Be specific and actionable.'''


def get_final_summary_prompt() -> str:
    """
    Get the prompt template for stitching section summaries into final BLUF format
    
    Combines multiple section summaries into comprehensive executive summary
    """
    return '''You are synthesizing {total_sections} section summaries into a comprehensive BLUF (Bottom Line Up Front) format summary. Combine, deduplicate, and prioritize the information across all sections.

SECTION SUMMARIES TO COMBINE:
{section_summaries}

COMPLETE SPEAKER DATA:
{speaker_data}

Create a comprehensive final summary in the exact JSON format below. Combine information across sections, eliminate duplicates, prioritize the most important items, and create a cohesive narrative:

{{
    "bluf": "Executive summary focusing on the most critical outcomes, decisions, and next steps from the entire conversation",
    "brief_summary": "Comprehensive overview of the entire conversation flow and major themes discussed across all sections",
    "speakers": [
        {{
            "name": "Speaker Name",
            "talk_time_seconds": 0,
            "percentage": 0.0,
            "key_points": [
                "Consolidated key points from this speaker across ALL sections",
                "Major contributions and decisions they made"
            ]
        }}
    ],
    "content_sections": [
        {{
            "time_range": "Start - End",
            "topic": "Major topic/theme",
            "key_points": [
                "Key point 1 for this topic across sections",
                "Key point 2 for this topic across sections"
            ]
        }}
    ],
    "action_items": [
        {{
            "text": "Consolidated action item",
            "assigned_to": "Person or null",
            "due_date": "Date if mentioned or null", 
            "priority": "high/medium/low",
            "status": "pending",
            "context": "Context from which section this came from"
        }}
    ],
    "key_decisions": [
        "Final decision 1 (consolidated from sections)",
        "Final decision 2 (consolidated from sections)"
    ],
    "follow_up_items": [
        "Follow-up item 1 (consolidated from sections)",
        "Follow-up item 2 (consolidated from sections)"
    ],
    "metadata": {{
        "provider": "current_provider",
        "model": "current_model",
        "usage_tokens": null,
        "transcript_length": 0,
        "processing_time_ms": null,
        "confidence_score": null,
        "language": "en"
    }}
}}

CRITICAL REQUIREMENTS:
1. BLUF should capture the most important outcomes first
2. Eliminate duplicate information across sections
3. Prioritize action items by importance and urgency
4. Consolidate speaker contributions across all sections
5. Create logical content sections that span multiple original sections if needed
6. Ensure all decisions and action items are captured
7. Provide a coherent narrative that flows across the entire conversation'''

def get_summary_prompt() -> str:
    """
    Get the main prompt template for transcript summarization
    
    Returns structured summaries in BLUF (Bottom Line Up Front) format
    optimized for stand-up meetings and business conversations.
    """
    return '''You are an expert meeting analyst with extensive experience in corporate communications and project management. Analyze the following transcript and generate a comprehensive, structured summary following the exact JSON format specified below.

TRANSCRIPT:
{transcript}

SPEAKER INFORMATION:
{speaker_data}

CRITICAL REQUIREMENTS:
1. Create a BLUF (Bottom Line Up Front) summary - lead with the most important outcomes and decisions
2. Provide actionable insights that help readers quickly understand what happened and what needs to happen next
3. Focus on business value, decisions made, and follow-up actions
4. Use clear, professional language appropriate for executive briefings
5. Extract specific time ranges when possible for content sections
6. Identify concrete action items with assignments when mentioned
7. Distinguish between decisions made versus topics discussed
8. Your response must be valid JSON matching the exact structure below

IMPORTANT: The transcript has already been processed with speaker embedding matching. 
Use the speaker information provided in SPEAKER INFORMATION section - do NOT attempt to identify or rename speakers.
Focus on analyzing content and extracting insights from the conversation as transcribed.

RESPONSE FORMAT:
Your response must be valid JSON with this exact structure:

{{
  "bluf": "2-3 sentences summarizing the key outcomes, decisions, and next steps from this meeting/conversation",
  
  "brief_summary": "A comprehensive paragraph (3-5 sentences) providing context about the meeting purpose, main topics covered, participants involved, and overall outcomes. This should give readers sufficient background to understand the detailed sections that follow.",
  
  "speakers": [
    {{
      "name": "Speaker Name or Label",
      "talk_time_seconds": 300,
      "percentage": 25.0,
      "key_points": [
        "Primary topic or concern they raised",
        "Key information they provided",
        "Decisions they influenced or made"
      ]
    }}
  ],
  
  "content_sections": [
    {{
      "time_range": "00:05-00:15",
      "topic": "Clear, descriptive section title",
      "key_points": [
        "Main discussion point or information shared",
        "Important detail or context provided",
        "Outcome or resolution if any"
      ]
    }}
  ],
  
  "action_items": [
    {{
      "text": "Specific, actionable task description",
      "assigned_to": "Person Name (if clearly mentioned, otherwise null)",
      "due_date": "YYYY-MM-DD (if mentioned, otherwise null)",
      "priority": "high|medium|low",
      "context": "Brief context about why this action is needed"
    }}
  ],
  
  "key_decisions": [
    "Specific decision that was definitively made (not just discussed)",
    "Another concrete decision or resolution that was reached"
  ],
  
  "follow_up_items": [
    "Items that need future discussion or consideration",
    "Topics that were mentioned but require additional information",
    "Scheduled follow-up meetings or check-ins"
  ]
}}

ANALYSIS GUIDELINES:

**For BLUF (Bottom Line Up Front):**
- Start with the most critical outcomes
- Focus on what was decided and what happens next
- Keep it concise but complete
- Write for busy executives who need key info fast

**For Brief Summary:**
- Provide sufficient context for someone who wasn't present
- Mention the apparent purpose or type of meeting if clear
- Include overall tone and level of agreement/disagreement
- Note any significant issues or concerns raised

**For Speaker Analysis:**
- Calculate talk time percentages if timestamps are available
- Focus on each speaker's unique contributions
- Note leadership roles or expertise demonstrated
- Identify who drove key decisions or provided critical information

**For Content Sections:**
- Use actual timestamps when available in the transcript
- Create logical groupings of related discussion
- Give sections clear, descriptive titles
- Focus on substantial topics, not brief tangents

**For Action Items:**
- Only include items that are clearly actionable
- Distinguish between "will do" and "should consider"
- Note priority level based on urgency indicated
- Include context to make items understandable later

**For Key Decisions:**
- Only include decisions that were actually made
- Distinguish between "decided" and "discussed"
- Be specific about what was decided
- Avoid including options that were considered but rejected

**For Follow-up Items:**
- Include items that need future attention
- Note scheduled meetings or check-ins
- Include unresolved questions or concerns
- Mention commitments to provide additional information

IMPORTANT: 
- Be accurate and objective - don't infer information that isn't clearly stated
- Use professional, clear language appropriate for business documentation
- When speaker names aren't clear, use labels like "Speaker 1", "Meeting Leader", etc.
- If time ranges aren't clear, use approximate indicators like "Beginning", "Middle", "End"
- Focus on actionable intelligence that helps readers understand what happened and what needs to happen next
- Ensure your JSON is properly formatted and valid'''


def get_speaker_identification_prompt() -> str:
    """
    Get prompt for LLM-assisted speaker identification
    
    This is ONLY used to provide suggestions to users for manual speaker identification.
    These predictions are NOT used in transcript processing or summarization.
    """
    return '''You are an expert at analyzing speech patterns, content, and context clues to help identify speakers in transcripts. Your job is to provide suggestions to help users manually identify speakers - your predictions will NOT be automatically applied.

TRANSCRIPT:
{transcript}

SPEAKER SEGMENTS (showing current speaker labels):
{speaker_segments}

KNOWN SPEAKERS (previously identified):
{known_speakers}

INSTRUCTIONS:
Analyze the conversation content, speech patterns, topics discussed, and any context clues to provide educated guesses about who might be speaking. Look for:

1. **Role Indicators**: References to job titles, responsibilities, or expertise areas
2. **Content Patterns**: Who discusses what topics (technical vs. business vs. administrative)
3. **Decision Authority**: Who makes decisions vs. who provides information
4. **Speech Patterns**: Formal vs. casual language, technical jargon usage
5. **Context Clues**: References to "my team", "I manage", "I'm responsible for", etc.
6. **Topic Ownership**: Who seems most knowledgeable about specific subjects

CRITICAL: These are suggestions only. Be conservative and express uncertainty when appropriate.

Respond with valid JSON in this format:

{{
  "speaker_predictions": [
    {{
      "speaker_label": "SPEAKER_01",
      "predicted_name": "John Smith",
      "confidence": 0.75,
      "reasoning": "Detailed explanation of why you think this speaker might be John Smith based on content analysis, speech patterns, or context clues",
      "evidence": [
        "References technical architecture decisions",
        "Mentions 'my development team'",
        "Uses technical jargon consistently"
      ],
      "uncertainty_factors": [
        "Could also be another technical lead",
        "No direct name mentions in analyzed segments"
      ]
    }}
  ],
  "overall_confidence": "high|medium|low",
  "analysis_notes": "General observations about the conversation that might help with speaker identification",
  "recommendations": [
    "Specific suggestions for the user to help confirm identities",
    "Additional context to look for in other parts of the transcript"
  ]
}}

GUIDELINES:

**Confidence Levels:**
- **High (0.8+)**: Very strong evidence from content/context
- **Medium (0.5-0.79)**: Good indicators but some uncertainty
- **Low (<0.5)**: Weak evidence, mostly speculation

**Analysis Focus:**
- Prioritize content-based identification over speech patterns
- Look for role-specific language and decision-making patterns
- Note expertise areas demonstrated in the conversation
- Consider formal vs. informal language usage
- Identify leadership vs. contributor dynamics

**Uncertainty Handling:**
- Always include uncertainty factors when confidence isn't extremely high
- Suggest alternative possibilities when appropriate
- Be explicit about limitations of the analysis
- Don't force predictions when evidence is weak

**Recommendations:**
- Suggest specific things users should look for to confirm identities
- Recommend checking other parts of the transcript
- Suggest cross-referencing with meeting attendees or participant lists
- Note any distinctive speech patterns or topics that might help

Remember: Your goal is to assist human decision-making, not replace it. Be helpful but honest about limitations and uncertainty.'''