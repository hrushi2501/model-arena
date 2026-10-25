from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

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
