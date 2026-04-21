from pydantic import BaseModel, ConfigDict
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
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cluster_number: int
    label: str
    ticket_count: int
    keywords: Optional[List[str]] = None
    representative_tickets: Optional[list] = None
    percentage: Optional[float] = None


class AnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
