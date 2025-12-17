#!/usr/bin/env python3
"""
GitHub Scanner Scheduler

Fetches top GitHub repositories and queues them for scanning.
Handles GitHub API rate limiting and tracks rate limit status.
"""

import os
import sys
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set
import requests
import psycopg2
from psycopg2.extras import RealDictCursor


class GitHubAPIClient:
    """GitHub API client with rate limit handling."""
    
    def __init__(self, token: Optional[str] = None):
        self.token = token
        self.base_url = "https://api.github.com"
        self.session = requests.Session()
        
        if token:
            self.session.headers.update({
                'Authorization': f'token {token}',
                'Accept': 'application/vnd.github.v3+json'
            })
        else:
            print("Warning: No GitHub token provided. Rate limits will be very restrictive.")
    
    def _check_rate_limit(self) -> Dict:
        """Check current rate limit status."""
        try:
            response = self.session.get(f"{self.base_url}/rate_limit")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error checking rate limit: {e}", file=sys.stderr)
            return {}
    
    def _wait_for_rate_limit(self, rate_limit_info: Dict):
        """Wait if rate limit is exceeded."""
        if 'rate' in rate_limit_info:
            remaining = rate_limit_info['rate'].get('remaining', 0)
            reset_time = rate_limit_info['rate'].get('reset', 0)
            
            if remaining < 10:  # Leave some buffer
                wait_time = reset_time - time.time()
                if wait_time > 0:
                    print(f"Rate limit almost exhausted. Waiting {int(wait_time)} seconds...")
                    time.sleep(wait_time + 1)
    
    def search_repositories(self, query: str, per_page: int = 100, max_results: int = 1000) -> List[Dict]:
        """Search for repositories."""
        repos = []
        page = 1
        
        while len(repos) < max_results:
            try:
                # Check rate limit before request
                rate_limit = self._check_rate_limit()
                self._wait_for_rate_limit(rate_limit)
                
                params = {
                    'q': query,
                    'sort': 'stars',
                    'order': 'desc',
                    'per_page': per_page,
                    'page': page
                }
                
                response = self.session.get(f"{self.base_url}/search/repositories", params=params)
                
                if response.status_code == 403:
                    print("Rate limit exceeded. Waiting...")
                    time.sleep(60)
                    continue
                
                response.raise_for_status()
                data = response.json()
                
                items = data.get('items', [])
                if not items:
                    break
                
                repos.extend(items)
                
                # GitHub search API only returns up to 1000 results
                if len(items) < per_page or len(repos) >= min(1000, max_results):
                    break
                
                page += 1
                time.sleep(1)  # Be nice to the API
            
            except Exception as e:
                print(f"Error searching repositories: {e}", file=sys.stderr)
                break
        
        return repos[:max_results]
    
    def get_repository(self, owner: str, repo: str) -> Optional[Dict]:
        """Get repository details."""
        try:
            response = self.session.get(f"{self.base_url}/repos/{owner}/{repo}")
            
            if response.status_code == 404:
                return None
            
            response.raise_for_status()
            return response.json()
        
        except Exception as e:
            print(f"Error fetching repository {owner}/{repo}: {e}", file=sys.stderr)
            return None
    
    def list_user_repos(self, username: str, per_page: int = 100) -> List[Dict]:
        """List all repositories for a user/organization."""
        repos = []
        page = 1
        
        while True:
            try:
                # Check rate limit
                rate_limit = self._check_rate_limit()
                self._wait_for_rate_limit(rate_limit)
                
                params = {
                    'per_page': per_page,
                    'page': page
                }
                
                # Try as user first, then as org
                response = self.session.get(f"{self.base_url}/users/{username}/repos", params=params)
                
                if response.status_code == 404:
                    # Try as organization
                    response = self.session.get(f"{self.base_url}/orgs/{username}/repos", params=params)
                
                if response.status_code == 403:
                    print("Rate limit exceeded. Waiting...")
                    time.sleep(60)
                    continue
                
                response.raise_for_status()
                items = response.json()
                
                if not items:
                    break
                
                repos.extend(items)
                
                if len(items) < per_page:
                    break
                
                page += 1
                time.sleep(0.5)  # Be nice to the API
            
            except Exception as e:
                print(f"Error listing repositories for {username}: {e}", file=sys.stderr)
                break
        
        return repos
    
    def has_github_actions(self, owner: str, repo: str) -> bool:
        """Check if repository has any GitHub Actions runs."""
        try:
            # Check if there have been any workflow runs
            response = self.session.get(
                f"{self.base_url}/repos/{owner}/{repo}/actions/runs",
                params={'per_page': 1}
            )
            
            if response.status_code == 404:
                # Actions not enabled or no runs
                return False
            
            if response.status_code == 403:
                # Rate limit or permissions issue, wait
                time.sleep(2)
                return False
            
            response.raise_for_status()
            data = response.json()
            
            # Check if there are any workflow runs
            total_count = data.get('total_count', 0)
            return total_count > 0
        
        except Exception as e:
            print(f"Error checking GitHub Actions for {owner}/{repo}: {e}", file=sys.stderr)
            return False


