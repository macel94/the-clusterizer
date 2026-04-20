from typing import List
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Analysis, Cluster
from ..schemas import AnalysisCreate, AnalysisResponse, ClusterResponse
from ..services.analysis import run_analysis

router = APIRouter()


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
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found.")

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


@router.delete("/{analysis_id}", status_code=204)
def delete_analysis(analysis_id: UUID, db: Session = Depends(get_db)):
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found.")
    db.delete(analysis)
    db.commit()
