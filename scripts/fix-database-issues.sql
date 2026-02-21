-- Manual database repair utility for stuck tasks, pending downloads, and false-positive failures.
-- The automatic recovery system (backend/app/tasks/recovery.py) now handles these cases
-- automatically on a 2-5 minute cycle. This script is retained for emergency manual
-- intervention when the backend service is down or recovery tasks are not running.
--
-- Original purpose: Fix all identified database issues
-- Run this script to correct stuck tasks, pending files, and false-positive failures

BEGIN;

\echo '=== FIX 1: Mark stuck PENDING YouTube files as ERROR ==='
\echo 'These files failed to download and will never succeed (require sign-in)'
\echo

UPDATE media_file
SET
    status = 'ERROR',
    last_error_message = COALESCE(last_error_message, 'Failed to download: Video requires authentication')
WHERE status = 'PENDING'
AND file_size = 0
AND (storage_path IS NULL OR storage_path = '')
AND last_error_message LIKE '%sign-in%'
RETURNING id, LEFT(filename, 50) as filename;

\echo
\echo '=== FIX 2: Mark stuck LLM tasks as failed (in_progress > 6 hours) ==='
\echo 'These tasks are stuck and preventing recovery from retrying them'
\echo

UPDATE task
SET
    status = 'failed',
    error_message = 'Task timeout - stuck in progress for > 6 hours',
    completed_at = NOW(),
    updated_at = NOW()
WHERE status = 'in_progress'
AND created_at < NOW() - INTERVAL '6 hours'
AND task_type IN ('speaker_identification', 'summarization', 'topic_extraction')
RETURNING id, task_type, AGE(NOW(), created_at) as was_running_for;

\echo
\echo '=== FIX 3: Clear false-positive failed task errors ==='
\echo 'These tasks were marked failed by overly aggressive recovery - reset to allow retry'
\echo

WITH updated AS (
    UPDATE task
    SET
        status = 'pending',
        error_message = NULL,
        completed_at = NULL,
        updated_at = NOW()
    WHERE status = 'failed'
    AND error_message = 'Task recovered after being stuck in processing'
    AND task_type IN ('speaker_identification', 'summarization', 'transcription')
    -- Only reset recent failures (last 3 days) to avoid retrying very old tasks
    AND created_at > NOW() - INTERVAL '3 days'
    RETURNING task_type
)
SELECT task_type, COUNT(*) as reset_count
FROM updated
GROUP BY task_type;

\echo
\echo '=== VERIFICATION ==='
\echo

SELECT
    'Files needing search indexing' as metric,
    COUNT(*) as count
FROM media_file mf
WHERE mf.status = 'COMPLETED'
AND NOT EXISTS(
    SELECT 1 FROM task
    WHERE task.media_file_id = mf.id
    AND task.task_type = 'search_indexing'
    AND task.status = 'completed'
);

COMMIT;

\echo
\echo '=== NEXT STEPS ==='
\echo '1. Restart backend to trigger periodic health check: docker restart opentranscribe-backend'
\echo '2. Health check will automatically:'
\echo '   - Dispatch search indexing for 401 missing files'
\echo '   - Retry reset LLM tasks'
\echo '3. Monitor recovery: docker logs -f opentranscribe-backend | grep -i recovery'
\echo
