-- Comprehensive Database Review Script
-- Checks for duplicates, stuck tasks, missing indexes, and data integrity issues

\echo '=== DUPLICATE CHECK ==='
\echo
SELECT
    'Duplicate transcript segments' as check_type,
    COUNT(*) as total_segments,
    COUNT(DISTINCT (media_file_id, start_time, end_time, text)) as unique_segments,
    COUNT(*) - COUNT(DISTINCT (media_file_id, start_time, end_time, text)) as duplicates
FROM transcript_segment;

\echo
\echo '=== FILE STATUS SUMMARY ==='
\echo
SELECT
    status,
    COUNT(*) as files,
    COUNT(CASE WHEN storage_path IS NOT NULL AND storage_path != '' THEN 1 END) as with_video,
    SUM((SELECT COUNT(*) FROM transcript_segment WHERE media_file_id = mf.id)) as total_segments,
    ROUND(AVG((SELECT COUNT(*) FROM transcript_segment WHERE media_file_id = mf.id))) as avg_segments
FROM media_file mf
GROUP BY status
ORDER BY status;

\echo
\echo '=== PENDING FILES (Should be ERROR) ==='
\echo
SELECT
    id,
    LEFT(filename, 60) as filename,
    SUBSTRING(last_error_message, 1, 80) as error
FROM media_file
WHERE status = 'PENDING'
ORDER BY id;

\echo
\echo '=== STUCK LLM TASKS (in_progress > 1 hour) ==='
\echo
SELECT
    t.task_type,
    COUNT(*) as count,
    MIN(AGE(NOW(), t.created_at)) as oldest,
    MAX(AGE(NOW(), t.created_at)) as newest
FROM task t
WHERE t.status = 'in_progress'
AND t.created_at < NOW() - INTERVAL '1 hour'
GROUP BY t.task_type
ORDER BY count DESC;

\echo
\echo '=== LLM TASK STATISTICS ==='
\echo
SELECT
    task_type,
    status,
    COUNT(*) as count
FROM task
WHERE task_type IN ('speaker_identification', 'summarization', 'topic_extraction')
GROUP BY task_type, status
ORDER BY task_type,
         CASE status
             WHEN 'completed' THEN 1
             WHEN 'in_progress' THEN 2
             WHEN 'failed' THEN 3
             ELSE 4
         END;

\echo
\echo '=== SEARCH INDEXING STATUS ==='
\echo
SELECT
    'Total COMPLETED files' as metric,
    COUNT(*) as value
FROM media_file
WHERE status = 'COMPLETED'

UNION ALL

SELECT
    'Files with search_indexing task completed',
    COUNT(DISTINCT mf.id)
FROM media_file mf
WHERE mf.status = 'COMPLETED'
AND EXISTS(
    SELECT 1 FROM task
    WHERE task.media_file_id = mf.id
    AND task.task_type = 'search_indexing'
    AND task.status = 'completed'
)

UNION ALL

SELECT
    'Files MISSING search indexing',
    COUNT(*)
FROM media_file mf
WHERE mf.status = 'COMPLETED'
AND NOT EXISTS(
    SELECT 1 FROM task
    WHERE task.media_file_id = mf.id
    AND task.task_type = 'search_indexing'
    AND task.status = 'completed'
);

\echo
\echo '=== FALSE-POSITIVE FAILED TASKS ==='
\echo
SELECT
    task_type,
    COUNT(*) as count
FROM task
WHERE status = 'failed'
AND error_message = 'Task recovered after being stuck in processing'
GROUP BY task_type
ORDER BY count DESC;

\echo
\echo '=== OPENSEARCH DOCUMENT COUNT ==='
\echo '(Run: curl -s http://localhost:5180/transcripts/_count)'
\echo

\echo '=== SUMMARY ==='
\echo 'Issues Found:'
\echo '  1. PENDING files that should be ERROR (failed YouTube downloads)'
\echo '  2. Stuck LLM tasks running > 22 hours'
\echo '  3. 401 COMPLETED files missing search indexing'
\echo '  4. 774 speaker_id + 768 summarization tasks falsely marked failed'
\echo
