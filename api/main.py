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
    
    Creates a scan queue entry. The queue worker will pick it up and create a job.
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
        
        # Queue worker will pick up this scan
        return ScanResponse(
            message="Scan queued successfully. The queue worker will process it shortly.",
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


@app.get("/api/v1/vulnerabilities/filters")
async def get_vulnerability_filters():
    """Get unique organizations and repositories for vulnerability filtering."""
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Get unique organizations with vulnerabilities
                cursor.execute(
                    """SELECT DISTINCT r.owner 
                       FROM repositories r
                       JOIN vulnerabilities v ON r.id = v.repository_id
                       ORDER BY r.owner"""
                )
                orgs = [row['owner'] for row in cursor.fetchall()]
                
                # Get unique repositories with vulnerabilities
                cursor.execute(
                    """SELECT DISTINCT r.owner, r.name 
                       FROM repositories r
                       JOIN vulnerabilities v ON r.id = v.repository_id
                       ORDER BY r.owner, r.name"""
                )
                repos = [{'owner': row['owner'], 'name': row['name']} for row in cursor.fetchall()]
        
        return {
            'organizations': orgs,
            'repositories': repos
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/vulnerabilities", response_model=PaginatedResponse)
async def list_vulnerabilities(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    repository_id: Optional[int] = None,
    org: Optional[str] = None,
    repo: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None
):
    """List vulnerabilities with optional filters, deduplicated across branches."""
    offset = (page - 1) * page_size
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Build query with join to repositories table
                where_clauses = []
                params = []
                
                if repository_id:
                    where_clauses.append("v.repository_id = %s")
                    params.append(repository_id)
                
                if org:
                    where_clauses.append("r.owner = %s")
                    params.append(org)
                
                if repo:
                    where_clauses.append("r.name = %s")
                    params.append(repo)
                
                if severity:
                    where_clauses.append("v.severity = %s")
                    params.append(severity)
                
                if status:
                    where_clauses.append("v.status = %s")
                    params.append(status)
                
                where_clause = ""
                if where_clauses:
                    where_clause = "WHERE " + " AND ".join(where_clauses)
                
                # Get total count of deduplicated vulnerabilities
                cursor.execute(
                    f"""SELECT COUNT(*) as count FROM (
                        SELECT DISTINCT v.repository_id, v.file_path, v.file_hash, v.vulnerability_type, v.line_number
                        FROM vulnerabilities v
                        JOIN repositories r ON v.repository_id = r.id
                        {where_clause}
                    ) AS deduped""",
                    params
                )
                total = cursor.fetchone()['count']
                
                # Get paginated results with repo info, deduplicated across branches
                # Group by file + vuln type, aggregate branch names
                params.extend([page_size, offset])
                cursor.execute(
                    f"""SELECT 
                        MIN(v.id) as id,
                        v.repository_id,
                        r.owner as repo_owner, 
                        r.name as repo_name,
                        r.url as repo_url,
                        v.file_path,
                        v.file_hash,
                        v.vulnerability_type,
                        v.severity,
                        v.title,
                        MIN(v.description) as description,
                        v.line_number,
                        MIN(v.code_snippet) as code_snippet,
                        MIN(v.recommendation) as recommendation,
                        MIN(v.cwe_id) as cwe_id,
                        MIN(v.cvss_score) as cvss_score,
                        MIN(v.detected_at) as detected_at,
                        MIN(v.status) as status,
                        MIN(v.manual_analysis) as manual_analysis,
                        MIN(v.analyzed_by) as analyzed_by,
                        MIN(v.analyzed_at) as analyzed_at,
                        ARRAY_AGG(DISTINCT b.name) FILTER (WHERE b.name IS NOT NULL) as branches,
                        COUNT(DISTINCT b.id) as branch_count
                       FROM vulnerabilities v
                       JOIN repositories r ON v.repository_id = r.id
                       LEFT JOIN branches b ON v.branch_id = b.id
                       {where_clause}
                       GROUP BY v.repository_id, r.owner, r.name, r.url, v.file_path, v.file_hash, 
                                v.vulnerability_type, v.severity, v.title, v.line_number
                       ORDER BY 
                         CASE v.severity 
                           WHEN 'critical' THEN 1
                           WHEN 'high' THEN 2
                           WHEN 'medium' THEN 3
                           WHEN 'low' THEN 4
                           ELSE 5
                         END,
                         MIN(v.detected_at) DESC
                       LIMIT %s OFFSET %s""",
                    params
                )
                vulnerabilities = cursor.fetchall()
                
                # Add GitHub URL to each vulnerability
                result = []
                for vuln in vulnerabilities:
                    vuln_dict = dict(vuln)
                    # Construct GitHub URL for the workflow file
                    # Use first branch or default to main
                    branches = vuln_dict.get('branches') or []
                    default_branch = branches[0] if branches else 'main'
                    if vuln_dict.get('repo_url'):
                        base_url = vuln_dict['repo_url'].replace('.git', '')
                        vuln_dict['github_url'] = f"{base_url}/blob/{default_branch}/{vuln_dict['file_path']}"
                        if vuln_dict.get('line_number'):
                            vuln_dict['github_url'] += f"#L{vuln_dict['line_number']}"
                    result.append(vuln_dict)
        
        return PaginatedResponse(
            total=total,
            page=page,
            page_size=page_size,
            data=result
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
                    where_clause = "WHERE sq.status = %s"
                    params.append(status)
                
                params.append(limit)
                cursor.execute(
                    f"""SELECT sq.*, 
                               CONCAT(r.owner, '/', r.name) as repository_name
                        FROM scan_queue sq
                        LEFT JOIN repositories r ON sq.repository_id = r.id
                        {where_clause}
                        ORDER BY sq.priority DESC, sq.queued_at ASC
                        LIMIT %s""",
                    params
                )
                items = cursor.fetchall()
                
                return [ScanQueueItem(**item) for item in items]
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Safe Files Endpoints

@app.get("/api/v1/safe-files")
async def list_safe_files():
    """List all files marked as safe."""
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """SELECT * FROM safe_files ORDER BY file_path, marked_at DESC"""
                )
                files = cursor.fetchall()
                return [dict(f) for f in files]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/safe-files")
async def mark_file_safe(
    file_path: str = Query(..., description="File path pattern to mark as safe"),
    file_hash: Optional[str] = Query(None, description="Optional specific file hash"),
    reason: Optional[str] = Query(None, description="Reason for marking safe"),
    marked_by: Optional[str] = Query(None, description="Who marked it safe")
):
    """Mark a file as safe globally (across all repos and branches)."""
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """INSERT INTO safe_files (file_path, file_hash, reason, marked_by)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (file_path, file_hash) DO UPDATE
                       SET reason = EXCLUDED.reason,
                           marked_by = EXCLUDED.marked_by,
                           marked_at = CURRENT_TIMESTAMP
                       RETURNING *""",
                    (file_path, file_hash, reason, marked_by)
                )
                result = cursor.fetchone()
                conn.commit()
                return dict(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/safe-files/{safe_file_id}")
async def remove_safe_file(safe_file_id: int):
    """Remove a file from the safe list."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM safe_files WHERE id = %s RETURNING id",
                    (safe_file_id,)
                )
                result = cursor.fetchone()
                if not result:
                    raise HTTPException(status_code=404, detail="Safe file entry not found")
                conn.commit()
                return {"message": "Safe file entry removed", "id": safe_file_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/vulnerabilities/{vulnerability_id}/mark-file-safe")
async def mark_vulnerability_file_safe(
    vulnerability_id: int,
    reason: Optional[str] = Query(None, description="Reason for marking safe"),
    marked_by: Optional[str] = Query(None, description="Who marked it safe")
):
    """Mark the file from a vulnerability as safe globally."""
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Get the vulnerability
                cursor.execute(
                    "SELECT file_path, file_hash FROM vulnerabilities WHERE id = %s",
                    (vulnerability_id,)
                )
                vuln = cursor.fetchone()
                if not vuln:
                    raise HTTPException(status_code=404, detail="Vulnerability not found")
                
                # Mark file as safe
                cursor.execute(
                    """INSERT INTO safe_files (file_path, file_hash, reason, marked_by)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (file_path, file_hash) DO UPDATE
                       SET reason = EXCLUDED.reason,
                           marked_by = EXCLUDED.marked_by,
                           marked_at = CURRENT_TIMESTAMP
                       RETURNING *""",
                    (vuln['file_path'], vuln['file_hash'], reason, marked_by)
                )
                safe_file = cursor.fetchone()
                
                # Mark all vulnerabilities with this file as ignored
                cursor.execute(
                    """UPDATE vulnerabilities 
                       SET status = 'ignored', 
                           manual_analysis = COALESCE(manual_analysis, '') || '\nAuto-ignored: File marked as safe globally',
                           analyzed_by = %s,
                           analyzed_at = CURRENT_TIMESTAMP
                       WHERE file_path = %s AND file_hash = %s AND status = 'open'""",
                    (marked_by, vuln['file_path'], vuln['file_hash'])
                )
                
                conn.commit()
                return {
                    "message": "File marked as safe globally",
                    "safe_file": dict(safe_file),
                    "file_path": vuln['file_path']
                }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv('API_PORT', '8000'))
    host = os.getenv('API_HOST', '0.0.0.0')
    
    uvicorn.run(app, host=host, port=port)
