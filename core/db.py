import os
from pathlib import Path

import logging

from sqlalchemy import create_engine, inspect, text, func
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(Path('data') / 'app.db').as_posix()}")

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
logger = logging.getLogger("database")


def init_db():
    """Create the sqlite data folder (if needed) and all ORM tables."""
    if DATABASE_URL.startswith("sqlite"):
        Path("data").mkdir(parents=True, exist_ok=True)
    from core import models  # noqa: F401 - ensure models are registered on Base
    Base.metadata.create_all(bind=engine)

    # create_all không bổ sung cột cho bảng đã tồn tại. Bổ sung metadata theo kiểu
    # backward-compatible để database hiện tại vẫn dùng được mà không cần xóa dữ liệu.
    columns = {column["name"] for column in inspect(engine).get_columns("chat_messages")}
    if "metadata" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE chat_messages ADD COLUMN metadata TEXT"))

    document_columns = {column["name"] for column in inspect(engine).get_columns("documents")}
    if "content_hash" not in document_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE documents ADD COLUMN content_hash VARCHAR(64)"))

    # Backfill/migrate existing databases before enforcing uniqueness.
    from core.file_hash import sha256_file
    from core.models import DOC_STATUS_INDEXED, Document

    document_columns = {column["name"] for column in inspect(engine).get_columns("documents")}
    lifecycle_column_added = "lifecycle_status" not in document_columns
    with engine.begin() as connection:
        if "document_code" not in document_columns:
            connection.execute(text("ALTER TABLE documents ADD COLUMN document_code VARCHAR(100)"))
        if "version_number" not in document_columns:
            connection.execute(
                text("ALTER TABLE documents ADD COLUMN version_number INTEGER NOT NULL DEFAULT 1")
            )
        if lifecycle_column_added:
            connection.execute(
                text(
                    "ALTER TABLE documents ADD COLUMN lifecycle_status "
                    "VARCHAR(20) NOT NULL DEFAULT 'draft'"
                )
            )
        if "replaces_document_id" not in document_columns:
            connection.execute(text("ALTER TABLE documents ADD COLUMN replaces_document_id INTEGER"))

        connection.execute(
            text(
                "UPDATE documents SET document_code = 'DOC-' || printf('%06d', id) "
                "WHERE document_code IS NULL OR trim(document_code) = ''"
            )
        )
        if lifecycle_column_added:
            connection.execute(
                text(
                    "UPDATE documents SET lifecycle_status = "
                    "CASE WHEN status = :indexed_status THEN 'active' ELSE 'draft' END"
                ),
                {"indexed_status": DOC_STATUS_INDEXED},
            )
        else:
            connection.execute(
                text(
                    "UPDATE documents SET lifecycle_status = "
                    "CASE WHEN status = :indexed_status THEN 'active' ELSE 'draft' END "
                    "WHERE lifecycle_status IS NULL "
                    "OR lifecycle_status NOT IN ('draft', 'active', 'superseded')"
                ),
                {"indexed_status": DOC_STATUS_INDEXED},
            )

        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_documents_code_version "
                "ON documents(document_code, version_number)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_documents_lifecycle_status "
                "ON documents(lifecycle_status)"
            )
        )
        connection.execute(
            text(
                "UPDATE users SET full_name = email "
                "WHERE full_name IS NULL OR trim(full_name) = ''"
            )
        )

    db = SessionLocal()
    try:
        for document in db.query(Document).filter(Document.content_hash.is_(None)).all():
            file_path = Path(document.path)
            if file_path.is_file():
                document.content_hash = sha256_file(file_path)
        db.commit()

        duplicate_hashes = (
            db.query(Document.content_hash)
            .filter(Document.content_hash.is_not(None))
            .group_by(Document.content_hash)
            .having(func.count(Document.id) > 1)
            .all()
        )
        if duplicate_hashes:
            logger.warning(
                "Skipped unique document hash index because duplicate records exist: %s",
                len(duplicate_hashes),
            )
        else:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS uq_documents_content_hash "
                        "ON documents(content_hash)"
                    )
                )
    finally:
        db.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
