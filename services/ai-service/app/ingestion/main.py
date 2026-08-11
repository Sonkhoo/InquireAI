from __future__ import annotations

import time
import uuid

from app.logging import logfire
from app.ingestion.parse import parse_document, TerminalParseError
from app.ingestion.chunk import chunk_document
from app.ingestion.enrich import enrich_chunks
from app.db.store import store_chunks, TerminalStoreError


def run_pipeline(
    file_path: str,
    workspace_id: str,
    allowed_role_ids: list[str],
    file_id: str | None = None,
) -> int:
    """
    Runs one file through the full ingestion pipeline.
    Pipeline:parse -> chunk -> enrich -> store
    Returns:
        Number of chunks successfully stored.

    Raises:
        TerminalParseError: If parsing fails permanently.
        TerminalStoreError: If storing fails permanently.
    """

    file_id = file_id or str(uuid.uuid4())
    filename = file_path.rsplit("/", 1)[-1]

    pipeline_start = time.monotonic()

    logfire.info(
        f"INGESTION START | "
        f"file={filename} | "
        f"file_id={file_id} | "
        f"workspace_id={workspace_id}"
    )

    # Parsing stage

    logfire.info(f"STEP START | parse | file={filename}")

    parse_start = time.monotonic()

    try:
        dl_doc = parse_document(file_path, workspace_id)
    except TerminalParseError as exc:
        parse_elapsed = time.monotonic() - parse_start

        logfire.error(
            f"STEP FAILED | parse | "
            f"file={filename} | "
            f"elapsed={parse_elapsed:.3f}s | "
            f"error={exc}"
        )
        raise

    parse_elapsed = time.monotonic() - parse_start

    logfire.info(
        f"STEP END | parse | "
        f"file={filename} | "
        f"elapsed={parse_elapsed:.3f}s"
    )

    # Chunking stage

    logfire.info(f"STEP START | chunk | file={filename}")

    chunk_start = time.monotonic()

    chunks = chunk_document(
        dl_doc=dl_doc,
        file_id=file_id,
        workspace_id=workspace_id,
        filename=filename,
        allowed_role_ids=allowed_role_ids,
    )

    chunk_elapsed = time.monotonic() - chunk_start

    logfire.info(
        f"STEP END | chunk | "
        f"file={filename} | "
        f"chunks={len(chunks)} | "
        f"elapsed={chunk_elapsed:.3f}s"
    )

    if not chunks:
        logfire.error(
            f"CHUNKING EMPTY | "
            f"file={filename} | "
            f"elapsed={chunk_elapsed:.3f}s"
        )
        return 0

    # Enrichment stage

    logfire.info(
        f"STEP START | enrich | "
        f"file={filename} | "
        f"chunks={len(chunks)}"
    )

    enrich_start = time.monotonic()

    chunks = enrich_chunks(
        dl_doc=dl_doc,
        chunks=chunks,
        workspace_id=workspace_id,
        filename=filename,
    )

    enrich_elapsed = time.monotonic() - enrich_start

    logfire.info(
        f"STEP END | enrich | "
        f"file={filename} | "
        f"chunks={len(chunks)} | "
        f"elapsed={enrich_elapsed:.3f}s"
    )

    # Embedding and storing stage

    logfire.info(
        f"STEP START | store | "
        f"file={filename} | "
        f"chunks={len(chunks)}"
    )

    store_start = time.monotonic()

    try:
        n_stored = store_chunks(chunks)
    except TerminalStoreError as exc:
        store_elapsed = time.monotonic() - store_start

        logfire.error(
            f"STEP FAILED | store | "
            f"file={filename} | "
            f"elapsed={store_elapsed:.3f}s | "
            f"error={exc}"
        )
        raise

    store_elapsed = time.monotonic() - store_start

    logfire.info(
        f"STEP END | store | "
        f"file={filename} | "
        f"stored={n_stored} | "
        f"elapsed={store_elapsed:.3f}s"
    )

    
    pipeline_elapsed = time.monotonic() - pipeline_start

    logfire.info(
        f"INGESTION COMPLETE | "
        f"file={filename} | "
        f"file_id={file_id} | "
        f"chunks={n_stored} | "
        f"total_elapsed={pipeline_elapsed:.3f}s"
    )

    return n_stored