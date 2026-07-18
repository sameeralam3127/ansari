"""Create the pgvector extension and all tables. Run manually in local dev.

Superseded by Alembic migrations once the schema needs to evolve (M1+).
"""

from sqlalchemy import text

from app.db import models  # noqa: F401  ensures models are registered on Base
from app.db.session import Base, engine


def init_db() -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
