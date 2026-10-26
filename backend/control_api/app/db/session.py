import os

from sqlalchemy import URL, create_engine, make_url
from sqlalchemy.orm import declarative_base, sessionmaker

url = make_url(
    os.getenv("DATABASE_URL")
    or (
        URL.create(
            "postgresql+psycopg",
            username=os.getenv("POSTGRES_USER", "model_arena"),
            password=os.environ["POSTGRES_PASSWORD"],
            host=os.getenv("POSTGRES_HOST", "postgres"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            database=os.getenv("POSTGRES_DB", "model_arena"),
        )
        if os.getenv("POSTGRES_PASSWORD")
        else "sqlite:///./model_arena.db"
    )
)
is_sqlite = url.get_backend_name() == "sqlite"
connect_args = {"check_same_thread": False} if is_sqlite else {"connect_timeout": 5}
engine = create_engine(url, connect_args=connect_args, pool_pre_ping=not is_sqlite)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    with SessionLocal() as db:
        yield db
