"""Persist comparisons using the schema owned and created by the control API."""

import os
from functools import cached_property

from sqlalchemy import URL, MetaData, create_engine, select, text


class ComparisonStore:
    def __init__(self, engine=None):
        if engine is None:
            database_url = os.getenv("DATABASE_URL")
            if not database_url:
                # Support the current Compose contract without building a DSN
                # by string interpolation (passwords may contain URL characters).
                database_url = URL.create(
                    "postgresql+psycopg",
                    username=os.getenv("POSTGRES_USER", "model_arena"),
                    password=os.environ["POSTGRES_PASSWORD"],
                    host=os.getenv("POSTGRES_HOST", "postgres"),
                    port=int(os.getenv("POSTGRES_PORT", "5432")),
                    database=os.getenv("POSTGRES_DB", "model_arena"),
                )
            engine = create_engine(database_url, pool_pre_ping=True)
        self.engine = engine

    @cached_property
    def tables(self):
        metadata = MetaData()
        metadata.reflect(
            bind=self.engine,
            only=["predictions", "feedback", "model_comparisons", "accuracy_counters"],
        )
        return metadata.tables

    def save(self, task, candidate_pred: int) -> None:
        predictions = self.tables["predictions"]
        comparisons = self.tables["model_comparisons"]
        feedback = self.tables["feedback"]
        with self.engine.begin() as conn:
            # Same row lock as feedback: exactly one side accounts for the late
            # candidate result, regardless of which transaction arrives first.
            prediction = (
                conn.execute(
                    select(predictions).where(predictions.c.id == task.request_id).with_for_update()
                )
                .mappings()
                .first()
            )
            if prediction is None:
                raise ValueError("Unknown prediction")
            if (
                prediction["selected_role"] != "champion"
                or prediction["prediction"] != task.champion_pred
            ):
                raise ValueError("Shadow task disagrees with persisted champion prediction")
            existing = conn.execute(
                select(comparisons).where(comparisons.c.prediction_id == task.request_id)
            ).first()
            if existing:
                return
            conn.execute(
                comparisons.insert().values(
                    prediction_id=task.request_id,
                    champion_pred=task.champion_pred,
                    candidate_pred=candidate_pred,
                    is_match=(candidate_pred == task.champion_pred),
                )
            )
            label = conn.execute(
                select(feedback.c.ground_truth_label)
                .where(feedback.c.prediction_id == task.request_id)
                .order_by(feedback.c.id)
                .limit(1)
            ).scalar_one_or_none()
            if label is not None:
                conn.execute(
                    text("""
                        INSERT INTO accuracy_counters (model_role, correct_count, total_count)
                        VALUES ('candidate', :correct, 1)
                        ON CONFLICT (model_role) DO UPDATE SET
                            correct_count = accuracy_counters.correct_count + :correct,
                            total_count = accuracy_counters.total_count + 1
                    """),
                    {"correct": int(candidate_pred == label)},
                )
