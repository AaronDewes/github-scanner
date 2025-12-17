"""
GitHub Scanner API

FastAPI-based REST API for managing repository scans and viewing vulnerabilities.
"""

import os
import re
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from psycopg2.extras import RealDictCursor

from models import (
    Repository, Vulnerability, VulnerabilityUpdate, 
    ScanRequest, ScanResponse, ScanQueueItem,
    VulnerabilityStats, PaginatedResponse, HealthCheck
)
from database import get_db_connection, get_db_cursor
from kubernetes_utils import KubernetesJobManager


# Initialize FastAPI app
app = FastAPI(
    title="GitHub Security Scanner API",
    description="API for scanning GitHub repositories for security vulnerabilities",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Kubernetes job manager
k8s_namespace = os.getenv('KUEUE_NAMESPACE', 'default')
job_manager = KubernetesJobManager(namespace=k8s_namespace)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "GitHub Security Scanner API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health", response_model=HealthCheck)
async def health_check():
    """Health check endpoint."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"
    
    return HealthCheck(
        status="healthy" if db_status == "connected" else "unhealthy",
        database=db_status,
        timestamp=datetime.now()
    )


def parse_github_url(url: str) -> tuple[str, str]:
    """Parse GitHub URL to extract owner and repo name."""
    patterns = [
        r'github\.com[:/]([^/]+)/([^/\.]+)',
        r'github\.com/([^/]+)/([^/]+)\.git',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1), match.group(2)
    
    raise ValueError(f"Invalid GitHub repository URL: {url}")


@app.post("/api/v1/scan", response_model=ScanResponse)
async def trigger_scan(scan_request: ScanRequest):
    """
    Trigger a repository scan.
    
    Creates a scan queue entry and submits a Kubernetes job.
    """
    try:
        # Parse repository URL
        owner, repo_name = parse_github_url(scan_request.repo_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Get or create repository
                cursor.execute(
                    """INSERT INTO repositories (url, owner, name, has_actions)
                       VALUES (%s, %s, %s, TRUE)
                       ON CONFLICT (owner, name) DO UPDATE
                       SET url = EXCLUDED.url
                       RETURNING id""",
                    (scan_request.repo_url, owner, repo_name)
                )
                repo = cursor.fetchone()
                repository_id = repo['id']
                
                # Create scan queue entry
                cursor.execute(
                    """INSERT INTO scan_queue (repository_id, priority, status)
                       VALUES (%s, %s, 'queued')
                       RETURNING id""",
                    (repository_id, scan_request.priority)
                )
                queue_item = cursor.fetchone()
                scan_queue_id = queue_item['id']
                
                conn.commit()
        
        # Create Kubernetes job
        job_name = job_manager.create_scan_job(
            repo_url=scan_request.repo_url,
            repo_owner=owner,
            repo_name=repo_name,
            scan_queue_id=scan_queue_id
        )
        
        # Update queue with job name
        if job_name:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "UPDATE scan_queue SET job_name = %s WHERE id = %s",
                        (job_name, scan_queue_id)
                    )
                    conn.commit()
        
        return ScanResponse(
            message="Scan queued successfully",
            repository_id=repository_id,
            scan_queue_id=scan_queue_id
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue scan: {str(e)}")


@app.get("/api/v1/repositories", response_model=PaginatedResponse)
async def list_repositories(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    status: Optional[str] = None
):
    """List all repositories."""
    offset = (page - 1) * page_size
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Build query
                where_clause = ""
                params = []
                if status:
                    where_clause = "WHERE scan_status = %s"
                    params.append(status)
                
                # Get total count
                cursor.execute(
                    f"SELECT COUNT(*) as count FROM repositories {where_clause}",
                    params
                )
                total = cursor.fetchone()['count']
                
                # Get paginated results
                params.extend([page_size, offset])
                cursor.execute(
                    f"""SELECT * FROM repositories {where_clause}
                       ORDER BY last_scanned_at DESC NULLS LAST, created_at DESC
                       LIMIT %s OFFSET %s""",
                    params
                )
                repositories = cursor.fetchall()
        
        return PaginatedResponse(
            total=total,
            page=page,
            page_size=page_size,
            data=[dict(repo) for repo in repositories]
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/repositories/{repository_id}", response_model=Repository)
async def get_repository(repository_id: int):
    """Get repository details."""
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    "SELECT * FROM repositories WHERE id = %s",
                    (repository_id,)
                )
                repo = cursor.fetchone()
                
                if not repo:
                    raise HTTPException(status_code=404, detail="Repository not found")
                
                return Repository(**repo)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/vulnerabilities", response_model=PaginatedResponse)
async def list_vulnerabilities(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    repository_id: Optional[int] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None
):
    """List vulnerabilities with optional filters."""
    offset = (page - 1) * page_size
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Build query
                where_clauses = []
                params = []
                
                if repository_id:
                    where_clauses.append("repository_id = %s")
                    params.append(repository_id)
                
                if severity:
                    where_clauses.append("severity = %s")
                    params.append(severity)
                
                if status:
                    where_clauses.append("status = %s")
                    params.append(status)
                
                where_clause = ""
                if where_clauses:
                    where_clause = "WHERE " + " AND ".join(where_clauses)
                
                # Get total count
                cursor.execute(
                    f"SELECT COUNT(*) as count FROM vulnerabilities {where_clause}",
                    params
                )
                total = cursor.fetchone()['count']
                
                # Get paginated results
                params.extend([page_size, offset])
                cursor.execute(
                    f"""SELECT * FROM vulnerabilities {where_clause}
                       ORDER BY 
                         CASE severity 
                           WHEN 'critical' THEN 1
                           WHEN 'high' THEN 2
                           WHEN 'medium' THEN 3
                           WHEN 'low' THEN 4
                           ELSE 5
                         END,
                         detected_at DESC
                       LIMIT %s OFFSET %s""",
                    params
                )
                vulnerabilities = cursor.fetchall()
        
        return PaginatedResponse(
            total=total,
            page=page,
            page_size=page_size,
            data=[dict(vuln) for vuln in vulnerabilities]
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/vulnerabilities/{vulnerability_id}", response_model=Vulnerability)
async def get_vulnerability(vulnerability_id: int):
    """Get vulnerability details."""
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    "SELECT * FROM vulnerabilities WHERE id = %s",
                    (vulnerability_id,)
                )
                vuln = cursor.fetchone()
                
                if not vuln:
                    raise HTTPException(status_code=404, detail="Vulnerability not found")
                
                return Vulnerability(**vuln)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/v1/vulnerabilities/{vulnerability_id}/analysis")
async def update_vulnerability_analysis(
    vulnerability_id: int,
    update: VulnerabilityUpdate
):
    """Update manual analysis for a vulnerability."""
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Check if vulnerability exists
                cursor.execute(
                    "SELECT id FROM vulnerabilities WHERE id = %s",
                    (vulnerability_id,)
                )
                if not cursor.fetchone():
                    raise HTTPException(status_code=404, detail="Vulnerability not found")
                
                # Build update query
                update_fields = []
                params = []
                
                if update.status is not None:
                    update_fields.append("status = %s")
                    params.append(update.status)
                
                if update.manual_analysis is not None:
                    update_fields.append("manual_analysis = %s")
                    params.append(update.manual_analysis)
                
                if update.analyzed_by is not None:
                    update_fields.append("analyzed_by = %s")
                    params.append(update.analyzed_by)
                
                if update_fields:
                    update_fields.append("analyzed_at = CURRENT_TIMESTAMP")
                    params.append(vulnerability_id)
                    
                    cursor.execute(
                        f"""UPDATE vulnerabilities 
                           SET {', '.join(update_fields)}
                           WHERE id = %s
                           RETURNING *""",
                        params
                    )
                    updated = cursor.fetchone()
                    conn.commit()
                    
                    return Vulnerability(**updated)
                else:
                    raise HTTPException(status_code=400, detail="No fields to update")
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/stats", response_model=List[VulnerabilityStats])
async def get_vulnerability_stats(
    limit: int = Query(100, ge=1, le=1000)
):
    """Get vulnerability statistics per repository."""
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """SELECT * FROM vulnerability_stats
                       ORDER BY total_vulnerabilities DESC, critical_count DESC
                       LIMIT %s""",
                    (limit,)
                )
                stats = cursor.fetchall()
                
                return [VulnerabilityStats(**stat) for stat in stats]
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/queue", response_model=List[ScanQueueItem])
async def get_scan_queue(
    status: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000)
):
    """Get scan queue items."""
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                where_clause = ""
                params = []
                
                if status:
                    where_clause = "WHERE status = %s"
                    params.append(status)
                
                params.append(limit)
                cursor.execute(
                    f"""SELECT * FROM scan_queue {where_clause}
                       ORDER BY priority DESC, queued_at ASC
                       LIMIT %s""",
                    params
                )
                items = cursor.fetchall()
                
                return [ScanQueueItem(**item) for item in items]
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv('API_PORT', '8000'))
    host = os.getenv('API_HOST', '0.0.0.0')
    
    uvicorn.run(app, host=host, port=port)
