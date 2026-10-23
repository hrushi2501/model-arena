from fastapi import FastAPI

app = FastAPI(
    title="Model Arena Model Server",
    description="Loads and serves one explicitly configured model version.",
    version="0.1.0",
)


@app.get("/health/live", tags=["health"])
def liveness() -> dict[str, str]:
    """Confirm that the model-server process is running."""
    return {"status": "alive"}
