import pytest
from pathlib import Path

from app.ingestion.parse import parse_document


def test_parse_document():
    pdf = Path(__file__).parent / "test-data" / "sample.pdf"

    dl_doc, document = parse_document(
        file_path=str(pdf),
        workspace_id="test-workspace",
    )

    # Docling document
    assert dl_doc is not None

    # Document metadata
    assert document.filename == pdf.name
    assert document.file_type == "pdf"
    assert document.workspace_id == "test-workspace"

    # Generated fields
    assert document.id is not None
    assert document.checksum is not None
    assert len(document.checksum) == 64  # SHA-256 hex digest
    assert document.total_pages > 0
    assert document.storage_backend == "disk"
    assert document.storage_key == f"local/{pdf.name}"