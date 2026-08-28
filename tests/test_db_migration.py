from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

import core.db as db_module
from core.models import DOC_LIFECYCLE_ACTIVE


def test_init_db_backfills_document_version_columns(tmp_path, monkeypatch):
    database_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{database_path}")

    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                hashed_password VARCHAR(255) NOT NULL,
                full_name VARCHAR(255),
                role VARCHAR(20) NOT NULL,
                created_at DATETIME NOT NULL
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE chat_messages (
                id INTEGER PRIMARY KEY,
                session_id VARCHAR(36) NOT NULL,
                role VARCHAR(20) NOT NULL,
                content TEXT NOT NULL,
                sources TEXT,
                created_at DATETIME NOT NULL
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY,
                filename VARCHAR(255) NOT NULL,
                original_filename VARCHAR(255) NOT NULL,
                path VARCHAR(500) NOT NULL,
                size_bytes INTEGER NOT NULL,
                status VARCHAR(20) NOT NULL,
                uploaded_by INTEGER,
                uploaded_at DATETIME NOT NULL
            )
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO users
                (id, email, hashed_password, full_name, role, created_at)
            VALUES
                (1, 'admin@example.com', 'hash', NULL, 'admin', CURRENT_TIMESTAMP)
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO documents
                (id, filename, original_filename, path, size_bytes, status, uploaded_by, uploaded_at)
            VALUES
                (3, 'stored.pdf', 'source.pdf', '/missing/source.pdf', 10, 'indexed', 1, CURRENT_TIMESTAMP)
            """
        )

    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(
        db_module,
        "SessionLocal",
        sessionmaker(autocommit=False, autoflush=False, bind=engine),
    )
    monkeypatch.setattr(db_module, "DATABASE_URL", f"sqlite:///{database_path}")

    db_module.init_db()

    document_columns = {column["name"] for column in inspect(engine).get_columns("documents")}
    assert {
        "content_hash",
        "document_code",
        "version_number",
        "lifecycle_status",
        "replaces_document_id",
    }.issubset(document_columns)

    with engine.connect() as connection:
        document = connection.execute(
            text(
                "SELECT document_code, version_number, lifecycle_status "
                "FROM documents WHERE id = 3"
            )
        ).one()
        full_name = connection.execute(text("SELECT full_name FROM users WHERE id = 1")).scalar_one()

    assert document.document_code == "DOC-000003"
    assert document.version_number == 1
    assert document.lifecycle_status == DOC_LIFECYCLE_ACTIVE
    assert full_name == "admin@example.com"

    engine.dispose()
