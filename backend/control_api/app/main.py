from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

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

app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
def root_redirect():
    """Redirect root path to interactive Swagger documentation."""
    return RedirectResponse(url="/docs")


@app.get("/health/live", tags=["health"])
def liveness() -> dict[str, str]:
    """Confirm that the API process is running."""
    return {"status": "alive"}
