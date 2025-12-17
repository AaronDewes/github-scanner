"""
Pydantic models for the API
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, HttpUrl, Field


class RepositoryBase(BaseModel):
    url: str
    owner: str
    name: str
    organization: Optional[str] = None
    has_actions: bool = False


class RepositoryCreate(RepositoryBase):
    pass


class Repository(RepositoryBase):
    id: int
    scan_status: str
    scan_error: Optional[str] = None
    first_scanned_at: Optional[datetime] = None
    last_scanned_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VulnerabilityBase(BaseModel):
    file_path: str
    file_hash: str
    vulnerability_type: str
    severity: str
    title: str
    description: Optional[str] = None
    line_number: Optional[int] = None
    code_snippet: Optional[str] = None
    recommendation: Optional[str] = None
    cwe_id: Optional[str] = None
    cvss_score: Optional[float] = None


class VulnerabilityCreate(VulnerabilityBase):
    repository_id: int
    branch_id: Optional[int] = None


class Vulnerability(VulnerabilityBase):
    id: int
    repository_id: int
    branch_id: Optional[int] = None
    status: str
    manual_analysis: Optional[str] = None
    analyzed_by: Optional[str] = None
    analyzed_at: Optional[datetime] = None
    detected_at: datetime
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VulnerabilityUpdate(BaseModel):
    status: Optional[str] = None
    manual_analysis: Optional[str] = None
    analyzed_by: Optional[str] = None


class ScanRequest(BaseModel):
    repo_url: str = Field(..., description="GitHub repository URL to scan")
    priority: int = Field(default=0, description="Scan priority (higher = sooner)")


class ScanResponse(BaseModel):
    message: str
    repository_id: int
    scan_queue_id: int


class ScanQueueItem(BaseModel):
    id: int
    repository_id: int
    repository_name: Optional[str] = None
    priority: int
    status: str
    attempts: int
    max_attempts: int
    error_message: Optional[str] = None
    job_name: Optional[str] = None
    queued_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class VulnerabilityStats(BaseModel):
    repository_id: int
    owner: str
    name: str
    total_vulnerabilities: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    open_count: int
    confirmed_count: int
    last_vulnerability_detected: Optional[datetime] = None


class PaginatedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    data: List[dict]


class HealthCheck(BaseModel):
    status: str
    database: str
    timestamp: datetime
