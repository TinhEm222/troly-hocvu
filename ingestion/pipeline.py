import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ingestion.chunking.pdfDocument import chunk_pdf_documents
from core.logging_setup import setup_logging
from core.db import SessionLocal
from core.models import DOC_LIFECYCLE_ACTIVE, Document

from vectorstore.upsert import upsert_chunks

setup_logging()
logger = logging.getLogger("ingestion")


@dataclass(frozen=True)
class ManagedDocumentSource:
    path: Path
    source_name: str
    document_id: int | None = None
    document_code: str | None = None
    version_number: int | None = None


def managed_source_from_document(document: Document) -> ManagedDocumentSource:
    return ManagedDocumentSource(
        path=Path(document.path),
        source_name=document.original_filename,
        document_id=document.id,
        document_code=document.document_code,
        version_number=document.version_number,
    )


def _get_managed_document_sources() -> list[ManagedDocumentSource]:
    """Lay dung cac phien ban ACTIVE dang duoc quan ly trong SQLite."""
    db = SessionLocal()
    try:
        sources = []
        documents = (
            db.query(Document)
            .filter(Document.lifecycle_status == DOC_LIFECYCLE_ACTIVE)
            .order_by(Document.id)
            .all()
        )
        for document in documents:
            path = Path(document.path)
            if path.is_file() and path.suffix.lower() == ".pdf":
                sources.append(managed_source_from_document(document))
            else:
                logger.warning(
                    "Skipping managed document %s because file is missing or not a PDF: %s",
                    document.id,
                    path,
                )
        return sources
    finally:
        db.close()


def _get_managed_document_paths() -> list[Path]:
    """Compatibility helper used by scripts/tests that only need filesystem paths."""
    return [source.path for source in _get_managed_document_sources()]


def run_ingestion_pipeline(
    progress_callback: Callable[[str, str, int, int], None] | None = None,
    document_sources: list[ManagedDocumentSource] | None = None,
    require_all_documents: bool = False,
):
    """
    Pipeline nạp dữ liệu từ các tài liệu PDF nội bộ của trường
    (quy chế đào tạo, sổ tay sinh viên, quy định học phí, chuẩn đầu ra...)
    đặt trong thư mục data/raw/.
    """
    sources = document_sources if document_sources is not None else _get_managed_document_sources()
    all_chunks = []
    indexed_document_ids: list[int] = []
    missing_sources: list[ManagedDocumentSource] = []

    if progress_callback:
        progress_callback(
            "extracting",
            f"Đang đọc và tách {len(sources)} tài liệu PDF...",
            1,
            4,
        )

    for source in sources:
        chunks = chunk_pdf_documents([source.path])
        if not chunks:
            missing_sources.append(source)
            continue

        for chunk in chunks:
            metadata = chunk.setdefault("metadata", {})
            metadata["source"] = source.source_name
            if source.document_id is not None:
                metadata["document_id"] = source.document_id
            if source.document_code is not None:
                metadata["document_code"] = source.document_code
            if source.version_number is not None:
                metadata["version_number"] = source.version_number

        all_chunks.extend(chunks)
        if source.document_id is not None:
            indexed_document_ids.append(source.document_id)

    if missing_sources and require_all_documents:
        names = ", ".join(source.source_name for source in missing_sources)
        raise ValueError(f"Không trích xuất được nội dung từ tài liệu: {names}")

    if progress_callback:
        progress_callback(
            "embedding",
            (
                f"Đã tách {len(all_chunks)} đoạn; đang tạo embedding và cập nhật vector..."
                if all_chunks
                else "Không còn tài liệu hiệu lực; đang làm rỗng kho vector..."
            ),
            2,
            4,
        )
    upsert_chunks(all_chunks)
    logger.info(f"Upserted {len(all_chunks)} chunks into the vector store.")
    return {
        "chunk_count": len(all_chunks),
        "indexed_document_ids": indexed_document_ids,
        "missing_sources": [source.source_name for source in missing_sources],
    }
    
if __name__ == "__main__":
    run_ingestion_pipeline()
