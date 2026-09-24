"""SQLAlchemy engine / session / Base + 啟動時的手刻 schema 遷移 [FD-029]"""
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
    # 已存圖 ↔ 生成資訊關聯（generation_history.saved_filename）
    _add_columns("generation_history", [
        ("saved_filename", "VARCHAR(200)"),
    ])
    # ALTER TABLE 不會補建 model 上宣告的 index（只有 create_all 會），舊庫需自行建。
    _add_index("ix_generation_history_saved_filename", "generation_history", "saved_filename")


def _add_index(index_name: str, table: str, column: str) -> None:
    """為既有資料表補建索引（create_all 只對新建的表生效）。表不存在時靜默略過。"""
    with engine.connect() as conn:
        if not list(conn.execute(text(f"PRAGMA table_info({table})"))):
            return
        conn.execute(text(
            f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} ({column})"
        ))
        conn.commit()


def _add_columns(table: str, columns: list[tuple[str, str]]) -> None:
    with engine.connect() as conn:
        existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
        for col_name, col_type in columns:
            if col_name not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"))
        conn.commit()
