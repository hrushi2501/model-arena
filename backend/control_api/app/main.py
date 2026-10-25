from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.api.v1.routes import get_or_create_active_rollout
from app.api.v1.routes import router as api_v1_router
from app.db.session import Base, SessionLocal, engine, get_db
from app.schemas.schemas import FeedbackRequest
from app.services.feedback import record_feedback
from app.services.outbox import dispatching


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Auto-create tables if they don't exist
    Base.metadata.create_all(bind=engine)
    # Ensure default active rollout is seeded
    db = SessionLocal()
    try:
        get_or_create_active_rollout(db)
    finally:
        db.close()
    async with dispatching(SessionLocal):
        yield


app = FastAPI(
    title="Model Arena Control API",
    description="Prediction routing gateway and safe model release controls.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware for frontend dashboard access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.metrics import (
    CONTENT_TYPE_LATEST,
    CANARY_PERCENTAGE,
    REQUEST_DURATION_SECONDS,
    REQUESTS_TOTAL,
    ROLLBACK_EVENTS_TOTAL,
    generate_latest,
)

app.include_router(api_v1_router, prefix="/api/v1")


@app.post("/api/v1/feedback")
def submit_feedback(request: FeedbackRequest, db: Session = Depends(get_db)):
    """Attach a delayed label once and update both available model accuracies."""
    return record_feedback(request, db)


@app.get("/health/live", tags=["health"])
def liveness() -> dict[str, str]:
    """Confirm that the API process is running."""
    return {"status": "alive"}


@app.get("/metrics", tags=["observability"])
def metrics() -> Response:
    """Prometheus scrape endpoint for model arena operational metrics."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
