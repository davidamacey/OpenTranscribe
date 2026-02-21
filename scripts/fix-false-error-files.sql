-- One-time correction script for files incorrectly marked ERROR despite having complete
-- transcripts. Originally applied 2026-02-12. Retained for reference and potential reuse
-- if similar false-positive ERROR marking occurs in the future.
--
-- Fix incorrectly marked ERROR files that actually completed successfully
-- These files have transcripts, video files, and completed_at timestamps
-- but were marked ERROR by overly aggressive recovery logic

BEGIN;

-- Show what we're about to fix
SELECT
    'Files to be corrected' as action,
    COUNT(*) as count,
    SUM((SELECT COUNT(*) FROM transcript_segment WHERE media_file_id = mf.id)) as total_segments
FROM media_file mf
WHERE mf.status = 'ERROR'
AND mf.storage_path IS NOT NULL
AND mf.storage_path != ''
AND mf.completed_at IS NOT NULL
AND EXISTS (SELECT 1 FROM transcript_segment WHERE media_file_id = mf.id LIMIT 1);

-- Update status to COMPLETED for files that actually completed
UPDATE media_file
SET
    status = 'COMPLETED',
    last_error_message = NULL  -- Clear the false error message
WHERE status = 'ERROR'
AND storage_path IS NOT NULL
AND storage_path != ''
AND completed_at IS NOT NULL
AND EXISTS (SELECT 1 FROM transcript_segment WHERE media_file_id = id LIMIT 1);

-- Show what we fixed
SELECT
    'Files corrected' as action,
    COUNT(*) as count,
    SUM((SELECT COUNT(*) FROM transcript_segment WHERE media_file_id = mf.id)) as total_segments
FROM media_file mf
WHERE mf.status = 'COMPLETED'
AND mf.completed_at IS NOT NULL
AND EXISTS (SELECT 1 FROM transcript_segment WHERE media_file_id = mf.id LIMIT 1);

COMMIT;
