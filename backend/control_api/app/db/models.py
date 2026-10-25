import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from sqlalchemy.sql import func
from app.db.session import Base


class Rollout(Base):
    __tablename__ = "rollouts"

    id = Column(Integer, primary_key=True, index=True)
    champion_version = Column(String(255), nullable=False, default="models:/wine-classifier/1")
    candidate_version = Column(String(255), nullable=False, default="models:/wine-classifier/2")
    state = Column(String(50), nullable=False, default="READY")  # READY, SHADOW, CANARY, PROMOTED, ROLLED_BACK
    canary_percentage = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    client_id = Column(String(255), nullable=True, index=True)
    selected_version = Column(String(255), nullable=False)
    selected_role = Column(String(50), nullable=False)  # champion, candidate
    prediction = Column(Integer, nullable=False)
    probabilities_json = Column(Text, nullable=True)
    latency_ms = Column(Float, nullable=False)
    status_code = Column(Integer, default=200)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    prediction_id = Column(String(64), nullable=False, index=True)
    ground_truth_label = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    event_type = Column(String(50), nullable=False)  # STAGE_CHANGE, DECISION, ROLLBACK, PROMOTE
    reason = Column(String(500), nullable=False)
    details_json = Column(Text, nullable=True)
