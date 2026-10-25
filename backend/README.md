# Backend

Python services for Model Arena. FastAPI applications use Uvicorn (ASGI). Each service owns its HTTP or queue boundary and can be built and released independently.

- `control_api`: prediction routing, rollout controls, and audit API.
- `model_serving`: loads one pinned MLflow model version per container.
- `worker`: asynchronous shadow comparisons and delayed-label processing.
- `ml`: DVC training and evaluation pipeline.

All services are fully implemented and integrated with PostgreSQL, RabbitMQ, MLflow, and Prometheus metrics.
