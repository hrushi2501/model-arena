FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /build
RUN pip install --no-cache-dir --prefix=/install "mlflow>=3,<4" "psycopg[binary]>=3.2,<4"

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
COPY --from=builder /install /usr/local
RUN useradd --system --uid 10001 --create-home mlflow \
    && mkdir -p /mlartifacts \
    && chown -R 10001:10001 /mlartifacts
USER 10001:10001
WORKDIR /mlartifacts
EXPOSE 5000
ENTRYPOINT ["mlflow", "server"]
