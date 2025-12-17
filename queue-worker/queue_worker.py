#!/usr/bin/env python3
"""
GitHub Scanner Queue Worker

Processes the scan queue and creates Kubernetes jobs for pending scans.
Ensures no more than a specified number of concurrent jobs are running.
"""

import os
import sys
import time
from datetime import datetime
from typing import Optional, List, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import requests


class GitHubRateLimiter:
    """Handles GitHub API rate limit checking."""
    
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
    
    def check_rate_limit(self) -> dict:
        """Check current GitHub API rate limit status."""
        try:
            response = self.session.get(f"{self.base_url}/rate_limit")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error checking rate limit: {e}", file=sys.stderr)
            return {}
    
    def store_rate_limit(self, rate_limit_info: dict):
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
    
    def get_rate_limit_status(self) -> Tuple[int, int, int]:
        """
        Get current rate limit status.
        
        Returns:
            Tuple of (remaining, limit, reset_timestamp)
        """
        rate_limit_info = self.check_rate_limit()
        
        if not rate_limit_info:
            return 5000, 5000, 0  # Assume OK if can't check
        
        # Store the rate limit info
        self.store_rate_limit(rate_limit_info)
        
        core = rate_limit_info.get('resources', {}).get('core', {})
        remaining = core.get('remaining', 5000)
        limit = core.get('limit', 5000)
        reset_time = core.get('reset', 0)
        
        return remaining, limit, reset_time
    
    def calculate_safe_jobs(self, requests_per_job: int = 50) -> int:
        """
        Calculate how many jobs can safely run given current rate limits.
        
        Args:
            requests_per_job: Estimated API requests per scan job
            
        Returns:
            Number of jobs that can be safely started
        """
        remaining, limit, reset_time = self.get_rate_limit_status()
        
        # Keep a buffer of 500 requests
        available = max(0, remaining - 500)
        
        safe_jobs = available // requests_per_job
        
        print(f"Rate limit: {remaining}/{limit} remaining, can safely run {safe_jobs} jobs")
        
        return safe_jobs
    
    def wait_if_needed(self, min_remaining: int = 500) -> bool:
        """
        Wait if rate limit is too low.
        
        Returns:
            True if ready to proceed, False if should skip this cycle
        """
        remaining, limit, reset_time = self.get_rate_limit_status()
        
        if remaining < min_remaining:
            wait_time = reset_time - time.time()
            if wait_time > 0 and wait_time <= 900:  # Wait max 15 minutes
                print(f"Rate limit low ({remaining} remaining). Waiting {int(wait_time)} seconds...")
                time.sleep(wait_time + 5)
                return True
            elif wait_time > 900:
                print(f"Rate limit low, reset in {int(wait_time)}s. Skipping this cycle.")
                return False
        
        return True


