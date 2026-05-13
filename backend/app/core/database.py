from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session
from app.core.config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)


class Base(DeclarativeBase):
    pass


def get_db():
    with Session(engine) as session:
        yield session


def init_db() -> None:
    import app.models  # noqa: F401 — registers all ORM models with Base
    Base.metadata.create_all(bind=engine)
