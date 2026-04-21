import logging
from datetime import datetime, UTC
from typing import Optional

from .jira import JiraService
from .embeddings import generate_embeddings
from .clustering import cluster_embeddings, extract_keywords, get_representative_tickets, generate_cluster_label

logger = logging.getLogger(__name__)


def _commit_analysis_progress(
    db,
    analysis,
    *,
    status: Optional[str] = None,
    status_detail: Optional[str] = None,
    progress_current: Optional[int] = None,
    progress_total: Optional[int] = None,
    progress_unit: Optional[str] = None,
    total_tickets: Optional[int] = None,
    error_message: Optional[str] = None,
    completed_at: Optional[datetime] = None,
) -> None:
    if status is not None:
        analysis.status = status
    if status_detail is not None:
        analysis.status_detail = status_detail
    if progress_current is not None:
        analysis.progress_current = progress_current
    if progress_total is not None:
        analysis.progress_total = progress_total
    if progress_unit is not None:
        analysis.progress_unit = progress_unit
    if total_tickets is not None:
        analysis.total_tickets = total_tickets
    if error_message is not None:
        analysis.error_message = error_message
    if completed_at is not None:
        analysis.completed_at = completed_at
    db.commit()


def run_analysis(
    analysis_id: str,
    jira_url: str,
    username: Optional[str],
    pat: str,
    jql_filter: str,
    num_clusters: int,
) -> None:
    """Full analysis pipeline executed in a background thread."""
    from ..database import SessionLocal
    from ..models import Analysis, Ticket, Cluster

    db = SessionLocal()
    try:
        analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
        if not analysis:
            logger.error("Analysis %s not found", analysis_id)
            return

        # ── 1. Mark as running ──────────────────────────────────────────────
        _commit_analysis_progress(
            db,
            analysis,
            status="running",
            status_detail="Fetching Jira tickets",
            progress_current=0,
            progress_total=0,
            progress_unit="tickets",
            total_tickets=0,
            error_message=None,
        )

        # ── 2. Fetch tickets from Jira ──────────────────────────────────────
        logger.info("[%s] Fetching Jira tickets …", analysis_id)
        jira = JiraService(jira_url, username, pat)
        raw_tickets = jira.fetch_tickets(jql_filter)

        if not raw_tickets:
            raise ValueError("No tickets matched the JQL filter.")

        logger.info("[%s] Fetched %d tickets.", analysis_id, len(raw_tickets))
        _commit_analysis_progress(
            db,
            analysis,
            status_detail="Generating embeddings",
            progress_current=0,
            progress_total=len(raw_tickets),
            progress_unit="tickets",
            total_tickets=len(raw_tickets),
        )

        # ── 3. Build embedding texts ─────────────────────────────────────────
        texts = []
        for t in raw_tickets:
            summary = t["summary"]
            desc = (t.get("description") or "")[:500]
            texts.append(f"{summary} {desc}".strip())

        # ── 4. Generate embeddings ───────────────────────────────────────────
        logger.info("[%s] Generating embeddings …", analysis_id)
        embeddings = generate_embeddings(
            texts,
            progress_callback=lambda completed, total: _commit_analysis_progress(
                db,
                analysis,
                status_detail="Generating embeddings",
                progress_current=completed,
                progress_total=total,
                progress_unit="tickets",
            ),
        )

        _commit_analysis_progress(
            db,
            analysis,
            status_detail="Saving embedded tickets",
            progress_current=0,
            progress_total=len(raw_tickets),
            progress_unit="tickets",
        )

        # ── 5. Persist tickets ───────────────────────────────────────────────
        logger.info("[%s] Saving tickets …", analysis_id)
        ticket_objects = []
        for i, t in enumerate(raw_tickets):
            obj = Ticket(
                analysis_id=analysis_id,
                jira_key=t["key"],
                summary=t["summary"],
                description=t.get("description", ""),
                issue_type=t.get("issue_type", ""),
                priority=t.get("priority", ""),
                ticket_status=t.get("status", ""),
                embedding=embeddings[i].tolist(),
            )
            ticket_objects.append(obj)
            db.add(obj)
        db.commit()

        _commit_analysis_progress(
            db,
            analysis,
            status_detail="Clustering tickets",
            progress_current=len(raw_tickets),
            progress_total=len(raw_tickets),
            progress_unit="tickets",
        )

        # ── 6. Cluster ───────────────────────────────────────────────────────
        logger.info("[%s] Clustering …", analysis_id)
        actual_clusters = min(num_clusters, len(raw_tickets))
        cluster_labels, cluster_centers = cluster_embeddings(embeddings, actual_clusters)

        for i, obj in enumerate(ticket_objects):
            obj.cluster_id = int(cluster_labels[i])
        db.commit()

        _commit_analysis_progress(
            db,
            analysis,
            status_detail="Labelling clusters",
            progress_current=0,
            progress_total=actual_clusters,
            progress_unit="clusters",
        )

        # ── 7. Build cluster summaries ───────────────────────────────────────
        logger.info("[%s] Building cluster summaries …", analysis_id)
        for cid in range(actual_clusters):
            mask = cluster_labels == cid
            cluster_tickets = [raw_tickets[i] for i in range(len(raw_tickets)) if mask[i]]
            if not cluster_tickets:
                continue

            cluster_texts = [
                f"{t['summary']} {(t.get('description') or '')[:200]}"
                for t in cluster_tickets
            ]
            keywords = extract_keywords(cluster_texts, top_n=5)
            # Ask the LLM for a descriptive label; fall back to keywords if unavailable.
            try:
                label = generate_cluster_label([t["summary"] for t in cluster_tickets])
            except Exception as llm_exc:
                logger.warning(
                    "[%s] LLM labelling failed for cluster %d, using keywords: %s",
                    analysis_id, cid, llm_exc,
                )
                label = " / ".join(keywords[:3]) if keywords else f"Cluster {cid + 1}"
            rep = get_representative_tickets(
                embeddings, cluster_labels, cluster_centers, raw_tickets, cid, top_n=3
            )

            db.add(
                Cluster(
                    analysis_id=analysis_id,
                    cluster_number=cid,
                    label=label,
                    ticket_count=len(cluster_tickets),
                    keywords=keywords,
                    representative_tickets=rep,
                )
            )
            analysis.progress_current = cid + 1
            db.commit()

        # ── 8. Finalize ──────────────────────────────────────────────────────
        _commit_analysis_progress(
            db,
            analysis,
            status="completed",
            status_detail="Analysis completed",
            progress_current=actual_clusters,
            progress_total=actual_clusters,
            progress_unit="clusters",
            total_tickets=len(raw_tickets),
            completed_at=datetime.now(UTC),
        )
        logger.info("[%s] Analysis completed.", analysis_id)

    except Exception as exc:
        logger.error("[%s] Analysis failed: %s", analysis_id, exc, exc_info=True)
        try:
            analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
            if analysis:
                _commit_analysis_progress(
                    db,
                    analysis,
                    status="failed",
                    status_detail="Analysis failed",
                    error_message=str(exc),
                )
        except Exception:
            pass
    finally:
        db.close()
