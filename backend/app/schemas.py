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


class RepresentativeTicketResponse(BaseModel):
    key: str
    summary: str


class ClusterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cluster_number: int
    label: str
    ticket_count: int
    keywords: Optional[List[str]] = None
    representative_tickets: Optional[List[RepresentativeTicketResponse]] = None
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


class TicketSearchItemResponse(BaseModel):
    jira_key: str
    summary: str
    description_preview: Optional[str] = None
    issue_type: Optional[str] = None
    priority: Optional[str] = None
    ticket_status: Optional[str] = None
    cluster_id: Optional[int] = None
    cluster_label: Optional[str] = None
    similarity_score: Optional[float] = None


class TicketSearchResponse(BaseModel):
    items: List[TicketSearchItemResponse]
    total: int
    limit: int
    offset: int
    query: Optional[str] = None


class TicketDetailResponse(TicketSearchItemResponse):
    analysis_id: UUID
    description: Optional[str] = None
    jira_issue_url: str
