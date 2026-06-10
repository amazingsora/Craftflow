from sqlalchemy import create_engine, text
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
    _migrate()


def _migrate() -> None:
    """Add new columns to existing SQLite tables (SQLite has no ALTER COLUMN IF NOT EXISTS)."""
    _add_columns("characters", [
        ("ai_summary", "TEXT"),
        ("portrait_path", "VARCHAR(500)"),
        ("color", "VARCHAR(7)"),
        ("concept_images", "TEXT"),
        ("ai_generated_images", "TEXT"),
        ("age", "INTEGER"),
        ("birthday", "VARCHAR(30)"),
        ("ai_prompt", "TEXT"),
        ("gender", "VARCHAR(10)"),
        ("tab_names", "TEXT"),
        ("variants", "TEXT"),
    ])
    _add_columns("projects", [
        ("genre", "VARCHAR(50)"),
        ("status", "VARCHAR(20)"),
        ("art_style_id", "INTEGER"),
    ])
    _add_columns("characters", [
        ("art_style_id", "INTEGER"),
        ("height", "INTEGER"),
        ("outfit", "TEXT"),
        ("lora_name", "VARCHAR(200)"),
        ("lora_weight", "FLOAT"),
    ])
    _add_columns("chapters", [
        ("volume_id", "INTEGER"),
    ])


def _add_columns(table: str, columns: list[tuple[str, str]]) -> None:
    with engine.connect() as conn:
        existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
        for col_name, col_type in columns:
            if col_name not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"))
        conn.commit()
