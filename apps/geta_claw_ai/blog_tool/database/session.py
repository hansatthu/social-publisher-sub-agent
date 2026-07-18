from __future__ import annotations
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select, text, event
from sqlalchemy.orm import Session, sessionmaker

from database.models import Article, Product, Base

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "seo_data.db"
DATABASE_URL = f"sqlite:///{DB_PATH.as_posix()}"

def get_engine():
    """Khởi tạo Engine với cấu hình tối ưu cho Multi-threading"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return create_engine(
        DATABASE_URL, 
        pool_pre_ping=True,
        # Bắt buộc cho đa luồng với SQLite (ThreadPoolExecutor)
        connect_args={
            "check_same_thread": False, 
            "timeout": 20.0  # Chờ tối đa 20s trước khi báo locked
        }
    )

Engine = get_engine()

# Bắt sự kiện mỗi khi có kết nối mới vào DB để thiết lập PRAGMA
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """
    [System Optimization] Bật WAL mode giúp giải quyết nút thắt cổ chai I/O.
    Tăng tốc độ Write và cho phép Non-blocking Reads.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA synchronous=NORMAL;")
    cursor.execute("PRAGMA cache_size=-64000;") # Dành 64MB RAM cho cache query
    cursor.execute("PRAGMA busy_timeout=20000;") # Cấu hình SQLite engine tự retry lock
    cursor.close()

SessionLocal = sessionmaker(bind=Engine, autoflush=False, autocommit=False, expire_on_commit=False)

def init_db() -> None:
    Base.metadata.create_all(bind=Engine)
    _ensure_article_columns()
    _ensure_product_columns()

def _ensure_article_columns() -> None:
    required_columns = {
        "language": "TEXT",
        "category_id": "INTEGER",
        "category_name": "TEXT",
        "seo_score": "INTEGER",
        "seo_notes": "TEXT",
        "long_tail_keywords": "TEXT",
        "target_sites": "TEXT",
        "source_images": "TEXT",
        "target_site": "TEXT",
    }
    try:
        with Engine.connect() as conn:
            result = conn.execute(text("PRAGMA table_info(articles)"))
            existing_columns = {row[1] for row in result}
            for column_name, column_type in required_columns.items():
                if column_name not in existing_columns:
                    print(f"[INIT_DB] Adding missing column: {column_name}")
                    conn.execute(text(f"ALTER TABLE articles ADD COLUMN {column_name} {column_type}"))
            conn.commit()
    except Exception as e:
        print(f"[INIT_DB] Error ensuring article columns: {e}")

def _ensure_product_columns() -> None:
    required_columns = {
        "name": "TEXT",
        "regular_price": "TEXT",
        "description": "TEXT",
        "short_description": "TEXT",
        "sku": "TEXT",
        "stock_quantity": "INTEGER",
        "categories": "TEXT",
        "images": "TEXT",
        "local_images": "TEXT",
        "wc_remote_id": "INTEGER",
        "product_url": "TEXT",
        "status": "TEXT",
        "error_log": "TEXT",
        "created_at": "DATETIME",
        "updated_at": "DATETIME",
    }

    with Engine.connect() as conn:
        product_table_info = conn.execute(text("PRAGMA table_info(products)"))
        existing_columns = {row[1] for row in product_table_info}
        if not existing_columns:
            return

        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                conn.execute(text(f"ALTER TABLE products ADD COLUMN {column_name} {column_type}"))
        conn.commit()

def get_session() -> Session:
    return SessionLocal()

def save_article(payload: dict[str, Any]) -> Article:
    with get_session() as db:
        article = Article(**payload)
        db.add(article)
        db.commit()
        db.refresh(article)
        return article

def list_articles(limit: int = 100) -> list[Article]:
    with get_session() as db:
        stmt = select(Article).order_by(Article.created_at.desc()).limit(limit)
        return list(db.scalars(stmt))