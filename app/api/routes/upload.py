"""
File upload endpoint for document ingestion.
Validates uploaded files and triggers the AI ingestion pipeline for processing and storage.
"""


import uuid
from pathlib import Path

from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException
import logfire

from app.models import UploadResponse
from app.ingestion.main import run_pipeline
from app.ingestion.parse import SUPPORTED_TYPES
from app.exceptions import TerminalParseError
from app.db.store import TerminalStoreError
from app.db import memory

router = APIRouter(tags=["Files"])

UPLOAD_DIR = Path("/tmp/inquire-uploads")
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

    ext = file.filename.rsplit(".", 1)[-1].lower()

    if ext not in SUPPORTED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}"
        )

    role_ids = [r.strip() for r in allowed_role_ids.split(",") if r.strip()]

    if not role_ids:
        raise HTTPException(
            status_code=400,
            detail="allowed_role_ids cannot be empty"
        )

    file_id = str(uuid.uuid4())
    dest_path = UPLOAD_DIR / f"{file_id}_{file.filename}"

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
        filename=file.filename,
        status="success",
        chunks_stored=n_stored,
    )