import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.db import SessionLocal, get_db
from core.deps import get_current_admin
from core.file_hash import sha256_stream
from core.models import (
    DOC_LIFECYCLE_ACTIVE,
    DOC_LIFECYCLE_DRAFT,
    DOC_LIFECYCLE_SUPERSEDED,
    DOC_STATUS_FAILED,
    DOC_STATUS_INDEXED,
    DOC_STATUS_PENDING,
    ROLE_ADMIN,
    ChatMessage,
    ChatSession,
    Document,
    User,
)
from core.settings_loader import load_settings

logger = logging.getLogger("admin")
router = APIRouter()

settings = load_settings()
RAW_DATA_DIR = Path(settings.get("data", {}).get("raw_dir", "data/raw"))
ALLOWED_EXTENSIONS = {".pdf"}

# Trang thai job re-index chay nen (in-memory, du cho 1 instance API)
_REINDEX_TOTAL_STEPS = 4
_reindex_lock = Lock()
_reindex_state = {
    "running": False,
    "last_started_at": None,
    "last_finished_at": None,
    "last_error": None,
    "stage": "idle",
    "message": "",
    "current_step": 0,
    "total_steps": _REINDEX_TOTAL_STEPS,
    "progress_percent": 0,
}


def _set_reindex_progress(
    stage: str, message: str, current_step: int, _total_steps: int = _REINDEX_TOTAL_STEPS
) -> None:
    _reindex_state.update(
        {
            "stage": stage,
            "message": message,
            "current_step": current_step,
            "total_steps": _REINDEX_TOTAL_STEPS,
            "progress_percent": round(current_step / _REINDEX_TOTAL_STEPS * 100),
        }
    )


def _schedule_reindex(background_tasks: BackgroundTasks, *, triggered_by: str) -> bool:
    """Start one background re-index job and update its shared status atomically."""
    with _reindex_lock:
        if _reindex_state["running"]:
            return False

        _reindex_state["running"] = True
        _reindex_state["last_started_at"] = datetime.utcnow().isoformat()
        _reindex_state["last_error"] = None
        _set_reindex_progress("extracting", "Đang chuẩn bị re-index...", 1)
        background_tasks.add_task(_run_reindex_job)

    logger.info("Re-index scheduled automatically: %s", triggered_by)
    return True


