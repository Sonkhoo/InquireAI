from app.ingestion import enrich
from app.models import Chunk, ChunkMetadata


class _StubDoc:
    def export_to_markdown(self) -> str:
        return "# Sample document\n\nThis is the full document text."


def test_enrich_chunks_adds_context_summary(monkeypatch):
    chunk = Chunk(
        id="chunk-1",
        text="Original chunk text",
        embedding=None,
        metadata=ChunkMetadata(
            file_id="file-1",
            workspace_id="workspace-1",
            filename="sample-1-7.pdf",
            allowed_role_ids=["viewer"],
            chunk_index=0,
            page_start=1,
            page_end=1,
            section_title="Intro",
            token_count=5,
        ),
    )

    monkeypatch.setattr(enrich.tokenizer, "count_tokens", lambda text: 100)
    monkeypatch.setattr(enrich, "_call_groq_for_context", lambda client, document_text, chunk_text: "Context summary")

    result = enrich.enrich_chunks(
        dl_doc=_StubDoc(),
        chunks=[chunk],
        workspace_id="workspace-1",
        filename="sample-1-7.pdf",
        client=object(),
    )

    assert len(result) == 1
    assert result[0].metadata.context_summary == "Context summary"
    assert result[0].text.startswith("Context summary\n\n")
    assert "Original chunk text" in result[0].text
