from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Analysis, Cluster, Ticket
from ..schemas import (
    AnalysisCreate,
    AnalysisResponse,
    ClusterResponse,
    TicketDetailResponse,
    TicketSearchItemResponse,
    TicketSearchResponse,
)
from ..services.analysis import run_analysis
from ..services.embeddings import generate_embeddings

router = APIRouter()


def _get_analysis_or_404(db: Session, analysis_id: UUID) -> Analysis:
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found.")
    return analysis


def _ticket_cluster_join_condition():
    return and_(
        Cluster.analysis_id == Ticket.analysis_id,
        Cluster.cluster_number == Ticket.cluster_id,
    )


def _preview_description(text: Optional[str], limit: int = 180) -> Optional[str]:
    if not text:
        return None
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _build_ticket_search_item(
    ticket: Ticket,
    cluster_label: Optional[str],
    similarity_score: Optional[float] = None,
) -> TicketSearchItemResponse:
    return TicketSearchItemResponse(
        jira_key=ticket.jira_key,
        summary=ticket.summary,
        description_preview=_preview_description(ticket.description),
        issue_type=ticket.issue_type,
        priority=ticket.priority,
        ticket_status=ticket.ticket_status,
        cluster_id=ticket.cluster_id,
        cluster_label=cluster_label,
        similarity_score=similarity_score,
    )


def _build_ticket_detail(
    ticket: Ticket,
    jira_url: str,
    cluster_label: Optional[str],
) -> TicketDetailResponse:
    return TicketDetailResponse(
        analysis_id=ticket.analysis_id,
        jira_key=ticket.jira_key,
        summary=ticket.summary,
        description_preview=_preview_description(ticket.description),
        description=ticket.description,
        issue_type=ticket.issue_type,
        priority=ticket.priority,
        ticket_status=ticket.ticket_status,
        cluster_id=ticket.cluster_id,
        cluster_label=cluster_label,
        jira_issue_url=f"{jira_url.rstrip('/')}/browse/{ticket.jira_key}",
    )


@router.post("/", response_model=AnalysisResponse, status_code=201)
def create_analysis(
    data: AnalysisCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    if data.num_clusters < 2 or data.num_clusters > 20:
        raise HTTPException(status_code=422, detail="num_clusters must be between 2 and 20.")

    analysis = Analysis(
        jira_url=data.jira_url,
        username=data.username,
        jql_filter=data.jql_filter,
        num_clusters=data.num_clusters,
        status="pending",
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    # PAT is passed to the background task and never persisted.
    background_tasks.add_task(
        run_analysis,
        str(analysis.id),
        data.jira_url,
        data.username,
        data.pat,
        data.jql_filter,
        data.num_clusters,
    )

    return analysis


@router.get("/", response_model=List[AnalysisResponse])
def list_analyses(db: Session = Depends(get_db)):
    return db.query(Analysis).order_by(Analysis.created_at.desc()).all()


@router.get("/{analysis_id}", response_model=AnalysisResponse)
def get_analysis(analysis_id: UUID, db: Session = Depends(get_db)):
    analysis = _get_analysis_or_404(db, analysis_id)

    clusters = (
        db.query(Cluster)
        .filter(Cluster.analysis_id == analysis_id)
        .order_by(Cluster.ticket_count.desc())
        .all()
    )

    total = analysis.total_tickets or 1
    cluster_responses = []
    for c in clusters:
        cr = ClusterResponse.model_validate(c)
        cr.percentage = round(c.ticket_count / total * 100, 1)
        cluster_responses.append(cr)

    response = AnalysisResponse.model_validate(analysis)
    response.clusters = cluster_responses
    return response


@router.get("/{analysis_id}/tickets", response_model=TicketSearchResponse)
def search_analysis_tickets(
    analysis_id: UUID,
    query: Optional[str] = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    _get_analysis_or_404(db, analysis_id)

    total = db.query(Ticket).filter(Ticket.analysis_id == analysis_id).count()
    search_text = (query or "").strip()
    cluster_label = Cluster.label.label("cluster_label")
    join_condition = _ticket_cluster_join_condition()

    if search_text:
        query_embedding = generate_embeddings([search_text])[0].tolist()
        distance = Ticket.embedding.cosine_distance(query_embedding).label("distance")
        rows = (
            db.query(Ticket, cluster_label, distance)
            .outerjoin(Cluster, join_condition)
            .filter(Ticket.analysis_id == analysis_id)
            .order_by(distance.asc(), Ticket.jira_key.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        items = [
            _build_ticket_search_item(
                ticket,
                label,
                similarity_score=max(0.0, round(1 - float(ticket_distance), 4)),
            )
            for ticket, label, ticket_distance in rows
        ]
    else:
        rows = (
            db.query(Ticket, cluster_label)
            .outerjoin(Cluster, join_condition)
            .filter(Ticket.analysis_id == analysis_id)
            .order_by(func.coalesce(Ticket.cluster_id, 2147483647), Ticket.jira_key.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        items = [_build_ticket_search_item(ticket, label) for ticket, label in rows]

    return TicketSearchResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        query=search_text or None,
    )


@router.get("/{analysis_id}/tickets/by-key/{jira_key}", response_model=TicketDetailResponse)
def get_analysis_ticket(
    analysis_id: UUID,
    jira_key: str,
    db: Session = Depends(get_db),
):
    analysis = _get_analysis_or_404(db, analysis_id)
    row = (
        db.query(Ticket, Cluster.label.label("cluster_label"))
        .outerjoin(Cluster, _ticket_cluster_join_condition())
        .filter(Ticket.analysis_id == analysis_id, Ticket.jira_key == jira_key)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    ticket, cluster_label = row
    return _build_ticket_detail(ticket, analysis.jira_url, cluster_label)


@router.delete("/{analysis_id}", status_code=204)
def delete_analysis(analysis_id: UUID, db: Session = Depends(get_db)):
    analysis = _get_analysis_or_404(db, analysis_id)
    db.delete(analysis)
    db.commit()
