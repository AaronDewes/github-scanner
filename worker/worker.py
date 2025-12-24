#!/usr/bin/env python3
"""
GitHub Scanner Worker

This worker uses Octoscan to analyze GitHub repositories for security vulnerabilities
in GitHub Actions workflows and stores the results in PostgreSQL.
"""

import os
import sys
import json
import subprocess
import hashlib
import re
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor
import requests


class GitHubRateLimiter:
    """Handles GitHub API rate limit checking and waiting."""
    
    def __init__(self, token: Optional[str] = None, database_url: Optional[str] = None):
        self.token = token
        self.database_url = database_url
        self.base_url = "https://api.github.com"
        self.session = requests.Session()
        
        if token:
            self.session.headers.update({
                'Authorization': f'token {token}',
                'Accept': 'application/vnd.github.v3+json'
            })
    
    def check_rate_limit(self) -> Dict:
        """Check current GitHub API rate limit status."""
        try:
            response = self.session.get(f"{self.base_url}/rate_limit")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error checking rate limit: {e}", file=sys.stderr)
            return {}
    
    def store_rate_limit(self, rate_limit_info: Dict):
        """Store rate limit information in the database."""
        if not self.database_url:
            return
        
        try:
            conn = psycopg2.connect(self.database_url)
            cursor = conn.cursor()
            
            for api_type in ['core', 'search']:
                if api_type in rate_limit_info.get('resources', {}):
                    info = rate_limit_info['resources'][api_type]
                    cursor.execute(
                        """INSERT INTO rate_limits (api_type, limit_value, remaining, reset_at)
                           VALUES (%s, %s, %s, to_timestamp(%s))""",
                        (api_type, info.get('limit', 0), info.get('remaining', 0), info.get('reset', 0))
                    )
            
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"Error storing rate limit: {e}", file=sys.stderr)
    
    def wait_for_rate_limit(self, min_remaining: int = 100) -> bool:
        """
        Check rate limits and wait if necessary.
        
        Args:
            min_remaining: Minimum remaining requests before waiting
            
        Returns:
            True if ready to proceed, False if rate limit cannot be resolved
        """
        rate_limit_info = self.check_rate_limit()
        
        if not rate_limit_info:
            print("Warning: Could not check rate limit, proceeding anyway")
            return True
        
        # Store rate limit info
        self.store_rate_limit(rate_limit_info)
        
        # Check core API (used by octoscan)
        core = rate_limit_info.get('resources', {}).get('core', {})
        remaining = core.get('remaining', 5000)
        reset_time = core.get('reset', 0)
        
        print(f"GitHub API rate limit: {remaining} requests remaining")
        
        if remaining < min_remaining:
            wait_time = reset_time - time.time()
            if wait_time > 0:
                # Cap wait time at 1 hour
                wait_time = min(wait_time, 3600)
                print(f"Rate limit low ({remaining} remaining). Waiting {int(wait_time)} seconds...")
                time.sleep(wait_time + 5)  # Add 5 seconds buffer
                
                # Re-check after waiting
                return self.wait_for_rate_limit(min_remaining)
            else:
                print("Rate limit should have reset, proceeding...")
        
        return True
    
    def has_sufficient_quota(self, min_remaining: int = 100) -> Tuple[bool, int, int]:
        """
        Check if there's sufficient API quota without waiting.
        
        Returns:
            Tuple of (has_quota, remaining, reset_timestamp)
        """
        rate_limit_info = self.check_rate_limit()
        
        if not rate_limit_info:
            return True, 5000, 0  # Assume OK if can't check
        
        core = rate_limit_info.get('resources', {}).get('core', {})
        remaining = core.get('remaining', 5000)
        reset_time = core.get('reset', 0)
        
        return remaining >= min_remaining, remaining, reset_time


class DatabaseConnection:
    """Manages PostgreSQL database connections."""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.conn = None
        self.cursor = None
    
    def __enter__(self):
        self.conn = psycopg2.connect(self.database_url)
        self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.conn.rollback()
        else:
            self.conn.commit()
        
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()


