"""Persist one comparison per prediction; PostgreSQL owns duplicate exclusion."""

import os

from sqlalchemy import URL, create_engine, make_url, text

COMPARISON_EXISTS = text("SELECT 1 FROM model_comparisons WHERE prediction_id = :request_id")


class ComparisonStore:
    def __init__(self, engine=None):
        if engine is None:
            url = make_url(
                os.getenv("DATABASE_URL")
                or URL.create(
                    "postgresql+psycopg",
                    username=os.getenv("POSTGRES_USER", "model_arena"),
                    password=os.environ["POSTGRES_PASSWORD"],
                    host=os.getenv("POSTGRES_HOST", "postgres"),
                    port=int(os.getenv("POSTGRES_PORT", "5432")),
                    database=os.getenv("POSTGRES_DB", "model_arena"),
                )
            )
            if url.get_backend_name() != "postgresql":
                raise ValueError("Worker requires a shared PostgreSQL database")
            # Preserve existing options such as an isolated test search_path.
            url = url.update_query_dict(
                {
                    "options": url.query.get("options", "")
                    + " -c statement_timeout=5000 -c lock_timeout=5000"
                }
            )
            engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
        self.engine = engine

    def check_schema(self):
        with self.engine.connect() as conn:
            conn.execute(
                text("""
                SELECT p.id, c.prediction_id FROM predictions p
                LEFT JOIN model_comparisons c ON c.prediction_id = p.id LIMIT 0
            """)
            )

    def completed(self, prediction_id: str) -> bool:
        with self.engine.connect() as conn:
            return (
                conn.execute(COMPARISON_EXISTS, {"request_id": prediction_id}).first() is not None
            )

    def save(self, task, candidate_pred: int) -> None:
        params = {
            "request_id": task.request_id,
            "champion": task.champion_pred,
            "candidate": candidate_pred,
        }
        with self.engine.begin() as conn:
            inserted = conn.execute(
                text("""
                INSERT INTO model_comparisons
                    (prediction_id, champion_pred, candidate_pred, is_match, timestamp)
                SELECT id, prediction, :candidate, prediction = :candidate, CURRENT_TIMESTAMP
                FROM predictions
                WHERE id = :request_id AND selected_role = 'champion' AND prediction = :champion
                  AND status_code = 200
                ON CONFLICT (prediction_id) DO NOTHING
                RETURNING prediction_id
            """),
                params,
            ).scalar_one_or_none()
            if inserted is None and conn.execute(COMPARISON_EXISTS, params).first() is None:
                raise ValueError("Unknown or mismatched champion prediction")
