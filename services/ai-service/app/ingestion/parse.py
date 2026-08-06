"""
parse.py — Parse a document with Docling and return:
1. DoclingDocument (for chunking)
2. Document model (for tracking/Postgres)

No chunking, embedding, or vector storage.
"""

import hashlib
import os
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import psutil
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableStructureOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import DoclingDocument

from app.exceptions import RetryableParseError, TerminalParseError
from app.logging import init_logging, logfire
from app.models import Document

init_logging()

MAX_PDF_PAGES = 300
SUPPORTED_TYPES = {"pdf", "docx", "xlsx", "md"}

_PROC = psutil.Process(os.getpid())


pdf_opts = PdfPipelineOptions()
pdf_opts.do_ocr = False
pdf_opts.do_table_structure = True
pdf_opts.generate_page_images = False
pdf_opts.table_structure_options = TableStructureOptions(do_cell_matching=False)

_CONVERTER = DocumentConverter(
    allowed_formats=[
        InputFormat.PDF,
        InputFormat.DOCX,
        InputFormat.XLSX,
        InputFormat.MD,
    ],
    format_options={
        InputFormat.PDF: PdfFormatOption(
            pipeline_options=pdf_opts,
            backend=PyPdfiumDocumentBackend,
        ),
    },
)


def _rss_mb() -> float:
    return _PROC.memory_info().rss / 1024**2


def _compute_checksum(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()


@retry(
    retry=retry_if_exception_type(RetryableParseError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _convert(path: Path) -> DoclingDocument:
    try:
        result = _CONVERTER.convert(str(path), page_range=(1, MAX_PDF_PAGES))
    except FileNotFoundError as e:
        raise TerminalParseError(f"File not found: {path}") from e
    except Exception as e:
        logfire.warning("Document conversion failed", filename=path.name, error=str(e))
        raise RetryableParseError(str(e)) from e

    # PARTIAL_SUCCESS means Docling silently dropped pages (e.g. a resource
    # failure partway through). A doc missing pages is worse than no doc —
    # this is terminal, not retryable: retrying re-runs the same pipeline
    # against the same file and will hit the same wall at the same page.
    if result.status.name == "PARTIAL_SUCCESS":
        logfire.error(f"Partial conversion for {path.name}: {result.errors}")
        raise TerminalParseError(
            f"Docling only partially converted {path.name} "
            f"(missing pages) — errors: {result.errors}"
        )

    if result.status.name == "FAILURE":
        raise TerminalParseError(f"Docling failed to convert {path}: {result.errors}")

    return result.document


def parse_document(file_path: str, workspace_id: str) -> tuple[DoclingDocument, Document]:
    path = Path(file_path)

    if not path.exists():
        raise TerminalParseError(f"File does not exist: {file_path}")

    file_type = path.suffix.lower().lstrip(".")
    if file_type not in SUPPORTED_TYPES:
        raise TerminalParseError(f"Unsupported file type: {file_type}")

    logfire.info("Starting document parse", filename=path.name, file_type=file_type)
    checksum = _compute_checksum(path)

    try:
        dl_doc = _convert(path)
    except TerminalParseError:
        logfire.error(f"Terminal parse failure for {path.name}")
        raise
    except RetryableParseError as e:
        logfire.error(f"Parse failed after retries for {path.name}: {e}")
        raise TerminalParseError(f"Exhausted retries parsing {path.name}") from e

    total_pages = len(dl_doc.pages) if getattr(dl_doc, "pages", None) else 0

    document = Document(
        id=str(uuid.uuid4()),
        filename=path.name,
        file_type=file_type,
        workspace_id=workspace_id,
        storage_backend="disk",
        storage_key=f"local/{path.name}",
        uploaded_at=datetime.now(timezone.utc),
        total_pages=total_pages,
        checksum=checksum,
        metadata={},
    )

    logfire.info(
        "Document parsed successfully",
        filename=path.name,
        total_pages=total_pages,
        text_items=len(dl_doc.texts),
        table_count=len(dl_doc.tables),
    )

    return dl_doc, document