class GitHubScanner:
    """Main scanner class that orchestrates the scanning process."""
    
    def __init__(self, repo_url: str, database_url: str, github_token: Optional[str] = None):
        self.repo_url = repo_url
        self.database_url = database_url
        self.github_token = github_token
        self.owner, self.repo_name = self._parse_repo_url(repo_url)
        self.repository_id = None
        self.scan_queue_id = None
        self.rate_limiter = GitHubRateLimiter(token=github_token, database_url=database_url)
        
    def _parse_repo_url(self, url: str) -> Tuple[str, str]:
        """Parse GitHub repository URL to extract owner and repo name."""
        # Handle various URL formats
        patterns = [
            r'github\.com[:/]([^/]+)/([^/\.]+)',
            r'github\.com/([^/]+)/([^/]+)\.git',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1), match.group(2)
        
        raise ValueError(f"Invalid GitHub repository URL: {url}")
    
    def _get_or_create_repository(self, db: DatabaseConnection) -> int:
        """Get or create repository entry in database."""
        # Check if repository exists
        db.cursor.execute(
            "SELECT id FROM repositories WHERE owner = %s AND name = %s",
            (self.owner, self.repo_name)
        )
        result = db.cursor.fetchone()
        
        if result:
            repo_id = result['id']
            # Update last scanned timestamp and status
            db.cursor.execute(
                """UPDATE repositories 
                   SET scan_status = 'scanning', 
                       last_scanned_at = CURRENT_TIMESTAMP
                   WHERE id = %s""",
                (repo_id,)
            )
        else:
            # Create new repository entry
            db.cursor.execute(
                """INSERT INTO repositories (url, owner, name, scan_status, has_actions)
                   VALUES (%s, %s, %s, 'scanning', TRUE)
                   RETURNING id""",
                (self.repo_url, self.owner, self.repo_name)
            )
            repo_id = db.cursor.fetchone()['id']
        
        return repo_id
    
    def _update_scan_queue(self, db: DatabaseConnection, status: str, error: Optional[str] = None):
        """Update scan queue status."""
        if self.scan_queue_id:
            if status == 'processing':
                db.cursor.execute(
                    """UPDATE scan_queue 
                       SET status = %s, started_at = CURRENT_TIMESTAMP
                       WHERE id = %s""",
                    (status, self.scan_queue_id)
                )
            elif status in ['completed', 'failed']:
                db.cursor.execute(
                    """UPDATE scan_queue 
                       SET status = %s, completed_at = CURRENT_TIMESTAMP, error_message = %s
                       WHERE id = %s""",
                    (status, error, self.scan_queue_id)
                )
            else:
                db.cursor.execute(
                    """UPDATE scan_queue 
                       SET status = %s, error_message = %s
                       WHERE id = %s""",
                    (status, error, self.scan_queue_id)
                )
    
    def _get_scan_queue_id(self, db: DatabaseConnection):
        """Find scan queue entry for this repository."""
        # Look for 'processing' status first (set by queue_worker before job starts)
        # Fall back to 'queued' status for manual/direct scans
        db.cursor.execute(
            """SELECT id FROM scan_queue 
               WHERE repository_id = %s AND status IN ('processing', 'queued')
               ORDER BY 
                 CASE status WHEN 'processing' THEN 1 ELSE 2 END,
                 priority DESC, queued_at ASC
               LIMIT 1""",
            (self.repository_id,)
        )
        result = db.cursor.fetchone()
        if result:
            self.scan_queue_id = result['id']
    
    def _clone_repository(self, target_dir: str) -> bool:
        """Clone the GitHub repository."""
        try:
            # Use git to clone the repository
            cmd = ['git', 'clone', '--depth', '1', self.repo_url, target_dir]
            
            # Add token if available
            if self.github_token:
                # Replace URL to include token
                auth_url = self.repo_url.replace(
                    'https://github.com/',
                    f'https://{self.github_token}@github.com/'
                )
                cmd = ['git', 'clone', '--depth', '1', auth_url, target_dir]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes timeout
            )
            
            if result.returncode != 0:
                print(f"Error cloning repository: {result.stderr}", file=sys.stderr)
                return False
            
            return True
        
        except subprocess.TimeoutExpired:
            print("Repository clone timed out", file=sys.stderr)
            return False
        except Exception as e:
            print(f"Exception during clone: {e}", file=sys.stderr)
            return False
    
    def _download_workflows(self, output_dir: str) -> bool:
        """Download workflows from all branches using octoscan dl."""
        try:
            cmd = [
                'octoscan',
                'dl',
                '--org', self.owner,
                '--repo', self.repo_name,
                '--default-branch',
                '--output-dir', output_dir
            ]
            
            # Add GitHub token if available
            if self.github_token:
                cmd.extend(['--token', self.github_token])
            
            print(f"Downloading workflows: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10 minutes timeout
            )
            
            if result.returncode != 0:
                print(f"Warning: octoscan dl returned non-zero: {result.stderr}", file=sys.stderr)
                # Check if any files were downloaded anyway
                if os.path.exists(output_dir) and any(os.scandir(output_dir)):
                    print("Some workflows were downloaded, continuing...")
                    return True
                return False
            
            if result.stdout:
                print(f"Octoscan dl output: {result.stdout}")
            
            return True
        
        except subprocess.TimeoutExpired:
            print("Octoscan dl timed out", file=sys.stderr)
            return False
        except Exception as e:
            print(f"Exception during octoscan dl: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            return False
    
    def _run_octoscan(self, workflows_dir: str) -> Optional[List[Dict]]:
        """Run octoscan analysis on downloaded workflows."""
        try:
            if not os.path.exists(workflows_dir):
                print(f"No workflows directory found at {workflows_dir}")
                return []
            
            cmd = [
                'octoscan',
                'scan',
                workflows_dir,
                '--format', 'json',
                '--disable-rules', 'shellcheck,local-action',  # Reduce false positives
                '--filter-run',  # Only focus on injections in actual shell scripts to reduce false positives
                '--filter-triggers', 'external'  # Focus on externally triggered workflows
            ]
            
            print(f"Running: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10 minutes timeout
            )
            
            # Octoscan may return non-zero even with valid results
            # Parse output if available
            if result.stdout:
                try:
                    vulnerabilities = json.loads(result.stdout)
                    if isinstance(vulnerabilities, list):
                        print(f"Octoscan found {len(vulnerabilities)} potential issues")
                        return vulnerabilities
                    else:
                        print("Unexpected octoscan output format")
                        return []
                except json.JSONDecodeError as e:
                    print(f"Failed to parse octoscan JSON output: {e}", file=sys.stderr)
                    print(f"Output: {result.stdout[:500]}", file=sys.stderr)
                    return []
            
            if result.stderr:
                print(f"Octoscan stderr: {result.stderr}", file=sys.stderr)
            
            # No vulnerabilities found
            return []
        
        except subprocess.TimeoutExpired:
            print("Octoscan timed out", file=sys.stderr)
            return None
        except Exception as e:
            print(f"Exception during octoscan: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            return None
    
    def _calculate_file_hash(self, file_path: str) -> str:
        """Calculate SHA-256 hash of a file."""
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception as e:
            print(f"Error hashing file {file_path}: {e}", file=sys.stderr)
            return ""
    
    def _extract_branch_from_path(self, file_path: str) -> str:
        """Extract branch name from octoscan dl output path.
        
        Path format: output_dir/owner/repo/branch/.github/workflows/file.yml
        """
        parts = file_path.split(os.sep)
        try:
            # Find .github in the path and get the part before it
            for i, part in enumerate(parts):
                if part == '.github' and i > 0:
                    return parts[i - 1]
        except Exception as e:
            print(f"Error extracting branch from path {file_path}: {e}", file=sys.stderr)
        
        # Default to main if extraction fails
        return 'main'
    
    def _clean_file_path(self, file_path: str) -> str:
        """Extract clean file path (starting from .github/) from octoscan output path.
        
        Input:  octoscan-output/owner/repo/branch/.github/workflows/file.yml
        Output: .github/workflows/file.yml
        """
        parts = file_path.split(os.sep)
        try:
            # Find .github in the path and return from there onwards
            for i, part in enumerate(parts):
                if part == '.github':
                    return os.sep.join(parts[i:])
        except Exception as e:
            print(f"Error cleaning file path {file_path}: {e}", file=sys.stderr)
        
        # Return original if extraction fails
        return file_path
    
    def _is_file_safe(self, db: DatabaseConnection, file_path: str, file_hash: str) -> bool:
        """Check if a file is marked as safe globally."""
        db.cursor.execute(
            """SELECT id FROM safe_files 
               WHERE file_path = %s 
               AND (file_hash IS NULL OR file_hash = %s)""",
            (file_path, file_hash)
        )
        return db.cursor.fetchone() is not None
    
    def _store_vulnerabilities(self, db: DatabaseConnection, vulnerabilities: List[Dict], workflows_dir: str):
        """Store discovered vulnerabilities in the database."""
        skipped_safe = 0
        for vuln in vulnerabilities:
            try:
                # Octoscan output format:
                # {
                #   "message": "Expression injection, \"github.head_ref\" is potentially untrusted.",
                #   "filepath": "octoscan-output/owner/repo/branch/.github/workflows/ci.yml",
                #   "line": 14,
                #   "column": 20,
                #   "kind": "expression-injection",
                #   "snippet": "  ref: ${{ github.head_ref }}",
                #   "end_column": 34
                # }
                
                raw_file_path = vuln.get('filepath', '')
                full_path = os.path.join(workflows_dir, raw_file_path) if not os.path.isabs(raw_file_path) else raw_file_path
                file_hash = self._calculate_file_hash(full_path) if os.path.exists(full_path) else ''
                
                # Clean up file path to just .github/workflows/... 
                clean_file_path = self._clean_file_path(raw_file_path)
                
                # Check if file is marked as safe globally
                if self._is_file_safe(db, clean_file_path, file_hash):
                    skipped_safe += 1
                    continue
                
                # Map vulnerability kind to severity
                vuln_kind = vuln.get('kind', 'unknown')
                severity = self._map_severity(vuln_kind)
                
                # Extract branch name from file path
                # octoscan dl creates structure: output_dir/owner/repo/branch/.github/workflows/file.yml
                branch_name = self._extract_branch_from_path(raw_file_path)
                
                # Get or create branch
                db.cursor.execute(
                    """INSERT INTO branches (repository_id, name)
                       VALUES (%s, %s)
                       ON CONFLICT (repository_id, name) DO UPDATE
                       SET last_scanned_at = CURRENT_TIMESTAMP
                       RETURNING id""",
                    (self.repository_id, branch_name)
                )
                branch_id = db.cursor.fetchone()['id']
                
                # Create title from message (first 512 chars)
                message = vuln.get('message', 'Security vulnerability detected')
                title = message[:512] if len(message) > 512 else message
                
                # Insert vulnerability (store clean file path)
                db.cursor.execute(
                    """INSERT INTO vulnerabilities 
                       (repository_id, branch_id, file_path, file_hash, vulnerability_type,
                        severity, title, description, line_number, code_snippet, 
                        recommendation, cwe_id, cvss_score)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        self.repository_id,
                        branch_id,
                        clean_file_path,
                        file_hash,
                        vuln_kind,
                        severity,
                        title,
                        message,  # Full message in description
                        vuln.get('line', None),
                        vuln.get('snippet', ''),
                        self._get_recommendation(vuln_kind),
                        None,  # CWE not provided by octoscan
                        None   # CVSS not provided by octoscan
                    )
                )
            
            except Exception as e:
                print(f"Error storing vulnerability: {e}", file=sys.stderr)
                import traceback
                traceback.print_exc()
                continue
        
        if skipped_safe > 0:
            print(f"Skipped {skipped_safe} vulnerabilities from globally safe files")
    
    def _map_severity(self, vuln_kind: str) -> str:
        """Map octoscan vulnerability kind to severity level."""
        # Map based on security impact
        severity_map = {
            'expression-injection': 'critical',
            'dangerous-checkout': 'high',
            'dangerous-action': 'high',
            'dangerous-write': 'high',
            'repo-jacking': 'high',
            'unsecure-commands': 'high',
            'known-vulnerability': 'high',
            'dangerous-artefact': 'medium',
            'credentials': 'critical',
            'runner-label': 'medium',
            'bot-check': 'medium',
            'local-action': 'low',
            'oidc-action': 'info',
            'shellcheck': 'low',
        }
        return severity_map.get(vuln_kind, 'medium')
    
    def _get_recommendation(self, vuln_kind: str) -> str:
        """Get recommendation based on vulnerability kind."""
        recommendations = {
            'expression-injection': 'Sanitize untrusted input before use in expressions. Use intermediate environment variables.',
            'dangerous-checkout': 'Avoid checking out untrusted code in privileged contexts like workflow_run or pull_request_target.',
            'dangerous-action': 'Treat artifact data as untrusted. Validate and sanitize before use.',
            'dangerous-write': 'Sanitize inputs before writing to GITHUB_ENV or GITHUB_OUTPUT to prevent command injection.',
            'repo-jacking': 'Verify that referenced GitHub actions point to valid organizations/users.',
            'unsecure-commands': 'Remove ACTIONS_ALLOW_UNSECURE_COMMANDS environment variable.',
            'known-vulnerability': 'Update the action to a patched version.',
            'dangerous-artefact': 'Avoid uploading sensitive files like .git/config in artifacts.',
            'credentials': 'Avoid hardcoding credentials. Use GitHub secrets instead.',
            'runner-label': 'Use ephemeral self-hosted runners or GitHub-hosted runners for untrusted code.',
            'bot-check': 'Use more robust checks than github.actor for bot identity verification.',
            'local-action': 'Review local action for potential vulnerabilities.',
            'oidc-action': 'Review OIDC action for proper security configuration.',
            'shellcheck': 'Fix shell script issues identified by shellcheck.',
        }
        return recommendations.get(vuln_kind, 'Review and fix the identified security issue.')
    
    def _record_scan_history(self, db: DatabaseConnection, status: str, 
                            vuln_count: int, duration: int, error: Optional[str] = None):
        """Record scan attempt in history."""
        db.cursor.execute(
            """INSERT INTO scan_history 
               (repository_id, scan_queue_id, status, vulnerabilities_found, 
                duration_seconds, error_message, started_at, completed_at)
               VALUES (%s, %s, %s, %s, %s, %s, 
                       CURRENT_TIMESTAMP - INTERVAL '%s seconds', 
                       CURRENT_TIMESTAMP)""",
            (self.repository_id, self.scan_queue_id, status, 
             vuln_count, duration, error, duration)
        )
    
    def scan(self) -> bool:
        """Execute the scanning process."""
        start_time = datetime.now()
        clone_dir = '/tmp/repo_clone'
        workflows_dir = '/tmp/octoscan-workflows'
        
        try:
            # Check GitHub API rate limits before proceeding
            print("Checking GitHub API rate limits...")
            if not self.rate_limiter.wait_for_rate_limit(min_remaining=100):
                print("Rate limit check failed, aborting scan")
                return False
            
            # Initialize database connection
            with DatabaseConnection(self.database_url) as db:
                # Get or create repository entry
                self.repository_id = self._get_or_create_repository(db)
                
                # Find scan queue entry
                self._get_scan_queue_id(db)
                
                # Update scan queue to processing
                self._update_scan_queue(db, 'processing')
                db.conn.commit()
            
            # Clone repository for commit information
            print(f"Cloning repository: {self.repo_url}")
            if not self._clone_repository(clone_dir):
                with DatabaseConnection(self.database_url) as db:
                    self._update_scan_queue(db, 'failed', 'Failed to clone repository')
                    db.cursor.execute(
                        "UPDATE repositories SET scan_status = 'failed', scan_error = %s WHERE id = %s",
                        ('Failed to clone repository', self.repository_id)
                    )
                    duration = int((datetime.now() - start_time).total_seconds())
                    self._record_scan_history(db, 'failed', 0, duration, 'Failed to clone repository')
                return False
            
            # Download workflows from all branches using octoscan dl
            print("Downloading workflows from all branches...")
            if not self._download_workflows(workflows_dir):
                with DatabaseConnection(self.database_url) as db:
                    self._update_scan_queue(db, 'failed', 'Failed to download workflows')
                    db.cursor.execute(
                        "UPDATE repositories SET scan_status = 'failed', scan_error = %s WHERE id = %s",
                        ('Failed to download workflows', self.repository_id)
                    )
                    duration = int((datetime.now() - start_time).total_seconds())
                    self._record_scan_history(db, 'failed', 0, duration, 'Failed to download workflows')
                return False
            
            # Run octoscan analysis
            print("Running octoscan analysis...")
            scan_results = self._run_octoscan(workflows_dir)
            
            if scan_results is None:
                with DatabaseConnection(self.database_url) as db:
                    self._update_scan_queue(db, 'failed', 'Octoscan failed')
                    db.cursor.execute(
                        "UPDATE repositories SET scan_status = 'failed', scan_error = %s WHERE id = %s",
                        ('Octoscan analysis failed', self.repository_id)
                    )
                    duration = int((datetime.now() - start_time).total_seconds())
                    self._record_scan_history(db, 'failed', 0, duration, 'Octoscan analysis failed')
                return False
            
            # Store results in database
            print(f"Found {len(scan_results)} vulnerabilities")
            
            with DatabaseConnection(self.database_url) as db:
                self._store_vulnerabilities(db, scan_results, workflows_dir)
                
                # Update repository status
                db.cursor.execute(
                    "UPDATE repositories SET scan_status = 'completed', scan_error = NULL WHERE id = %s",
                    (self.repository_id,)
                )
                
                # Update scan queue
                self._update_scan_queue(db, 'completed')
                
                # Record scan history
                duration = int((datetime.now() - start_time).total_seconds())
                self._record_scan_history(db, 'completed', len(scan_results), duration)
            
            print("Scan completed successfully")
            return True
        
        except Exception as e:
            print(f"Scan failed with exception: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            
            try:
                with DatabaseConnection(self.database_url) as db:
                    error_msg = str(e)
                    self._update_scan_queue(db, 'failed', error_msg)
                    db.cursor.execute(
                        "UPDATE repositories SET scan_status = 'failed', scan_error = %s WHERE id = %s",
                        (error_msg, self.repository_id)
                    )
                    duration = int((datetime.now() - start_time).total_seconds())
                    self._record_scan_history(db, 'failed', 0, duration, error_msg)
            except Exception as db_error:
                print(f"Failed to update database after error: {db_error}", file=sys.stderr)
            
            return False
        
        finally:
            # Cleanup
            for dir_path in [clone_dir, workflows_dir]:
                if os.path.exists(dir_path):
                    subprocess.run(['rm', '-rf', dir_path], capture_output=True)


def main():
    """Main entry point for the worker."""
    # Get configuration from environment
    repo_url = os.getenv('REPO_URL')
    database_url = os.getenv('DATABASE_URL')
    github_token = os.getenv('GITHUB_TOKEN')
    
    if not repo_url:
        print("Error: REPO_URL environment variable is required", file=sys.stderr)
        sys.exit(1)
    
    if not database_url:
        print("Error: DATABASE_URL environment variable is required", file=sys.stderr)
        sys.exit(1)
    
    # Create scanner and run
    scanner = GitHubScanner(repo_url, database_url, github_token)
    success = scanner.scan()
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
