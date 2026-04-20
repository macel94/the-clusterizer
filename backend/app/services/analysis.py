import logging
from datetime import datetime
from typing import Optional

from .jira import JiraService
from .embeddings import generate_embeddings
from .clustering import cluster_embeddings, extract_keywords, get_representative_tickets

logger = logging.getLogger(__name__)


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
        analysis.status = "running"
        db.commit()

        # ── 2. Fetch tickets from Jira ──────────────────────────────────────
        logger.info("[%s] Fetching Jira tickets …", analysis_id)
        jira = JiraService(jira_url, username, pat)
        raw_tickets = jira.fetch_tickets(jql_filter)

        if not raw_tickets:
            raise ValueError("No tickets matched the JQL filter.")

        logger.info("[%s] Fetched %d tickets.", analysis_id, len(raw_tickets))

        # ── 3. Build embedding texts ─────────────────────────────────────────
        texts = []
        for t in raw_tickets:
            summary = t["summary"]
            desc = (t.get("description") or "")[:500]
            texts.append(f"{summary} {desc}".strip())

        # ── 4. Generate embeddings ───────────────────────────────────────────
        logger.info("[%s] Generating embeddings …", analysis_id)
        embeddings = generate_embeddings(texts)

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

        # ── 6. Cluster ───────────────────────────────────────────────────────
        logger.info("[%s] Clustering …", analysis_id)
        actual_clusters = min(num_clusters, len(raw_tickets))
        cluster_labels, cluster_centers = cluster_embeddings(embeddings, actual_clusters)

        for i, obj in enumerate(ticket_objects):
            obj.cluster_id = int(cluster_labels[i])
        db.commit()

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

        # ── 8. Finalize ──────────────────────────────────────────────────────
        analysis.status = "completed"
        analysis.total_tickets = len(raw_tickets)
        analysis.completed_at = datetime.utcnow()
        db.commit()
        logger.info("[%s] Analysis completed.", analysis_id)

    except Exception as exc:
        logger.error("[%s] Analysis failed: %s", analysis_id, exc, exc_info=True)
        try:
            analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
            if analysis:
                analysis.status = "failed"
                analysis.error_message = str(exc)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
