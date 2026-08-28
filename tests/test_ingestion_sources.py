from pathlib import Path

import ingestion.chunking.pdfDocument as pdf_module
import ingestion.pipeline as pipeline_module


def test_chunk_pdf_documents_processes_only_managed_document_paths(tmp_path, monkeypatch):
    managed = tmp_path / "managed.pdf"
    orphan = tmp_path / "orphan.pdf"
    managed.write_bytes(b"managed")
    orphan.write_bytes(b"orphan")

    monkeypatch.setattr(
        pdf_module,
        "extract_lines_from_pdf",
        lambda path: [(1, path.name)],
    )
    monkeypatch.setattr(
        pdf_module,
        "_build_structured_chunks",
        lambda lines, source_name: [{"text": source_name}],
    )

    chunks = pdf_module.chunk_pdf_documents([managed])

    assert [chunk["text"] for chunk in chunks] == ["managed.pdf"]


def test_ingestion_pipeline_passes_only_database_documents_to_chunker(monkeypatch):
    managed = Path("/managed.pdf")
    received = []

    monkeypatch.setattr(
        pipeline_module,
        "_get_managed_document_sources",
        lambda: [
            pipeline_module.ManagedDocumentSource(
                path=managed,
                source_name="managed-original.pdf",
                document_id=7,
                document_code="DOC-TEST",
                version_number=2,
            )
        ],
    )
    monkeypatch.setattr(
        pipeline_module,
        "chunk_pdf_documents",
        lambda paths: received.extend(paths) or [{"text": "managed", "metadata": {}}],
    )
    monkeypatch.setattr(pipeline_module, "upsert_chunks", lambda chunks: chunks)

    result = pipeline_module.run_ingestion_pipeline()

    assert received == [managed]
    assert result["chunk_count"] == 1
