from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.models import Document
from app.worker.loader import DocumentLoader


def _resolve_pdf_path() -> Path:
    env_path = os.getenv("DOCLOADER_TEST_PDF")
    if env_path:
        return Path(env_path)

    return Path(__file__).parent / "test-data" / "sample.pdf"

@pytest.mark.smoke
def test_document_loader_smoke() -> None:
    pdf_path = _resolve_pdf_path()

    if not pdf_path.exists():
        pytest.skip(f"No PDF found at {pdf_path}. Put a sample PDF there or set DOCLOADER_TEST_PDF.")

    loader = DocumentLoader(str(pdf_path))
    document = loader.load()

    assert isinstance(document, Document)
    assert document.id
    assert document.filename
    assert document.file_type
    assert document.workspace_id
    assert document.storage_key
    assert document.uploaded_at is not None
    assert document.total_pages >= 0
    assert document.metadata is not None
