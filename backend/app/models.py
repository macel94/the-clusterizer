import uuid
from datetime import datetime

from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from pgvector.sqlalchemy import Vector

from .database import Base


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    jira_url = Column(String, nullable=False)
    username = Column(String)
    jql_filter = Column(Text, nullable=False)
    num_clusters = Column(Integer, nullable=False, default=5)
    status = Column(String, nullable=False, default="pending")
    error_message = Column(Text)
    total_tickets = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.utcnow())
    completed_at = Column(DateTime(timezone=True))


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id = Column(UUID(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"))
    jira_key = Column(String, nullable=False)
    summary = Column(Text, nullable=False)
    description = Column(Text)
    issue_type = Column(String)
    priority = Column(String)
    ticket_status = Column(String)
    cluster_id = Column(Integer)
    embedding = Column(Vector(384))


class Cluster(Base):
    __tablename__ = "clusters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id = Column(UUID(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"))
    cluster_number = Column(Integer, nullable=False)
    label = Column(String, nullable=False)
    ticket_count = Column(Integer, nullable=False)
    keywords = Column(ARRAY(String))
    representative_tickets = Column(JSONB)
