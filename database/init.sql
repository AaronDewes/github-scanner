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
