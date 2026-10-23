# Backend

Python services for Model Arena. FastAPI applications use Uvicorn (ASGI). Each service owns its HTTP or queue boundary and can be built and released independently.

- `control_api`: prediction routing, rollout controls, and audit API.
- `model_serving`: loads one pinned MLflow model version per container.
- `worker`: asynchronous shadow comparisons and delayed-label processing.
- `ml`: DVC training and evaluation pipeline.

The service code currently contains health-check starters only. Prediction, persistence, queue processing, and rollout decisions remain to be implemented.