class UserOut(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    role: str
    created_at: str

    class Config:
        from_attributes = True


class DocumentOut(BaseModel):
    id: int
    filename: str
    original_filename: str
    size_bytes: int
    status: str
    uploaded_by: Optional[int] = None
    uploaded_at: str
    document_code: str
    version_number: int
    lifecycle_status: str
    replaces_document_id: Optional[int] = None

    class Config:
        from_attributes = True


class StatsOut(BaseModel):
    total_users: int
    total_students: int
    total_admins: int
    total_documents: int
    total_chat_sessions: int
    total_messages: int
    qdrant_points_count: Optional[int] = None


class ReindexStatusOut(BaseModel):
    running: bool
    last_started_at: Optional[str] = None
    last_finished_at: Optional[str] = None
    last_error: Optional[str] = None
    stage: Optional[str] = None
    message: Optional[str] = None
    current_step: int = 0
    total_steps: int = _REINDEX_TOTAL_STEPS
    progress_percent: int = 0


def _document_to_out(doc: Document) -> DocumentOut:
    return DocumentOut(
        id=doc.id,
        filename=doc.filename,
        original_filename=doc.original_filename,
        size_bytes=doc.size_bytes,
        status=doc.status,
        uploaded_by=doc.uploaded_by,
        uploaded_at=doc.uploaded_at.isoformat(),
        document_code=doc.document_code,
        version_number=doc.version_number,
        lifecycle_status=doc.lifecycle_status,
        replaces_document_id=doc.replaces_document_id,
    )


# ---------------------------------------------------------------------------
# Thống kê tổng quan (Dashboard)
# ---------------------------------------------------------------------------
@router.get("/stats", response_model=StatsOut)
async def get_stats(current_admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    total_users = db.query(User).count()
    total_admins = db.query(User).filter(User.role == ROLE_ADMIN).count()

    qdrant_points_count = None
    try:
        from vectorstore.qdrant import get_qdrant_client

        client = get_qdrant_client()
        collection_name = settings["vector_database"]["collection_name"]
        info = client.get_collection(collection_name=collection_name)
        qdrant_points_count = info.points_count
    except Exception as e:
        logger.warning(f"Could not fetch Qdrant stats: {e}")

    return StatsOut(
        total_users=total_users,
        total_students=total_users - total_admins,
        total_admins=total_admins,
        total_documents=(
            db.query(Document)
            .filter(
                Document.status == DOC_STATUS_INDEXED,
                Document.lifecycle_status == DOC_LIFECYCLE_ACTIVE,
            )
            .count()
        ),
        total_chat_sessions=db.query(ChatSession).count(),
        total_messages=db.query(ChatMessage).count(),
        qdrant_points_count=qdrant_points_count,
    )


# ---------------------------------------------------------------------------
# Quản lý tài liệu: Upload / Xem / Xóa / Re-index
# ---------------------------------------------------------------------------
@router.get("/documents", response_model=list[DocumentOut])
async def list_documents(current_admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    docs = db.query(Document).order_by(Document.uploaded_at.desc()).all()
    return [_document_to_out(d) for d in docs]


@router.post("/documents/upload", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    upload_mode: str = Form("new"),
    replaces_document_id: Optional[int] = Form(None),
    auto_reindex: bool = Form(True),
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    if _reindex_state["running"]:
        raise HTTPException(status_code=409, detail="Re-index đang chạy, chưa thể tải tài liệu mới.")

    original_filename = file.filename or "document.pdf"
    ext = Path(original_filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Chỉ chấp nhận file PDF (.pdf).")

    mode = upload_mode.strip().lower()
    if mode not in {"new", "update"}:
        raise HTTPException(
            status_code=400,
            detail='upload_mode chỉ nhận giá trị "new" hoặc "update".',
        )

    replaced_document = None
    if mode == "update":
        if replaces_document_id is None:
            raise HTTPException(
                status_code=400,
                detail="Cần chọn tài liệu đang hiệu lực mà phiên bản mới sẽ thay thế.",
            )
        replaced_document = (
            db.query(Document)
            .filter(
                Document.id == replaces_document_id,
                Document.lifecycle_status == DOC_LIFECYCLE_ACTIVE,
            )
            .first()
        )
        if replaced_document is None:
            raise HTTPException(
                status_code=409,
                detail="Tài liệu được chọn không tồn tại hoặc không còn ở trạng thái đang hiệu lực.",
            )
        unfinished_version = (
            db.query(Document)
            .filter(
                Document.document_code == replaced_document.document_code,
                Document.lifecycle_status == DOC_LIFECYCLE_DRAFT,
            )
            .first()
        )
        if unfinished_version is not None:
            raise HTTPException(
                status_code=409,
                detail="Tài liệu này đã có một phiên bản đang chờ xử lý. Hãy xử lý hoặc xóa bản đó trước.",
            )
    elif replaces_document_id is not None:
        raise HTTPException(
            status_code=400,
            detail="Tài liệu mới không được khai báo phiên bản bị thay thế.",
        )

    content_hash = sha256_stream(file.file)
    file.file.seek(0)
    existing = db.query(Document).filter(Document.content_hash == content_hash).first()
    if existing is not None:
        file.file.close()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'Tài liệu có nội dung trùng với "{existing.original_filename}" đã tồn tại.',
        )

    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Sanitize + prefix voi uuid de tranh trung ten/path traversal
    safe_stem = Path(original_filename).stem.replace("/", "_").replace("\\", "_").strip() or "document"
    stored_filename = f"{uuid.uuid4().hex}_{safe_stem}{ext}"
    destination = RAW_DATA_DIR / stored_filename

    try:
        with destination.open("wb") as out_file:
            shutil.copyfileobj(file.file, out_file)
    finally:
        file.file.close()

    size_bytes = destination.stat().st_size

    if replaced_document is None:
        document_code = f"DOC-{uuid.uuid4().hex[:12].upper()}"
        version_number = 1
    else:
        document_code = replaced_document.document_code
        latest_version = (
            db.query(func.max(Document.version_number))
            .filter(Document.document_code == document_code)
            .scalar()
            or 0
        )
        version_number = latest_version + 1

    document = Document(
        filename=stored_filename,
        original_filename=original_filename,
        path=str(destination),
        size_bytes=size_bytes,
        status=DOC_STATUS_PENDING,
        content_hash=content_hash,
        uploaded_by=current_admin.id,
        document_code=document_code,
        version_number=version_number,
        lifecycle_status=DOC_LIFECYCLE_DRAFT,
        replaces_document_id=replaced_document.id if replaced_document is not None else None,
    )
    db.add(document)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if destination.exists():
            destination.unlink()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tài liệu này vừa được upload bởi một admin khác.",
        )
    db.refresh(document)

    logger.info(
        "Admin %s uploaded document %s as %s version %s",
        current_admin.email,
        original_filename,
        document_code,
        version_number,
    )
    if auto_reindex:
        _schedule_reindex(
            background_tasks,
            triggered_by=f'upload "{original_filename}" by {current_admin.email}',
        )
    return _document_to_out(document)


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: int,
    background_tasks: BackgroundTasks,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    if _reindex_state["running"]:
        raise HTTPException(status_code=409, detail="Re-index đang chạy, chưa thể xóa tài liệu.")

    document = db.query(Document).filter(Document.id == document_id).first()
    if document is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu.")

    replacement = (
        db.query(Document)
        .filter(Document.replaces_document_id == document.id)
        .order_by(Document.version_number.desc())
        .first()
    )
    if replacement is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Không thể xóa vì phiên bản {replacement.version_number} đang liên kết với tài liệu này. "
                "Hãy xóa phiên bản mới hơn trước."
            ),
        )

    file_path = Path(document.path)
    if file_path.exists():
        try:
            file_path.unlink()
        except OSError as e:
            logger.warning(f"Could not delete file {file_path}: {e}")

    db.delete(document)
    db.commit()
    logger.info(f"Admin {current_admin.email} deleted document: {document.original_filename}")
    _schedule_reindex(
        background_tasks,
        triggered_by=f'delete "{document.original_filename}" by {current_admin.email}',
    )
    return {"message": "Đã xóa tài liệu. Hệ thống đang tự động re-index dữ liệu tìm kiếm."}


def _run_reindex_job():
    """Re-index corpus va chuyen draft thanh active chi sau khi xu ly thanh cong."""
    from core.startup import reinitialize_rag_components
    from ingestion.pipeline import managed_source_from_document, run_ingestion_pipeline

    db = SessionLocal()
    draft_documents: list[Document] = []
    try:
        draft_documents = (
            db.query(Document)
            .filter(Document.lifecycle_status == DOC_LIFECYCLE_DRAFT)
            .order_by(Document.id)
            .all()
        )
        replaced_ids = {
            document.replaces_document_id
            for document in draft_documents
            if document.replaces_document_id is not None
        }
        active_documents = (
            db.query(Document)
            .filter(Document.lifecycle_status == DOC_LIFECYCLE_ACTIVE)
            .order_by(Document.id)
            .all()
        )
        effective_documents = [
            document for document in active_documents if document.id not in replaced_ids
        ] + draft_documents
        document_sources = [
            managed_source_from_document(document) for document in effective_documents
        ]

        _set_reindex_progress("extracting", "Đang đọc và tách nội dung tài liệu PDF...", 1)
        run_ingestion_pipeline(
            progress_callback=_set_reindex_progress,
            document_sources=document_sources,
            require_all_documents=True,
        )
        _set_reindex_progress("initializing", "Đang khởi tạo bộ tìm kiếm...", 3)
        initialized_components = reinitialize_rag_components()
        if document_sources and initialized_components is None:
            raise RuntimeError("Không thể khởi tạo lại bộ tìm kiếm sau khi lập chỉ mục.")

        for document in active_documents:
            if document.id not in replaced_ids:
                document.status = DOC_STATUS_INDEXED

        for document in draft_documents:
            if document.replaces_document_id is not None:
                replaced_document = db.get(Document, document.replaces_document_id)
                if replaced_document is None or replaced_document.lifecycle_status != DOC_LIFECYCLE_ACTIVE:
                    raise RuntimeError(
                        f"Phiên bản cũ của tài liệu {document.document_code} không còn hiệu lực."
                    )
                replaced_document.lifecycle_status = DOC_LIFECYCLE_SUPERSEDED
            document.status = DOC_STATUS_INDEXED
            document.lifecycle_status = DOC_LIFECYCLE_ACTIVE

        db.commit()
        _reindex_state["last_error"] = None
        _set_reindex_progress("completed", "Đã re-index xong.", _REINDEX_TOTAL_STEPS)
        logger.info("Reindex job completed successfully.")
    except Exception as e:
        logger.error(f"Reindex job failed: {e}", exc_info=True)
        db.rollback()
        draft_ids = [document.id for document in draft_documents]
        if draft_ids:
            (
                db.query(Document)
                .filter(Document.id.in_(draft_ids))
                .update({Document.status: DOC_STATUS_FAILED}, synchronize_session=False)
            )
        db.commit()
        _reindex_state["last_error"] = str(e)
        _reindex_state["message"] = f"Re-index thất bại: {e}"
        _reindex_state["stage"] = "failed"
    finally:
        db.close()
        with _reindex_lock:
            _reindex_state["running"] = False
            _reindex_state["last_finished_at"] = datetime.utcnow().isoformat()


@router.post("/documents/reindex", status_code=status.HTTP_202_ACCEPTED)
async def reindex_documents(
    background_tasks: BackgroundTasks, current_admin: User = Depends(get_current_admin)
):
    if not _schedule_reindex(
        background_tasks,
        triggered_by=f"manual request by {current_admin.email}",
    ):
        raise HTTPException(status_code=409, detail="Re-index đang chạy, vui lòng chờ hoàn tất.")
    return {"message": "Đã bắt đầu re-index dữ liệu. Quá trình này có thể mất vài phút."}


@router.get("/documents/reindex/status", response_model=ReindexStatusOut)
async def reindex_status(current_admin: User = Depends(get_current_admin)):
    return ReindexStatusOut(**_reindex_state)


# ---------------------------------------------------------------------------
# Quản lý người dùng
# ---------------------------------------------------------------------------
@router.get("/users", response_model=list[UserOut])
async def list_users(current_admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [
        UserOut(
            id=u.id, email=u.email, full_name=u.full_name, role=u.role, created_at=u.created_at.isoformat()
        )
        for u in users
    ]


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int, current_admin: User = Depends(get_current_admin), db: Session = Depends(get_db)
):
    if user_id == current_admin.id:
        raise HTTPException(status_code=400, detail="Không thể tự xóa tài khoản của chính mình.")

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng.")

    uploaded_documents = db.query(Document).filter(Document.uploaded_by == user.id).count()
    if uploaded_documents:
        raise HTTPException(
            status_code=409,
            detail="Không thể xóa người dùng đã tải tài liệu vì cần giữ thông tin người tải lên.",
        )

    db.delete(user)
    db.commit()
    logger.info(f"Admin {current_admin.email} deleted user: {user.email}")
    return {"message": "Đã xóa người dùng."}
