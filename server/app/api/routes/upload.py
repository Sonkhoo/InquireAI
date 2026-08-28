"""
File upload endpoint for document ingestion.
Validates uploaded files and triggers the AI ingestion pipeline for processing and storage.
"""


import uuid
from pathlib import Path
import tempfile

from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException
import logfire

from app.models import UploadResponse
from app.ingestion.main import run_pipeline
from app.ingestion.parse import SUPPORTED_TYPES
from app.exceptions import TerminalParseError
from app.db.store import TerminalStoreError
from app.memory import memory

router = APIRouter(tags=["Files"])

UPLOAD_DIR = Path(tempfile.gettempdir()) / "inquire-uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_FILE_SIZE_MB = 50


@router.post("/files", response_model=UploadResponse)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    workspace_id: str = Form(...),
    user_email: str = Form(...),  # demo stand-in for auth
    allowed_role_ids: str = Form(...),  # comma-separated, e.g. "viewer,admin"
):
    # Only admins may ingest documents (auth is skipped for the demo — the
    # frontend sends the selected user's email and we look up their role).
    user = memory.get_user_by_email(user_email)
    if not user:
        raise HTTPException(status_code=404, detail=f"Unknown demo user: {user_email}")
    if user["role"] != "admin":
        raise HTTPException(
            status_code=403,
            detail=f"Only admins can ingest files (user role: {user['role']})",
        )
    logfire.info("files route: admin verified", email=user_email, role=user["role"])

    if file.filename is None or file.filename.strip() == "":
        raise HTTPException(
            status_code=400,
            detail="File must have a valid filename",
        )
    ext_check = Path(file.filename).suffix.lstrip(".").lower()
    if ext_check not in SUPPORTED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext_check}"
        )

    role_ids = [r.strip() for r in allowed_role_ids.split(",") if r.strip()]

    if not role_ids:
        raise HTTPException(
            status_code=400,
            detail="allowed_role_ids cannot be empty"
        )

    safe_filename = Path(file.filename).name
    file_id = str(uuid.uuid4())
    ext = Path(safe_filename).suffix  # e.g. ".pdf"
    dest_path = UPLOAD_DIR / f"{file_id}{ext}"

    size = 0

    with dest_path.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)

            if size > MAX_FILE_SIZE_MB * 1024 * 1024:
                dest_path.unlink(missing_ok=True)

                raise HTTPException(
                    status_code=413,
                    detail="File too large"
                )

            out.write(chunk)

    logfire.info(
        "files route: upload received",
        filename=file.filename,
        workspace_id=workspace_id,
        size_bytes=size,
    )

    try:
        n_stored = run_pipeline(
            str(dest_path),
            workspace_id,
            role_ids,
            file_id,
            filename=safe_filename,
        )

    except (TerminalParseError, TerminalStoreError) as exc:
        logfire.error(f"files route: ingestion failed: {exc}")

        raise HTTPException(
            status_code=422,
            detail=str(exc),
        )

    finally:
        dest_path.unlink(missing_ok=True)

    if n_stored == 0:
        raise HTTPException(
            status_code=422,
            detail="Document parsed but no chunks were safely stored.",
        )

    return UploadResponse(
        file_id=file_id,
        filename=file.filename or "",
        status="success",
        chunks_stored=n_stored,
    )