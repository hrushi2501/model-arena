# Local infrastructure

Service configuration for Nginx, MLflow, Prometheus, and Grafana lives here. PostgreSQL and RabbitMQ are declared in the root `compose.yaml`.

The root Compose file binds local admin dashboards to loopback during development and keeps database and RabbitMQ ports private to the Compose network. The current Prometheus config is a starter and will report scrape errors until `/metrics` endpoints are implemented.