class KubernetesJobManager:
    """Manages Kubernetes jobs for repository scanning."""
    
    def __init__(self, namespace: str = "default", image: str = "ghcr.io/aarondewes/github-scanner-worker:main"):
        self.namespace = namespace
        self.image = image
        
        # Try to load in-cluster config first, fall back to kubeconfig
        try:
            config.load_incluster_config()
        except config.ConfigException:
            try:
                config.load_kube_config()
            except config.ConfigException:
                print("Error: Could not load Kubernetes config", file=sys.stderr)
                sys.exit(1)
        
        self.batch_v1 = client.BatchV1Api()
        self.core_v1 = client.CoreV1Api()
    
    def _sanitize_job_name(self, repo_owner: str, repo_name: str, scan_id: int) -> str:
        """Create a valid Kubernetes job name."""
        import re
        name = f"scan-{repo_owner}-{repo_name}-{scan_id}".lower()
        name = re.sub(r'[^a-z0-9-]', '-', name)
        name = re.sub(r'-+', '-', name)
        name = name[:63]
        return name.strip('-')
    
    def create_scan_job(
        self,
        repo_url: str,
        repo_owner: str,
        repo_name: str,
        scan_queue_id: int,
        github_token: str,
        database_url: str
    ) -> Optional[str]:
        """Create a Kubernetes job for scanning a repository."""
        
        job_name = self._sanitize_job_name(repo_owner, repo_name, scan_queue_id)
        
        # Define the job
        job = client.V1Job(
            api_version="batch/v1",
            kind="Job",
            metadata=client.V1ObjectMeta(
                name=job_name,
                labels={
                    "app": "github-scanner",
                    "component": "worker",
                    "scan-id": str(scan_queue_id)
                }
            ),
            spec=client.V1JobSpec(
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(
                        labels={
                            "app": "github-scanner",
                            "component": "worker"
                        }
                    ),
                    spec=client.V1PodSpec(
                        restart_policy="Never",
                        containers=[
                            client.V1Container(
                                name="scanner",
                                image=self.image,
                                image_pull_policy="Always",
                                env=[
                                    client.V1EnvVar(
                                        name="REPO_URL",
                                        value=repo_url
                                    ),
                                    client.V1EnvVar(
                                        name="DATABASE_URL",
                                        value=database_url
                                    ),
                                    client.V1EnvVar(
                                        name="GITHUB_TOKEN",
                                        value=github_token
                                    )
                                ],
                                resources=client.V1ResourceRequirements(
                                    requests={
                                        "cpu": "500m",
                                        "memory": "1Gi"
                                    },
                                    limits={
                                        "cpu": "2",
                                        "memory": "4Gi"
                                    }
                                )
                            )
                        ]
                    )
                ),
                backoff_limit=3,
                ttl_seconds_after_finished=3600
            )
        )
        
        try:
            self.batch_v1.create_namespaced_job(
                namespace=self.namespace,
                body=job
            )
            print(f"Created job {job_name} for {repo_owner}/{repo_name}")
            return job_name
        
        except ApiException as e:
            if e.status == 409:
                print(f"Job {job_name} already exists")
                return job_name
            print(f"Error creating job: {e}", file=sys.stderr)
            return None
        except Exception as e:
            print(f"Error creating job: {e}", file=sys.stderr)
            return None
    
    def count_running_jobs(self) -> int:
        """Count the number of currently running scanner jobs."""
        try:
            jobs = self.batch_v1.list_namespaced_job(
                namespace=self.namespace,
                label_selector="app=github-scanner,component=worker"
            )
            
            running_count = 0
            for job in jobs.items:
                # Check if job is still active (not completed or failed)
                if job.status.active and job.status.active > 0:
                    running_count += 1
            
            return running_count
        
        except Exception as e:
            print(f"Error counting running jobs: {e}", file=sys.stderr)
            return 0
    
    def cleanup_old_jobs(self, max_age_hours: int = 24):
        """Clean up completed jobs older than specified hours."""
        try:
            jobs = self.batch_v1.list_namespaced_job(
                namespace=self.namespace,
                label_selector="app=github-scanner,component=worker"
            )
            
            cutoff_time = datetime.now().timestamp() - (max_age_hours * 3600)
            
            for job in jobs.items:
                # Check if job is completed and old
                if job.status.completion_time:
                    completion_timestamp = job.status.completion_time.timestamp()
                    if completion_timestamp < cutoff_time:
                        try:
                            self.batch_v1.delete_namespaced_job(
                                name=job.metadata.name,
                                namespace=self.namespace,
                                body=client.V1DeleteOptions(
                                    propagation_policy='Foreground'
                                )
                            )
                            print(f"Cleaned up old job: {job.metadata.name}")
                        except Exception as e:
                            print(f"Error deleting job {job.metadata.name}: {e}", file=sys.stderr)
        
        except Exception as e:
            print(f"Error cleaning up old jobs: {e}", file=sys.stderr)


