-- Initial setup for GitHub Scanner database

-- Create database user if not exists
-- Note: Run this as superuser
-- CREATE USER scanner WITH PASSWORD 'your_secure_password';
-- GRANT ALL PRIVILEGES ON DATABASE github_scanner TO scanner;

-- Grant privileges on all tables
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO scanner;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO scanner;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO scanner;

-- Set default privileges for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO scanner;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO scanner;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO scanner;

-- Migration: Add safe_files table if not exists
CREATE TABLE IF NOT EXISTS safe_files (
    id SERIAL PRIMARY KEY,
    file_path VARCHAR(1024) NOT NULL,
    file_hash VARCHAR(64),
    reason TEXT,
    marked_by VARCHAR(255),
    marked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(file_path, file_hash)
);

CREATE INDEX IF NOT EXISTS idx_safe_files_path ON safe_files(file_path);
CREATE INDEX IF NOT EXISTS idx_safe_files_hash ON safe_files(file_hash);

DROP TRIGGER IF EXISTS update_safe_files_updated_at ON safe_files;
CREATE TRIGGER update_safe_files_updated_at BEFORE UPDATE ON safe_files
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
