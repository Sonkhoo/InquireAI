import pytest
from pathlib import Path

from app.ingestion.parse import parse_document
from app.ingestion.chunk import chunk_document


def test_chunk_document():
    pdf = Path(__file__).parent / "test-data" / "sample.pdf"

    dl_doc, document = parse_document(
        file_path=str(pdf),
        workspace_id="test-workspace",
    )

    chunks = chunk_document(
        dl_doc=dl_doc,
        file_id=document.id,
        workspace_id=document.workspace_id,
        filename=document.filename,
        allowed_role_ids=["viewer", "admin"],
    )

    # At least one chunk should be produced
    assert len(chunks) > 0

    for i, chunk in enumerate(chunks):
        # Chunk object
        assert chunk.id is not None
        assert chunk.metadata.chunk_index == i

        # Text
        assert chunk.text is not None
        assert chunk.text.strip() != ""

        # Embedding is added later
        assert chunk.embedding is None

        # Metadata
        meta = chunk.metadata

        assert meta.file_id == document.id
        assert meta.workspace_id == document.workspace_id
        assert meta.filename == document.filename
        assert meta.allowed_role_ids == ["viewer", "admin"]

        assert meta.chunk_index == i

        # Token count
        assert meta.token_count > 0

        # Optional page information
        if meta.page_start is not None and meta.page_end is not None:
            assert meta.page_start <= meta.page_end