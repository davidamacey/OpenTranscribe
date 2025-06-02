"""
Task recovery and monitoring configuration.

This module centralizes all configuration related to task recovery,
monitoring thresholds, and recovery policies.
"""

from dataclasses import dataclass
from typing import Dict


@dataclass
class TaskRecoveryConfig:
    """Configuration for task recovery operations."""
    
    # Maximum allowed duration for different task types (in seconds)
    MAX_TASK_DURATIONS: Dict[str, int] = None
    
    # Time before considering a task stale (in seconds)
    STALENESS_THRESHOLD: int = 300  # 5 minutes
    
    # Time to wait before startup recovery kicks in (in seconds)
    STARTUP_RECOVERY_DELAY: int = 10
    
    # Periodic health check interval (in minutes)
    HEALTH_CHECK_INTERVAL: int = 10
    
    # Maximum runtime for health check task (in seconds)
    HEALTH_CHECK_MAX_RUNTIME: int = 480  # 8 minutes, less than 10 min interval
    
    # Task execution overlap prevention
    PREVENT_TASK_OVERLAP: bool = True
    
    # File age thresholds for recovery (in hours)
    FILE_RECOVERY_AGE_THRESHOLD: int = 2
    PENDING_FILE_RETRY_THRESHOLD: int = 6
    
    # Orphaned task threshold (in hours)
    ORPHANED_TASK_THRESHOLD: int = 1

    def __post_init__(self):
        if self.MAX_TASK_DURATIONS is None:
            self.MAX_TASK_DURATIONS = {
                "transcription": 3600,  # 1 hour max for transcription
                "extract_audio": 600,   # 10 minutes max for audio extraction
                "analyze_transcript": 900,  # 15 minutes max for analysis
                "summarize_transcript": 900,  # 15 minutes max for summarization
                "default": 1800  # 30 minutes default for other task types
            }


# Global configuration instance
task_recovery_config = TaskRecoveryConfig()