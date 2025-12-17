-- GitHub Scanner Database Schema

-- Repositories table
CREATE TABLE IF NOT EXISTS repositories (
    id SERIAL PRIMARY KEY,
    url VARCHAR(512) UNIQUE NOT NULL,
    owner VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    organization VARCHAR(255),
    default_branch VARCHAR(255) DEFAULT 'main',
    has_actions BOOLEAN DEFAULT FALSE,
    first_scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_scanned_at TIMESTAMP,
    scan_status VARCHAR(50) DEFAULT 'pending', -- pending, scanning, completed, failed
    scan_error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(owner, name)
);

CREATE INDEX IF NOT EXISTS idx_repositories_owner ON repositories(owner);
CREATE INDEX IF NOT EXISTS idx_repositories_scan_status ON repositories(scan_status);
CREATE INDEX IF NOT EXISTS idx_repositories_last_scanned ON repositories(last_scanned_at);

-- Branches table
CREATE TABLE IF NOT EXISTS branches (
    id SERIAL PRIMARY KEY,
    repository_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    last_scanned_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(repository_id, name)
);

CREATE INDEX IF NOT EXISTS idx_branches_repository ON branches(repository_id);

-- Vulnerabilities table
CREATE TABLE IF NOT EXISTS vulnerabilities (
    id SERIAL PRIMARY KEY,
    repository_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    branch_id INTEGER REFERENCES branches(id) ON DELETE CASCADE,
    file_path VARCHAR(1024) NOT NULL,
    file_hash VARCHAR(64) NOT NULL, -- SHA-256 hash of the file
    vulnerability_type VARCHAR(255) NOT NULL,
    severity VARCHAR(20) NOT NULL, -- critical, high, medium, low, info
    title VARCHAR(512) NOT NULL,
    description TEXT,
    line_number INTEGER,
    code_snippet TEXT,
    recommendation TEXT,
    cwe_id VARCHAR(20),
    cvss_score DECIMAL(3,1),
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50) DEFAULT 'open', -- open, confirmed, false_positive, fixed, ignored
    manual_analysis TEXT,
    analyzed_by VARCHAR(255),
    analyzed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_vulnerabilities_repository ON vulnerabilities(repository_id);
CREATE INDEX IF NOT EXISTS idx_vulnerabilities_branch ON vulnerabilities(branch_id);
CREATE INDEX IF NOT EXISTS idx_vulnerabilities_severity ON vulnerabilities(severity);
CREATE INDEX IF NOT EXISTS idx_vulnerabilities_status ON vulnerabilities(status);
CREATE INDEX IF NOT EXISTS idx_vulnerabilities_type ON vulnerabilities(vulnerability_type);
CREATE INDEX IF NOT EXISTS idx_vulnerabilities_file_hash ON vulnerabilities(file_hash);

-- Scan queue table (for tracking what needs to be scanned)
CREATE TABLE IF NOT EXISTS scan_queue (
    id SERIAL PRIMARY KEY,
    repository_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    priority INTEGER DEFAULT 0,
    status VARCHAR(50) DEFAULT 'queued', -- queued, processing, completed, failed
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    error_message TEXT,
    job_name VARCHAR(255), -- Kubernetes job name
    queued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_scan_queue_status ON scan_queue(status);
CREATE INDEX IF NOT EXISTS idx_scan_queue_priority ON scan_queue(priority DESC);
CREATE INDEX IF NOT EXISTS idx_scan_queue_repository ON scan_queue(repository_id);

-- Scan history table (for tracking all scan attempts)
CREATE TABLE IF NOT EXISTS scan_history (
    id SERIAL PRIMARY KEY,
    repository_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    scan_queue_id INTEGER REFERENCES scan_queue(id) ON DELETE SET NULL,
    status VARCHAR(50) NOT NULL,
    vulnerabilities_found INTEGER DEFAULT 0,
    duration_seconds INTEGER,
    error_message TEXT,
    octoscan_version VARCHAR(50),
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_scan_history_repository ON scan_history(repository_id);
CREATE INDEX IF NOT EXISTS idx_scan_history_started ON scan_history(started_at);

-- GitHub API rate limit tracking
CREATE TABLE IF NOT EXISTS rate_limits (
    id SERIAL PRIMARY KEY,
    api_type VARCHAR(50) NOT NULL, -- core, search, graphql
    limit_value INTEGER NOT NULL,
    remaining INTEGER NOT NULL,
    reset_at TIMESTAMP NOT NULL,
    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_rate_limits_api_type ON rate_limits(api_type);
CREATE INDEX IF NOT EXISTS idx_rate_limits_reset ON rate_limits(reset_at);

-- Safe files table (files marked as safe globally across all repos/branches)
CREATE TABLE IF NOT EXISTS safe_files (
    id SERIAL PRIMARY KEY,
    file_path VARCHAR(1024) NOT NULL, -- The workflow file path pattern (e.g., .github/workflows/ci.yml)
    file_hash VARCHAR(64), -- Optional: specific file hash to match
    reason TEXT, -- Why the file is marked safe
    marked_by VARCHAR(255), -- Who marked it safe
    marked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(file_path, file_hash)
);

CREATE INDEX IF NOT EXISTS idx_safe_files_path ON safe_files(file_path);
CREATE INDEX IF NOT EXISTS idx_safe_files_hash ON safe_files(file_hash);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for updated_at
DROP TRIGGER IF EXISTS update_repositories_updated_at ON repositories;
CREATE TRIGGER update_repositories_updated_at BEFORE UPDATE ON repositories
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_branches_updated_at ON branches;
CREATE TRIGGER update_branches_updated_at BEFORE UPDATE ON branches
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_vulnerabilities_updated_at ON vulnerabilities;
CREATE TRIGGER update_vulnerabilities_updated_at BEFORE UPDATE ON vulnerabilities
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_scan_queue_updated_at ON scan_queue;
CREATE TRIGGER update_scan_queue_updated_at BEFORE UPDATE ON scan_queue
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_safe_files_updated_at ON safe_files;
CREATE TRIGGER update_safe_files_updated_at BEFORE UPDATE ON safe_files
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create view for vulnerability statistics
CREATE OR REPLACE VIEW vulnerability_stats AS
SELECT 
    r.id as repository_id,
    r.owner,
    r.name,
    COUNT(v.id) as total_vulnerabilities,
    COUNT(CASE WHEN v.severity = 'critical' THEN 1 END) as critical_count,
    COUNT(CASE WHEN v.severity = 'high' THEN 1 END) as high_count,
    COUNT(CASE WHEN v.severity = 'medium' THEN 1 END) as medium_count,
    COUNT(CASE WHEN v.severity = 'low' THEN 1 END) as low_count,
    COUNT(CASE WHEN v.status = 'open' THEN 1 END) as open_count,
    COUNT(CASE WHEN v.status = 'confirmed' THEN 1 END) as confirmed_count,
    MAX(v.detected_at) as last_vulnerability_detected
FROM repositories r
LEFT JOIN vulnerabilities v ON r.id = v.repository_id
GROUP BY r.id, r.owner, r.name;
