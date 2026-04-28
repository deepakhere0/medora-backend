import logging
import uuid
from uuid import UUID

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.core.storage import supabase_client

logger = logging.getLogger(__name__)

# ── Allowed types ──────────────────────────────────────────────────────────────

ALLOWED_MIME = {"image/jpeg", "image/png", "application/pdf"}
_EXT_MAP     = {"image/jpeg": "jpg", "image/png": "png", "application/pdf": "pdf"}
# 5 MB limit applied uniformly across all file types
MAX_BYTES    = 5 * 1024 * 1024

VALID_UPLOAD_TYPES = {"prescription", "lab_test", "scan", "report", "vaccination"}


async def upload_report_file(
    file: UploadFile,
    patient_id: UUID,
) -> tuple[str, str, str, int]:
    """
    Validate and upload a patient report file to Supabase Storage.

    Returns (storage_path, public_url, file_type, file_size_bytes).
    Raises HTTPException for validation or upload failures.
    """
    file_type = (file.content_type or "").split(";")[0].strip()

    # Validate MIME type — do NOT echo the submitted value back to the user
    # (prevents reflecting an attacker-controlled string in the error body).
    if file_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                "Only PDF, JPG, and PNG files are accepted. "
                "Please convert your file and try again."
            ),
        )

    file_bytes = await file.read()
    size = len(file_bytes)

    if size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is empty.",
        )

    if size > MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File is too large. Maximum allowed size is 5 MB.",
        )

    ext  = _EXT_MAP[file_type]
    path = f"patient-reports/{patient_id}/{uuid.uuid4()}.{ext}"

    try:
        supabase_client.storage.from_(settings.SUPABASE_BUCKET).upload(
            path=path,
            file=file_bytes,
            file_options={"content-type": file_type},
        )
    except Exception as exc:
        # Log only the exception class name and patient_id — never the full
        # exception message, which may contain storage paths or credentials.
        logger.error(
            "supabase_upload_failed patient_id=%s error_type=%s",
            patient_id,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="File upload failed. Please try again.",
        )

    public_url: str = (
        supabase_client.storage.from_(settings.SUPABASE_BUCKET).get_public_url(path)
    )
    return path, public_url, file_type, size


def delete_uploaded_file(path: str) -> None:
    """Best-effort Supabase cleanup for atomic rollback. Never raises."""
    try:
        supabase_client.storage.from_(settings.SUPABASE_BUCKET).remove([path])
    except Exception as exc:
        # Log only exception type — not the path — to avoid leaking storage layout.
        logger.warning(
            "orphaned_file_cleanup_failed error_type=%s",
            type(exc).__name__,
        )


def get_public_url(storage_path: str) -> str:
    """Convert a storage path to a public URL."""
    return supabase_client.storage.from_(settings.SUPABASE_BUCKET).get_public_url(storage_path)
