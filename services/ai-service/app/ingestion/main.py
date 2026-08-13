from __future__ import annotations

import argparse
import sys
import time
import uuid

from app.logging import logfire
from app.ingestion.parse import parse_document, TerminalParseError
from app.ingestion.chunk import chunk_document
from app.ingestion.enrich import enrich_chunks
from app.ingestion.clean import (
    clean_text,
    is_safe_chunk,
)
from app.guardrails.prompt_guard import detect_prompt_injection
from app.db.store import store_chunks, TerminalStoreError


def run_pipeline(
    file_path: str,
    workspace_id: str,
    allowed_role_ids: list[str],
    file_id: str | None = None,
) -> int:
    """
    Run one file through the complete ingestion pipeline.

    Pipeline:
        parse
        -> clean
        -> prompt-injection screening
        -> chunk
        -> chunk safety checks
        -> enrich
        -> embed/store

    Returns:
        Number of chunks successfully stored.
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

    # ---------------------------------------------------------
    # 1. Parse
    # ---------------------------------------------------------

    parse_start = time.monotonic()

    try:
        dl_doc, doc = parse_document(
            file_path,
            workspace_id,
        )

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

    # ---------------------------------------------------------
    # 2. Chunk
    # ---------------------------------------------------------

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
            f"file={filename}"
        )
        return 0

    # ---------------------------------------------------------
    # 3. Chunk safety checks
    # ---------------------------------------------------------

    safe_chunks = []

    for chunk in chunks:
        if is_safe_chunk(chunk.text):
            safe_chunks.append(chunk)
        else:
            logfire.warning(
                f"UNSAFE CHUNK SKIPPED | "
                f"file={filename}"
            )

    chunks = safe_chunks

    if not chunks:
        logfire.error(
            f"NO SAFE CHUNKS | "
            f"file={filename}"
        )
        return 0

    logfire.info(
        f"STEP END | chunk-safety | "
        f"file={filename} | "
        f"safe_chunks={len(chunks)}"
    )

    # ---------------------------------------------------------
    # 4. Enrichment
    # ---------------------------------------------------------

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

    # ---------------------------------------------------------
    # 5. Embedding + Qdrant storage
    # ---------------------------------------------------------

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

    # ---------------------------------------------------------
    # 6. Complete
    # ---------------------------------------------------------

    pipeline_elapsed = time.monotonic() - pipeline_start

    logfire.info(
        f"INGESTION COMPLETE | "
        f"file={filename} | "
        f"file_id={file_id} | "
        f"chunks={n_stored} | "
        f"total_elapsed={pipeline_elapsed:.3f}s"
    )

    return n_stored


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the AI Core document ingestion pipeline."
    )

    parser.add_argument(
        "--file",
        required=True,
        help="Path to the document to ingest.",
    )

    parser.add_argument(
        "--workspace-id",
        required=True,
        help="Workspace ID that owns the document.",
    )

    parser.add_argument(
    "--allowed-role-ids",
    dest="allowed_role_ids",
    action="append",
    default=[],
    help="Role IDs allowed to access this document. Can be specified multiple times.",
    )

    parser.add_argument(
        "--file-id",
        default=None,
        help="Optional file ID. Generated automatically if omitted.",
    )

    args = parser.parse_args()
    args.allowed_role_ids = [
        role_id for group in args.allowed_role_ids for role_id in group
    ]
    return args


def main() -> None:
    args = parse_args()

    try:
        stored = run_pipeline(
            file_path=args.file,
            workspace_id=args.workspace_id,
            allowed_role_ids=args.allowed_role_ids,
            file_id=args.file_id,
        )

        print(f"\nIngestion complete. Stored {stored} chunks.")

    except (TerminalParseError, TerminalStoreError) as exc:
        print(
            f"\nIngestion failed: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    except Exception as exc:
        logfire.exception(
            "UNEXPECTED INGESTION ERROR",
            error=str(exc),
        )

        print(
            f"\nUnexpected ingestion error: {exc}",
            file=sys.stderr,
        )

        sys.exit(1)


if __name__ == "__main__":
    main()