from contextlib import asynccontextmanager
from functools import partial
from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy.orm import Session

from app.api.v1.routes import router
from app.db.migrate import initialize_schema
from app.db.session import SessionLocal, engine, get_db
from app.schemas.schemas import FeedbackRequest
from app.services.background import background
from app.services.decision_engine import get_or_create_active_rollout, monitor_once
from app.services.feedback import record_feedback
from app.services.outbox import dispatching
from app.settings import validate_model_versions


@asynccontextmanager
async def lifespan(app):
    validate_model_versions()
    initialize_schema(engine)
    with SessionLocal() as db:
        get_or_create_active_rollout(db)
    async with (
        dispatching(SessionLocal),
        background(partial(monitor_once, SessionLocal), "release-policy", 5),
    ):
        yield


app = FastAPI(title="Model Arena Control API", version="0.2.0", lifespan=lifespan)
app.include_router(router, prefix="/api/v1")


@app.post("/api/v1/feedback")
def submit_feedback(request: FeedbackRequest, db: Annotated[Session, Depends(get_db)]):
    return record_feedback(request, db)


@app.get("/health/live")
def liveness():
    return {"status": "alive"}
