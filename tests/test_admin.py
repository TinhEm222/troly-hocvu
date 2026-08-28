from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import api.routes.admin as admin_module
from api.routes.admin import router as admin_router
from api.routes.auth import router as auth_router
from core.db import Base, get_db
from core.models import ROLE_ADMIN, ROLE_STUDENT, User
from core.security import hash_password


@pytest.fixture()
def admin_client(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    db.add_all(
        [
            User(
                email="admin@example.com",
                hashed_password=hash_password("admin-password"),
                full_name="Test Admin",
                role=ROLE_ADMIN,
            ),
            User(
                email="student@example.com",
                hashed_password=hash_password("student-password"),
                full_name="Test Student",
                role=ROLE_STUDENT,
            ),
        ]
    )
    db.commit()
    db.close()

    raw_data_dir = tmp_path / "raw"
    monkeypatch.setattr(admin_module, "RAW_DATA_DIR", raw_data_dir)
    monkeypatch.setattr(admin_module, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(
        admin_module,
        "_reindex_state",
        {"running": False, "last_started_at": None, "last_finished_at": None, "last_error": None},
    )

    app = FastAPI()
    app.include_router(auth_router, prefix="/api/auth")
    app.include_router(admin_router, prefix="/api/admin")

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client, raw_data_dir

    engine.dispose()


def login(client: TestClient, email: str, password: str) -> str:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_admin_login_returns_admin_role_and_student_is_forbidden(admin_client):
    client, _ = admin_client

    admin_response = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-password"},
    )
    assert admin_response.status_code == 200
    assert admin_response.json()["user"]["role"] == ROLE_ADMIN

    student_token = login(client, "student@example.com", "student-password")
    response = client.get("/api/admin/stats", headers=auth_headers(student_token))
    assert response.status_code == 403


def test_admin_dashboard_returns_counts(admin_client):
    client, _ = admin_client
    token = login(client, "admin@example.com", "admin-password")

    response = client.get("/api/admin/stats", headers=auth_headers(token))

    assert response.status_code == 200
    assert response.json()["total_users"] == 2
    assert response.json()["total_admins"] == 1
    assert response.json()["total_students"] == 1
    assert response.json()["total_documents"] == 0


def test_admin_can_upload_list_delete_pdf_and_reject_other_extensions(admin_client):
    client, raw_data_dir = admin_client
    token = login(client, "admin@example.com", "admin-password")
    headers = auth_headers(token)

    invalid = client.post(
        "/api/admin/documents/upload",
        headers=headers,
        files={"file": ("notes.txt", b"not a pdf", "text/plain")},
    )
    assert invalid.status_code == 400

    uploaded = client.post(
        "/api/admin/documents/upload",
        headers=headers,
        files={"file": ("guide.pdf", b"%PDF-1.7 test", "application/pdf")},
    )
    assert uploaded.status_code == 201
    document = uploaded.json()
    assert document["original_filename"] == "guide.pdf"
    assert document["status"] == "pending"
    stored_files = list(raw_data_dir.iterdir())
    assert len(stored_files) == 1

    dashboard_before_reindex = client.get("/api/admin/stats", headers=headers)
    assert dashboard_before_reindex.status_code == 200
    assert dashboard_before_reindex.json()["total_documents"] == 0

    listed = client.get("/api/admin/documents", headers=headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [document["id"]]

    deleted = client.delete(f"/api/admin/documents/{document['id']}", headers=headers)
    assert deleted.status_code == 200
    assert list(raw_data_dir.iterdir()) == []
    assert client.get("/api/admin/documents", headers=headers).json() == []


def test_admin_rejects_duplicate_pdf_content(admin_client):
    client, raw_data_dir = admin_client
    token = login(client, "admin@example.com", "admin-password")
    headers = auth_headers(token)
    pdf_bytes = b"%PDF-1.7 same content"

    first = client.post(
        "/api/admin/documents/upload",
        headers=headers,
        files={"file": ("first.pdf", pdf_bytes, "application/pdf")},
    )
    duplicate = client.post(
        "/api/admin/documents/upload",
        headers=headers,
        files={"file": ("renamed.pdf", pdf_bytes, "application/pdf")},
    )

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert "đã tồn tại" in duplicate.json()["detail"].lower()
    assert len(list(raw_data_dir.iterdir())) == 1


def test_document_update_keeps_old_version_active_until_reindex_succeeds(
    admin_client, monkeypatch
):
    client, _ = admin_client
    token = login(client, "admin@example.com", "admin-password")
    headers = auth_headers(token)

    monkeypatch.setattr(
        "ingestion.pipeline.run_ingestion_pipeline",
        lambda **kwargs: {"chunk_count": 1, "indexed_document_ids": []},
    )
    monkeypatch.setattr(
        "core.startup.reinitialize_rag_components",
        lambda: {"bm25": object(), "reranker": object()},
    )

    first = client.post(
        "/api/admin/documents/upload",
        headers=headers,
        files={"file": ("quy-che.pdf", b"%PDF-1.7 version one", "application/pdf")},
    )
    assert first.status_code == 201
    first_document = first.json()
    assert first_document["version_number"] == 1
    assert first_document["lifecycle_status"] == "draft"

    admin_module._run_reindex_job()
    active_first = client.get("/api/admin/documents", headers=headers).json()[0]
    assert active_first["status"] == "indexed"
    assert active_first["lifecycle_status"] == "active"

    second = client.post(
        "/api/admin/documents/upload",
        headers=headers,
        data={
            "upload_mode": "update",
            "replaces_document_id": str(first_document["id"]),
        },
        files={"file": ("quy-che-moi.pdf", b"%PDF-1.7 version two", "application/pdf")},
    )
    assert second.status_code == 201
    second_document = second.json()
    assert second_document["document_code"] == first_document["document_code"]
    assert second_document["version_number"] == 2
    assert second_document["lifecycle_status"] == "draft"

    before_reindex = {
        document["id"]: document
        for document in client.get("/api/admin/documents", headers=headers).json()
    }
    assert before_reindex[first_document["id"]]["lifecycle_status"] == "active"

    admin_module._run_reindex_job()
    after_reindex = {
        document["id"]: document
        for document in client.get("/api/admin/documents", headers=headers).json()
    }
    assert after_reindex[first_document["id"]]["lifecycle_status"] == "superseded"
    assert after_reindex[second_document["id"]]["lifecycle_status"] == "active"
    assert after_reindex[second_document["id"]]["status"] == "indexed"


def test_admin_reindex_reports_completion_state(admin_client, monkeypatch):
    client, _ = admin_client
    token = login(client, "admin@example.com", "admin-password")

    def fake_reindex_job():
        admin_module._reindex_state["running"] = False
        admin_module._reindex_state["last_finished_at"] = datetime.utcnow().isoformat()

    monkeypatch.setattr(admin_module, "_run_reindex_job", fake_reindex_job)
    response = client.post("/api/admin/documents/reindex", headers=auth_headers(token))

    assert response.status_code == 202
    assert response.json()["message"]
    status_response = client.get("/api/admin/documents/reindex/status", headers=auth_headers(token))
    assert status_response.status_code == 200
    assert status_response.json()["running"] is False
    assert status_response.json()["last_finished_at"] is not None


def test_admin_reindex_status_exposes_progress(admin_client):
    client, _ = admin_client
    token = login(client, "admin@example.com", "admin-password")
    admin_module._reindex_state.update(
        {
            "running": True,
            "stage": "embedding",
            "message": "Đang tạo embedding...",
            "current_step": 2,
            "total_steps": 4,
            "progress_percent": 50,
        }
    )

    response = client.get("/api/admin/documents/reindex/status", headers=auth_headers(token))

    assert response.status_code == 200
    assert response.json()["stage"] == "embedding"
    assert response.json()["message"] == "Đang tạo embedding..."
    assert response.json()["current_step"] == 2
    assert response.json()["total_steps"] == 4
    assert response.json()["progress_percent"] == 50


def test_admin_can_list_and_delete_other_users_but_not_self(admin_client):
    client, _ = admin_client
    token = login(client, "admin@example.com", "admin-password")
    headers = auth_headers(token)

    users = client.get("/api/admin/users", headers=headers)
    assert users.status_code == 200
    student = next(user for user in users.json() if user["role"] == ROLE_STUDENT)
    admin = next(user for user in users.json() if user["role"] == ROLE_ADMIN)

    self_delete = client.delete(f"/api/admin/users/{admin['id']}", headers=headers)
    assert self_delete.status_code == 400

    delete_student = client.delete(f"/api/admin/users/{student['id']}", headers=headers)
    assert delete_student.status_code == 200
    remaining = client.get("/api/admin/users", headers=headers).json()
    assert [user["id"] for user in remaining] == [admin["id"]]
