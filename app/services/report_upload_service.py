import logging
import uuid
from uuid import UUID

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.core.storage import supabase_client

logger = logging.getLogger(__name__)

ALLOWED_MIME = {"image/jpeg", "image/png", "application/pdf"}
IMAGE_MAX_BYTES = 10 * 1024 * 1024   # 10 MB
PDF_MAX_BYTES   = 20 * 1024 * 1024   # 20 MB
_EXT_MAP = {"image/jpeg": "jpg", "image/png": "png", "application/pdf": "pdf"}

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

    if file_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only JPEG, PNG, and PDF files are allowed",
        )

    file_bytes = await file.read()
    size = len(file_bytes)
    max_bytes = IMAGE_MAX_BYTES if file_type.startswith("image/") else PDF_MAX_BYTES
    if size > max_bytes:
        limit_mb = max_bytes // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large — maximum {limit_mb} MB for {file_type}",
        )

    ext = _EXT_MAP[file_type]
    path = f"patient-reports/{patient_id}/{uuid.uuid4()}.{ext}"

    try:
        supabase_client.storage.from_(settings.SUPABASE_BUCKET).upload(
            path=path,
            file=file_bytes,
            file_options={"content-type": file_type},
        )
    except Exception as exc:
        logger.error("Supabase upload failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="File upload failed",
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
        logger.warning("Failed to delete orphaned report file %s: %s", path, exc)


def get_public_url(storage_path: str) -> str:
    """Convert a storage path to a public URL. Works for patient-reports/ paths."""
    return supabase_client.storage.from_(settings.SUPABASE_BUCKET).get_public_url(storage_path)
