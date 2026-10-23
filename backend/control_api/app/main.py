from fastapi import FastAPI

app = FastAPI(
    title="Model Arena Control API",
    description="Prediction routing and safe model release controls.",
    version="0.1.0",
)


@app.get("/health/live", tags=["health"])
def liveness() -> dict[str, str]:
    """Confirm that the API process is running."""
    return {"status": "alive"}
