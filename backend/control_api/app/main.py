from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

from app.api.v1.routes import router as api_v1_router
from app.db.session import Base, SessionLocal, engine
from app.api.v1.routes import get_or_create_active_rollout


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

# --- Prometheus Metrics ---
REQUESTS_TOTAL = Counter(
    "model_arena_requests_total",
    "Total count of prediction requests routed through the arena",
    ["role", "status"],
)

REQUEST_DURATION_SECONDS = Histogram(
    "model_arena_request_duration_seconds",
    "Prediction request duration in seconds",
    buckets=[0.01, 0.025, 0.05, 0.075, 0.1, 0.2, 0.5, 1.0, 2.0],
)

CANARY_PERCENTAGE = Gauge(
    "model_arena_canary_percentage",
    "Current active canary traffic split percentage (0.0 to 1.0)",
)
CANARY_PERCENTAGE.set(0.0)

ROLLBACK_EVENTS_TOTAL = Counter(
    "model_arena_rollback_events_total",
    "Total count of automated and manual rollback events triggered",
)

app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/health/live", tags=["health"])
def liveness() -> dict[str, str]:
    """Confirm that the API process is running."""
    return {"status": "alive"}


@app.get("/metrics", tags=["observability"])
def metrics() -> Response:
    """Prometheus scrape endpoint for model arena operational metrics."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
