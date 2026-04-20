from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from datetime import datetime


class AnalysisCreate(BaseModel):
    jira_url: str
    username: Optional[str] = None
    pat: str
    jql_filter: str
    num_clusters: int = 5


class ClusterResponse(BaseModel):
    id: UUID
    cluster_number: int
    label: str
    ticket_count: int
    keywords: Optional[List[str]] = None
    representative_tickets: Optional[list] = None
    percentage: Optional[float] = None

    class Config:
        from_attributes = True


class AnalysisResponse(BaseModel):
    id: UUID
    jira_url: str
    username: Optional[str] = None
    jql_filter: str
    num_clusters: int
    status: str
    error_message: Optional[str] = None
    total_tickets: int
    created_at: datetime
    completed_at: Optional[datetime] = None
    clusters: Optional[List[ClusterResponse]] = None

    class Config:
        from_attributes = True
