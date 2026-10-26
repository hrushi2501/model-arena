"""Idempotent, additive startup upgrade for honest failed predictions."""

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Integer, inspect

from app.db.session import Base


def initialize_schema(engine):
    Base.metadata.create_all(engine)
    prediction = next(
        c for c in inspect(engine).get_columns("predictions") if c["name"] == "prediction"
    )
    if not prediction["nullable"]:
        with engine.begin() as connection:
            operations = Operations(MigrationContext.configure(connection))
            with operations.batch_alter_table("predictions") as batch:
                batch.alter_column("prediction", existing_type=Integer(), nullable=True)
