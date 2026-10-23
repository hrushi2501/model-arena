# Database

PostgreSQL stores application state and audit records. Use separate databases (`model_arena` and `mlflow`) on the local PostgreSQL instance so the application schema and MLflow schema have separate ownership.

Put application schema migrations under `migrations/` and repeatable demo data under `seeds/`. Never store credentials in migrations or seed files.
