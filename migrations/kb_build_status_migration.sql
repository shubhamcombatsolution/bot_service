-- KB Build Status Migration Script
-- Add build status fields to tbl_knowledge_base for background processing support
-- Run this script if Alembic migration doesn't work

-- Add build_status column (pending, in_progress, completed, failed)
ALTER TABLE tbl_knowledge_base 
ADD COLUMN IF NOT EXISTS build_status VARCHAR(50) DEFAULT 'pending';

-- Add build_task_id column (references BuildTasksManager task ID)
ALTER TABLE tbl_knowledge_base 
ADD COLUMN IF NOT EXISTS build_task_id VARCHAR(100);

-- Add build_error column (stores error message if build failed)
ALTER TABLE tbl_knowledge_base 
ADD COLUMN IF NOT EXISTS build_error TEXT;

-- Add build_started_at column
ALTER TABLE tbl_knowledge_base 
ADD COLUMN IF NOT EXISTS build_started_at TIMESTAMP;

-- Add build_completed_at column
ALTER TABLE tbl_knowledge_base 
ADD COLUMN IF NOT EXISTS build_completed_at TIMESTAMP;

-- Update existing records to have 'completed' status (they were created before this feature)
UPDATE tbl_knowledge_base 
SET build_status = 'completed' 
WHERE build_status IS NULL OR build_status = 'pending';

-- Verify the migration
SELECT column_name, data_type, is_nullable, column_default 
FROM information_schema.columns 
WHERE table_name = 'tbl_knowledge_base' 
AND column_name LIKE 'build_%';