class Scheduler:
    """Main scheduler class."""
    
    def __init__(self, database_url: str, github_token: Optional[str] = None, debug_mode: bool = False):
        self.database_url = database_url
        self.github_client = GitHubAPIClient(token=github_token)
        self.debug_mode = debug_mode
        
        if debug_mode:
            print("=" * 60)
            print("DEBUG MODE ENABLED - No database interactions")
            print("=" * 60)
    
    def _get_db_connection(self):
        """Get database connection."""
        return psycopg2.connect(self.database_url)
    
    def _store_rate_limit(self, conn, api_type: str, limit: int, remaining: int, reset_time: int):
        """Store rate limit information."""
        with conn.cursor() as cursor:
            cursor.execute(
                """INSERT INTO rate_limits (api_type, limit_value, remaining, reset_at)
                   VALUES (%s, %s, %s, to_timestamp(%s))""",
                (api_type, limit, remaining, reset_time)
            )
            conn.commit()
    
    def _queue_repository(self, conn, repo_data: Dict, priority: int = 0) -> bool:
        """Add repository to scan queue."""
        try:
            owner = repo_data.get('owner', {}).get('login', '')
            name = repo_data.get('name', '')
            url = repo_data.get('html_url', '')
            archived = repo_data.get('archived', False)
            stars = repo_data.get('stargazers_count', 0)
            
            if not owner or not name or not url:
                return False
            
            # Skip archived repositories
            if archived:
                if self.debug_mode:
                    print(f"[SKIP] {owner}/{name} - archived")
                else:
                    print(f"Skipping {owner}/{name} - repository is archived")
                return False
            
            # Check if repo has GitHub Actions runs
            has_actions = self.github_client.has_github_actions(owner, name)
            
            if not has_actions:
                if self.debug_mode:
                    print(f"[SKIP] {owner}/{name} - no actions runs")
                else:
                    print(f"Skipping {owner}/{name} - no GitHub Actions runs")
                return False
            
            # Debug mode: just print and return
            if self.debug_mode:
                print(f"[FOUND] {owner}/{name}")
                print(f"        URL: {url}")
                print(f"        Stars: {stars}")
                print(f"        Priority: {priority}")
                print(f"        Has Actions: Yes")
                print()
                return True
            
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                
                # Insert or update repository
                cursor.execute(
                    """INSERT INTO repositories (url, owner, name, has_actions)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (owner, name) DO UPDATE
                       SET url = EXCLUDED.url, has_actions = EXCLUDED.has_actions
                       RETURNING id""",
                    (url, owner, name, has_actions)
                )
                repo = cursor.fetchone()
                repository_id = repo['id']
                
                # Check if already in queue or recently scanned
                cursor.execute(
                    """SELECT sq.id, r.last_scanned_at
                       FROM repositories r
                       LEFT JOIN scan_queue sq ON r.id = sq.repository_id 
                         AND sq.status IN ('queued', 'processing')
                       WHERE r.id = %s""",
                    (repository_id,)
                )
                result = cursor.fetchone()
                
                # Skip if already queued
                if result and result['id']:
                    print(f"Skipping {owner}/{name} - already queued")
                    return False
                
                # Skip if scanned in last 7 days
                if result and result['last_scanned_at']:
                    days_since_scan = (datetime.now() - result['last_scanned_at']).days
                    if days_since_scan < 7:
                        print(f"Skipping {owner}/{name} - scanned {days_since_scan} days ago")
                        return False
                
                # Add to queue
                cursor.execute(
                    """INSERT INTO scan_queue (repository_id, priority, status)
                       VALUES (%s, %s, 'queued')""",
                    (repository_id, priority)
                )
                conn.commit()
                
                print(f"Queued {owner}/{name} for scanning")
                return True
        
        except Exception as e:
            print(f"Error queuing repository: {e}", file=sys.stderr)
            conn.rollback()
            return False
    
    def fetch_top_repositories(self, count: int = 10000):
        """Fetch top repositories and queue them for scanning."""
        print(f"Fetching top {count} repositories...")
        
        # Search for repositories with many stars, excluding archived repos
        repos = self.github_client.search_repositories(
            query="stars:>100 archived:false",
            max_results=count
        )
        
        print(f"Found {len(repos)} repositories")
        
        if self.debug_mode:
            print(f"\n{'=' * 60}")
            print("Processing repositories...")
            print(f"{'=' * 60}\n")
        
        conn = None if self.debug_mode else self._get_db_connection()
        
        try:
            queued_count = 0
            owners_seen: Set[str] = set()
            
            # Queue top repositories
            for repo in repos:
                if self._queue_repository(conn, repo, priority=10):
                    queued_count += 1
                
                # Track owners for expansion
                owner = repo.get('owner', {}).get('login')
                if owner:
                    owners_seen.add(owner)
            
            print(f"Queued {queued_count} repositories from search")
            
            # Expand to include more repos from same owners
            print(f"Expanding to repositories from {len(owners_seen)} owners...")
            expanded_count = 0
            
            for owner in owners_seen:
                owner_repos = self.github_client.list_user_repos(owner)
                
                for repo in owner_repos:
                    if self._queue_repository(conn, repo, priority=5):
                        expanded_count += 1
                
                # Limit expansion to avoid overwhelming the queue
                if expanded_count > count * 2:
                    break
            
            print(f"Queued {expanded_count} additional repositories from expansion")
            print(f"Total queued: {queued_count + expanded_count}")
        
        finally:
            if conn:
                conn.close()
    
    def run(self, interval: int = 86400):
        """Run scheduler in a loop."""
        print("Starting GitHub Scanner Scheduler")
        if self.debug_mode:
            print("Running in DEBUG mode - no database operations")
        print(f"Scan interval: {interval} seconds ({interval / 3600:.1f} hours)")
        
        while True:
            try:
                start_time = datetime.now()
                print(f"\n[{start_time}] Starting scan scheduling...")
                
                # Get top repos count from env
                top_repos_count = int(os.getenv('TOP_REPOS_COUNT', '10000'))
                
                # Fetch and queue repositories
                self.fetch_top_repositories(count=top_repos_count)
                
                duration = (datetime.now() - start_time).total_seconds()
                print(f"Scheduling completed in {duration:.1f} seconds")
                
                # In debug mode, exit after one run
                if self.debug_mode:
                    print("\nDebug mode: exiting after one run")
                    break
                
                # Wait for next interval
                print(f"Waiting {interval} seconds until next scan...")
                time.sleep(interval)
            
            except KeyboardInterrupt:
                print("\nScheduler stopped by user")
                break
            except Exception as e:
                print(f"Scheduler error: {e}", file=sys.stderr)
                print("Waiting 5 minutes before retry...")
                time.sleep(300)


def main():
    """Main entry point."""
    database_url = os.getenv('DATABASE_URL')
    github_token = os.getenv('GITHUB_TOKEN')
    scan_interval = int(os.getenv('SCAN_INTERVAL', '86400'))
    debug_mode = os.getenv('DEBUG_MODE', '').lower() in ('true', '1', 'yes')
    
    if not debug_mode and not database_url:
        print("Error: DATABASE_URL environment variable is required", file=sys.stderr)
        print("Hint: Set DEBUG_MODE=true to run without database", file=sys.stderr)
        sys.exit(1)
    
    if not github_token:
        print("Warning: GITHUB_TOKEN not set. Rate limits will be restrictive.")
    
    scheduler = Scheduler(database_url, github_token, debug_mode=debug_mode)
    scheduler.run(interval=scan_interval)


if __name__ == '__main__':
    main()