class QueueWorker:
    """Queue worker that processes pending scans."""
    
    def __init__(
        self,
        database_url: str,
        github_token: str,
        namespace: str = "default",
        max_concurrent_jobs: int = 10,
        poll_interval: int = 30,
        worker_image: str = "ghcr.io/aarondewes/github-scanner-worker:main"
    ):
        self.database_url = database_url
        self.github_token = github_token
        self.max_concurrent_jobs = max_concurrent_jobs
        self.poll_interval = poll_interval
        
        self.job_manager = KubernetesJobManager(
            namespace=namespace,
            image=worker_image
        )
        
        self.rate_limiter = GitHubRateLimiter(
            token=github_token,
            database_url=database_url
        )
    
    def _get_db_connection(self):
        """Get database connection."""
        return psycopg2.connect(self.database_url)
    
    def _get_pending_scans(self, conn, limit: int = 10) -> List[dict]:
        """Get pending scans from the queue."""
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """SELECT sq.id, sq.repository_id, r.url, r.owner, r.name
                   FROM scan_queue sq
                   JOIN repositories r ON sq.repository_id = r.id
                   WHERE sq.status = 'queued'
                   ORDER BY sq.priority DESC, sq.queued_at ASC
                   LIMIT %s""",
                (limit,)
            )
            return cursor.fetchall()
    
    def _update_scan_status(self, conn, scan_id: int, status: str, job_name: Optional[str] = None):
        """Update scan queue status."""
        with conn.cursor() as cursor:
            if status == 'processing' and job_name:
                cursor.execute(
                    """UPDATE scan_queue 
                       SET status = %s, started_at = CURRENT_TIMESTAMP, job_name = %s
                       WHERE id = %s""",
                    (status, job_name, scan_id)
                )
            elif status == 'failed':
                cursor.execute(
                    """UPDATE scan_queue 
                       SET status = %s, completed_at = CURRENT_TIMESTAMP,
                           error_message = 'Failed to create job'
                       WHERE id = %s""",
                    (status, scan_id)
                )
            else:
                cursor.execute(
                    "UPDATE scan_queue SET status = %s WHERE id = %s",
                    (status, scan_id)
                )
            conn.commit()
    
    def process_queue(self):
        """Process pending scans in the queue."""
        # Check GitHub API rate limits first
        if not self.rate_limiter.wait_if_needed(min_remaining=500):
            print("Rate limit too low, skipping this cycle")
            return
        
        # Calculate how many jobs are safe given rate limits
        rate_limit_jobs = self.rate_limiter.calculate_safe_jobs(requests_per_job=50)
        
        if rate_limit_jobs <= 0:
            print("Rate limit does not allow new jobs, waiting...")
            return
        
        # Count currently running jobs
        running_jobs = self.job_manager.count_running_jobs()
        print(f"Currently running jobs: {running_jobs}/{self.max_concurrent_jobs}")
        
        # Calculate how many new jobs we can start (min of concurrent limit and rate limit)
        available_slots = self.max_concurrent_jobs - running_jobs
        available_slots = min(available_slots, rate_limit_jobs)
        
        if available_slots <= 0:
            print("No available slots (concurrent limit or rate limit), waiting...")
            return
        
        # Get pending scans
        conn = self._get_db_connection()
        try:
            pending_scans = self._get_pending_scans(conn, limit=available_slots)
            
            if not pending_scans:
                print("No pending scans in queue")
                return
            
            print(f"Processing {len(pending_scans)} pending scans...")
            
            for scan in pending_scans:
                # Create Kubernetes job
                job_name = self.job_manager.create_scan_job(
                    repo_url=scan['url'],
                    repo_owner=scan['owner'],
                    repo_name=scan['name'],
                    scan_queue_id=scan['id'],
                    github_token=self.github_token,
                    database_url=self.database_url
                )
                
                if job_name:
                    # Update status to processing
                    self._update_scan_status(conn, scan['id'], 'processing', job_name)
                    print(f"Started scan for {scan['owner']}/{scan['name']}")
                else:
                    # Mark as failed
                    self._update_scan_status(conn, scan['id'], 'failed')
                    print(f"Failed to create job for {scan['owner']}/{scan['name']}")
        
        finally:
            conn.close()
    
    def run(self):
        """Run the queue worker loop."""
        print("Starting Queue Worker")
        print(f"Max concurrent jobs: {self.max_concurrent_jobs}")
        print(f"Poll interval: {self.poll_interval} seconds")
        print(f"Worker image: {self.job_manager.image}")
        print()
        
        while True:
            try:
                start_time = datetime.now()
                print(f"\n[{start_time}] Processing queue...")
                
                # Process the queue
                self.process_queue()
                
                # Cleanup old jobs (once per hour)
                if start_time.minute == 0:
                    print("Running cleanup of old jobs...")
                    self.job_manager.cleanup_old_jobs()
                
                duration = (datetime.now() - start_time).total_seconds()
                print(f"Queue processing completed in {duration:.1f} seconds")
                
                # Wait for next poll
                print(f"Waiting {self.poll_interval} seconds until next poll...")
                time.sleep(self.poll_interval)
            
            except KeyboardInterrupt:
                print("\nQueue worker stopped by user")
                break
            except Exception as e:
                print(f"Queue worker error: {e}", file=sys.stderr)
                import traceback
                traceback.print_exc()
                print("Waiting 60 seconds before retry...")
                time.sleep(60)


def main():
    """Main entry point."""
    database_url = os.getenv('DATABASE_URL')
    github_token = os.getenv('GITHUB_TOKEN')
    namespace = os.getenv('KUBERNETES_NAMESPACE', 'default')
    max_concurrent_jobs = int(os.getenv('MAX_CONCURRENT_JOBS', '10'))
    poll_interval = int(os.getenv('POLL_INTERVAL', '30'))
    worker_image = os.getenv('WORKER_IMAGE', 'ghcr.io/aarondewes/github-scanner-worker:main')
    
    if not database_url:
        print("Error: DATABASE_URL environment variable is required", file=sys.stderr)
        sys.exit(1)
    
    if not github_token:
        print("Error: GITHUB_TOKEN environment variable is required", file=sys.stderr)
        sys.exit(1)
    
    worker = QueueWorker(
        database_url=database_url,
        github_token=github_token,
        namespace=namespace,
        max_concurrent_jobs=max_concurrent_jobs,
        poll_interval=poll_interval,
        worker_image=worker_image
    )
    
    worker.run()


if __name__ == '__main__':
    main()
