"""
Kubernetes utilities for managing scan jobs
"""

import os
import re
from typing import Optional
from kubernetes import client, config
from kubernetes.client.rest import ApiException


class KubernetesJobManager:
    """Manages Kubernetes jobs for repository scanning."""
    
    def __init__(self, namespace: str = "default"):
        self.namespace = namespace
        
        # Try to load in-cluster config first, fall back to kubeconfig
        try:
            config.load_incluster_config()
        except config.ConfigException:
            try:
                config.load_kube_config()
            except config.ConfigException:
                print("Warning: Could not load Kubernetes config. Jobs will not be created.")
                self.batch_v1 = None
                return
        
        self.batch_v1 = client.BatchV1Api()
    
    def _sanitize_job_name(self, repo_owner: str, repo_name: str, scan_id: int) -> str:
        """Create a valid Kubernetes job name."""
        # Kubernetes names must be lowercase alphanumeric with hyphens
        name = f"scan-{repo_owner}-{repo_name}-{scan_id}".lower()
        name = re.sub(r'[^a-z0-9-]', '-', name)
        name = re.sub(r'-+', '-', name)  # Replace multiple hyphens with single
        name = name[:63]  # Max length for Kubernetes names
        return name.strip('-')
    
    def create_scan_job(
        self,
        repo_url: str,
        repo_owner: str,
        repo_name: str,
        scan_queue_id: int,
        image: str = "ghcr.io/aarondewes/github-scanner-worker:main",
        queue_name: str = "scanner-queue"
    ) -> Optional[str]:
        """Create a Kubernetes job for scanning a repository."""
        
        if self.batch_v1 is None:
            print("Warning: Kubernetes client not initialized. Cannot create job.")
            return None
        
        job_name = self._sanitize_job_name(repo_owner, repo_name, scan_queue_id)
        
        # Get database URL from environment
        database_url = os.getenv('DATABASE_URL')
        github_token = os.getenv('GITHUB_TOKEN')
        
        # Define the job
        job = client.V1Job(
            api_version="batch/v1",
            kind="Job",
            metadata=client.V1ObjectMeta(
                name=job_name,
                labels={
                    "app": "github-scanner",
                    "component": "worker",
                    "kueue.x-k8s.io/queue-name": queue_name,
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
                                image=image,
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
                ttl_seconds_after_finished=3600  # Clean up after 1 hour
            )
        )
        
        try:
            # Create the job
            self.batch_v1.create_namespaced_job(
                namespace=self.namespace,
                body=job
            )
            print(f"Created job: {job_name}")
            return job_name
        
        except ApiException as e:
            print(f"Exception when creating job: {e}")
            return None
    
    def get_job_status(self, job_name: str) -> Optional[dict]:
        """Get the status of a job."""
        
        if self.batch_v1 is None:
            return None
        
        try:
            job = self.batch_v1.read_namespaced_job(
                name=job_name,
                namespace=self.namespace
            )
            
            status = {
                "active": job.status.active or 0,
                "succeeded": job.status.succeeded or 0,
                "failed": job.status.failed or 0,
                "start_time": job.status.start_time,
                "completion_time": job.status.completion_time
            }
            
            return status
        
        except ApiException as e:
            print(f"Exception when reading job status: {e}")
            return None
    
    def delete_job(self, job_name: str) -> bool:
        """Delete a job."""
        
        if self.batch_v1 is None:
            return False
        
        try:
            self.batch_v1.delete_namespaced_job(
                name=job_name,
                namespace=self.namespace,
                body=client.V1DeleteOptions(
                    propagation_policy='Background'
                )
            )
            print(f"Deleted job: {job_name}")
            return True
        
        except ApiException as e:
            print(f"Exception when deleting job: {e}")
            return False
