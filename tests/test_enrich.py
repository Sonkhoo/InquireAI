from pathlib import Path

from app.ingestion.parse import parse_document
from app.ingestion.chunk import chunk_document
from app.ingestion.enrich import enrich_chunks


def test_enrich_chunks():
    pdf = Path(__file__).parent / "test-data" / "sample-1-7.pdf"

    # 1. Real parsing
    dl_doc, document = parse_document(
        file_path=str(pdf),
        workspace_id="test-workspace",
    )

    assert dl_doc is not None

    # 2. Real structure-aware chunking
    chunks = chunk_document(
        dl_doc=dl_doc,
        file_id=document.id,
        workspace_id=document.workspace_id,
        filename=document.filename,
        allowed_role_ids=["viewer", "admin"],
    )

    assert len(chunks) > 0

    # 3. Real enrichment
    result = enrich_chunks(
        dl_doc=dl_doc,
        chunks=chunks,
        workspace_id=document.workspace_id,
        filename=document.filename,
    )

    # 4. Chunk count should not change
    assert len(result) == len(chunks)

    # 5. Every chunk should have a context summary
    for chunk in result:
        # Image-only chunks are intentionally skipped
        if chunk.text.strip() == "<!-- image -->":
            continue

        assert chunk.metadata.context_summary is not None
        assert chunk.metadata.context_summary.strip() != ""

        assert chunk.text.startswith(
            f"{chunk.metadata.context_summary}\n\n"
        )

        print("\n" + "=" * 80)
        print(f"Chunk index: {chunk.metadata.chunk_index}")
        print(f"Context summary: {chunk.metadata.context_summary}")
        print(f"Text:\n{chunk.text}")


if __name__ == "__main__":
    test_enrich_chunks()