"""
File cleanup service for recovering stuck files and maintaining system health.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from app.models.media import MediaFile, FileStatus
from app.utils.task_utils import (
    check_for_stuck_files,
    recover_stuck_file,
    cancel_active_task
)
from app.db.session_utils import session_scope

logger = logging.getLogger(__name__)


class FileCleanupService:
    """Service for automated file cleanup and recovery operations."""
    
    def __init__(self):
        self.stuck_threshold_hours = 2
        self.orphan_threshold_hours = 12
        self.max_recovery_attempts = 3
    
    def run_cleanup_cycle(self) -> Dict[str, Any]:
        """
        Run a complete cleanup cycle.
        
        Returns:
            Dictionary with cleanup results and statistics
        """
        results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stuck_files_checked": 0,
            "files_recovered": 0,
            "files_marked_orphaned": 0,
            "cleanup_errors": [],
            "recommendations": []
        }
        
        try:
            with session_scope() as db:
                # Step 1: Check for stuck files
                stuck_file_ids = check_for_stuck_files(db, self.stuck_threshold_hours)
                results["stuck_files_checked"] = len(stuck_file_ids)
                
                if stuck_file_ids:
                    logger.info(f"Found {len(stuck_file_ids)} stuck files for cleanup")
                    
                    # Step 2: Attempt recovery
                    for file_id in stuck_file_ids:
                        try:
                            success = self._attempt_file_recovery(db, file_id)
                            if success:
                                results["files_recovered"] += 1
                            else:
                                results["files_marked_orphaned"] += 1
                        except Exception as e:
                            error_msg = f"Error processing stuck file {file_id}: {str(e)}"
                            logger.error(error_msg)
                            results["cleanup_errors"].append(error_msg)
                
                # Step 3: Handle very old orphaned files
                old_orphaned_count = self._handle_old_orphaned_files(db)
                if old_orphaned_count > 0:
                    results["recommendations"].append(
                        f"Found {old_orphaned_count} old orphaned files that may need admin attention"
                    )
                
                # Step 4: Generate health recommendations
                health_recommendations = self._generate_health_recommendations(db)
                results["recommendations"].extend(health_recommendations)
                
        except Exception as e:
            error_msg = f"Critical error in cleanup cycle: {str(e)}"
            logger.error(error_msg)
            results["cleanup_errors"].append(error_msg)
        
        logger.info(f"Cleanup cycle completed: {results}")
        return results
    
    def _attempt_file_recovery(self, db: Session, file_id: int) -> bool:
        """
        Attempt to recover a single stuck file.
        
        Args:
            db: Database session
            file_id: ID of the file to recover
            
        Returns:
            True if recovery was successful, False if marked as orphaned
        """
        media_file = db.query(MediaFile).filter(MediaFile.id == file_id).first()
        if not media_file:
            return False
        
        # Check if we've already tried recovery too many times
        if media_file.recovery_attempts >= self.max_recovery_attempts:
            logger.warning(f"File {file_id} has exceeded max recovery attempts ({self.max_recovery_attempts})")
            # Mark as permanently orphaned
            media_file.status = FileStatus.ORPHANED
            media_file.force_delete_eligible = True
            db.commit()
            return False
        
        # Attempt recovery
        return recover_stuck_file(db, file_id)
    
    def _handle_old_orphaned_files(self, db: Session) -> int:
        """
        Handle files that have been orphaned for a long time.
        
        Args:
            db: Database session
            
        Returns:
            Number of old orphaned files found
        """
        threshold_time = datetime.now(timezone.utc) - timedelta(hours=self.orphan_threshold_hours)
        
        old_orphaned_files = db.query(MediaFile).filter(
            MediaFile.status == FileStatus.ORPHANED,
            MediaFile.last_recovery_attempt < threshold_time
        ).all()
        
        for file in old_orphaned_files:
            # Mark as eligible for force deletion
            file.force_delete_eligible = True
            logger.warning(f"File {file.id} has been orphaned for over {self.orphan_threshold_hours} hours")
        
        if old_orphaned_files:
            db.commit()
        
        return len(old_orphaned_files)
    
    def _generate_health_recommendations(self, db: Session) -> List[str]:
        """
        Generate system health recommendations based on file states.
        
        Args:
            db: Database session
            
        Returns:
            List of recommendation strings
        """
        recommendations = []
        
        # Count files by status
        status_counts = {}
        for status in FileStatus:
            count = db.query(MediaFile).filter(MediaFile.status == status).count()
            status_counts[status.value] = count
        
        # Check for concerning patterns
        error_rate = status_counts.get('error', 0) / max(sum(status_counts.values()), 1)
        if error_rate > 0.1:  # More than 10% error rate
            recommendations.append(
                f"High error rate detected: {error_rate:.1%} of files are in error state. "
                "Consider investigating processing pipeline health."
            )
        
        orphaned_count = status_counts.get('orphaned', 0)
        if orphaned_count > 0:
            recommendations.append(
                f"Found {orphaned_count} orphaned file(s). "
                "Consider manual review or cleanup of these files."
            )
        
        processing_count = status_counts.get('processing', 0)
        if processing_count > 50:  # Arbitrary threshold
            recommendations.append(
                f"Large number of files currently processing ({processing_count}). "
                "Monitor worker capacity and queue health."
            )
        
        return recommendations
    
    def force_cleanup_orphaned_files(self, db: Session, dry_run: bool = False) -> Dict[str, Any]:
        """
        Force cleanup of orphaned files (admin operation).
        
        Args:
            db: Database session
            dry_run: If True, only preview what would be cleaned up
            
        Returns:
            Dictionary with cleanup results
        """
        results = {
            "dry_run": dry_run,
            "eligible_for_deletion": 0,
            "successfully_deleted": 0,
            "deletion_errors": [],
            "files_processed": []
        }
        
        # Find files eligible for force deletion
        eligible_files = db.query(MediaFile).filter(
            MediaFile.force_delete_eligible == True,
            MediaFile.status.in_([FileStatus.ORPHANED, FileStatus.ERROR])
        ).all()
        
        results["eligible_for_deletion"] = len(eligible_files)
        
        if not dry_run:
            from app.api.endpoints.files.crud import delete_media_file
            from app.models.user import User
            
            # Create a system user for cleanup operations
            system_user = User(role="admin", email="system@cleanup")
            
            for file in eligible_files:
                try:
                    # Force delete the file
                    delete_media_file(db, file.id, system_user, force=True)
                    results["successfully_deleted"] += 1
                    results["files_processed"].append({
                        "id": file.id,
                        "filename": file.filename,
                        "status": "deleted"
                    })
                except Exception as e:
                    error_msg = f"Failed to delete file {file.id}: {str(e)}"
                    results["deletion_errors"].append(error_msg)
                    results["files_processed"].append({
                        "id": file.id,
                        "filename": file.filename,
                        "status": "error",
                        "error": str(e)
                    })
        else:
            # Dry run - just record what would be deleted
            for file in eligible_files:
                results["files_processed"].append({
                    "id": file.id,
                    "filename": file.filename,
                    "status": "would_delete",
                    "current_status": file.status
                })
        
        return results
    
    def get_cleanup_statistics(self, db: Session) -> Dict[str, Any]:
        """
        Get current cleanup statistics and system health metrics.
        
        Args:
            db: Database session
            
        Returns:
            Dictionary with statistics
        """
        stats = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "file_counts_by_status": {},
            "stuck_files_detected": 0,
            "files_eligible_for_cleanup": 0,
            "avg_processing_time_hours": 0,
            "health_score": "unknown"
        }
        
        # Count files by status
        for status in FileStatus:
            count = db.query(MediaFile).filter(MediaFile.status == status).count()
            stats["file_counts_by_status"][status.value] = count
        
        # Count stuck files
        stuck_files = check_for_stuck_files(db, self.stuck_threshold_hours)
        stats["stuck_files_detected"] = len(stuck_files)
        
        # Count files eligible for cleanup
        eligible_count = db.query(MediaFile).filter(
            MediaFile.force_delete_eligible == True
        ).count()
        stats["files_eligible_for_cleanup"] = eligible_count
        
        # Calculate average processing time for completed files
        completed_files = db.query(MediaFile).filter(
            MediaFile.status == FileStatus.COMPLETED,
            MediaFile.task_started_at.isnot(None),
            MediaFile.completed_at.isnot(None)
        ).all()
        
        if completed_files:
            total_processing_time = sum([
                (file.completed_at - file.task_started_at).total_seconds() / 3600
                for file in completed_files
                if file.completed_at and file.task_started_at
            ])
            stats["avg_processing_time_hours"] = total_processing_time / len(completed_files)
        
        # Calculate health score
        total_files = sum(stats["file_counts_by_status"].values())
        if total_files > 0:
            error_rate = stats["file_counts_by_status"].get("error", 0) / total_files
            orphaned_rate = stats["file_counts_by_status"].get("orphaned", 0) / total_files
            
            if error_rate < 0.05 and orphaned_rate < 0.02:
                stats["health_score"] = "healthy"
            elif error_rate < 0.1 and orphaned_rate < 0.05:
                stats["health_score"] = "fair"
            else:
                stats["health_score"] = "poor"
        else:
            stats["health_score"] = "empty"
        
        return stats


# Global service instance
cleanup_service = FileCleanupService()