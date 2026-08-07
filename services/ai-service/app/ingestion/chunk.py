from __future__ import annotations

import uuid
from typing import List
from transformers import AutoTokenizer
from docling.chunking import HybridChunker
from docling_core.types.doc import DoclingDocument
from docling_core.transforms.chunker.hierarchical_chunker import (
    ChunkingDocSerializer,
    ChunkingSerializerProvider,
)
from docling_core.transforms.chunker.tokenizer.huggingface import (
    HuggingFaceTokenizer,
)
from docling_core.transforms.serializer.markdown import (
    MarkdownParams,
    MarkdownTableSerializer,
)

from app.logging import logfire
from app.models import Chunk, ChunkMetadata


EMBED_MODEL_ID = "Qwen/Qwen3-Embedding-4B"
MAX_TOKENS = 512

class MDTableSerializerProvider(ChunkingSerializerProvider):
    """Serialize Docling tables as compact Markdown."""

    def get_serializer(self, doc):
        return ChunkingDocSerializer(
            doc=doc,
            table_serializer=MarkdownTableSerializer(),
            params=MarkdownParams(compact_tables=True),
        )

hf_tokenizer = AutoTokenizer.from_pretrained(EMBED_MODEL_ID)

tokenizer = HuggingFaceTokenizer(
    tokenizer=hf_tokenizer,
    max_tokens=MAX_TOKENS,
)


_CHUNKER = HybridChunker(
    tokenizer=tokenizer,
    merge_peers=True,
    repeat_table_header=True,
    serializer_provider=MDTableSerializerProvider(),
)


def _dedupe_chunks(chunks: List[dict]) -> List[dict]:
    """Deduplicate chunks based on their text content."""
    seen_texts = set()
    deduped_chunks = []
    for chunk in chunks:
        if chunk["text"] not in seen_texts:
            seen_texts.add(chunk["text"])
            deduped_chunks.append(chunk)
    return deduped_chunks

def _extract_page_range(raw_chunk):
    pages = []
    for item in raw_chunk.meta.doc_items:
        for prov in item.prov:
            pages.append(prov.page_no)
    if not pages:
        return None, None
    return min(pages), max(pages)

def _extract_section_title(raw_chunk):
    headings = raw_chunk.meta.headings
    if not headings:
        return None
    return " > ".join(headings)

def chunk_document(
    dl_doc: DoclingDocument,
    file_id: str,
    workspace_id: str,
    filename: str,
    allowed_role_ids: list[str],
) -> List[Chunk]:
    """
    Chunk a Docling document for RAG.
    Pipeline:HybridChunker,contextualize(),deduplicate,Chunk models
    """
    text = dl_doc.export_to_markdown()
    raw_chunks = list(_CHUNKER.chunk(dl_doc=dl_doc))

    logfire.info(
        "Chunking completed",
        filename=filename,
        raw_chunk_count=len(raw_chunks),
        text_length=len(text),
    )

    processed_chunks = []

    for idx, raw_chunk in enumerate(raw_chunks):
        text = _CHUNKER.contextualize(raw_chunk)
        if not text.strip():
            continue
        page_start, page_end = _extract_page_range(raw_chunk)
        section_title = _extract_section_title(raw_chunk)

        processed_chunks.append(
            {
                "text": text,
                "chunk_index": idx,
                "page_start": page_start,
                "page_end": page_end,
                "section_title": section_title,
                "token_count": tokenizer.count_tokens(text),
            }
        )


    processed_chunks = _dedupe_chunks(processed_chunks)

    chunks: List[Chunk] = []

    for chunk in processed_chunks:

        metadata = ChunkMetadata(
            file_id=file_id,
            workspace_id=workspace_id,
            filename=filename,
            allowed_role_ids=allowed_role_ids,
            chunk_index=chunk["chunk_index"],
            page_start=chunk["page_start"],
            page_end=chunk["page_end"],
            section_title=chunk["section_title"],
            token_count=chunk["token_count"],
        )

        chunks.append(
            Chunk(
                id=str(uuid.uuid4()),
                text=chunk["text"],
                embedding=None,      # Filled later by embed.py
                metadata=metadata,
            )
        )

    logfire.info(
        "Chunking summary",
        filename=filename,
        chunk_count=len(chunks),
        raw_chunk_count=len(raw_chunks),
    )
    return chunks