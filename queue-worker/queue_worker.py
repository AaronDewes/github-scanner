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
from typing import Optional, List
import psycopg2
from psycopg2.extras import RealDictCursor
from kubernetes import client, config
from kubernetes.client.rest import ApiException


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
        # Count currently running jobs
        running_jobs = self.job_manager.count_running_jobs()
        print(f"Currently running jobs: {running_jobs}/{self.max_concurrent_jobs}")
        
        # Calculate how many new jobs we can start
        available_slots = self.max_concurrent_jobs - running_jobs
        
        if available_slots <= 0:
            print("Max concurrent jobs reached, waiting...")
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
