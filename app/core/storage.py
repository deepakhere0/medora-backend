import time
from uuid import UUID

from fastapi import HTTPException, status
from supabase import create_client, Client

from app.core.config import settings


supabase_client: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_KEY,
)


def upload_file(
    file_bytes: bytes,
    file_name: str,
    content_type: str,
    org_id: UUID,
    patient_id: UUID,
) -> str:
    timestamp = int(time.time())
    safe_name = file_name.replace(" ", "_")
    path = f"{org_id}/{patient_id}/{timestamp}_{safe_name}"

    try:
        supabase_client.storage \
            .from_(settings.SUPABASE_BUCKET) \
            .upload(
                path=path,
                file=file_bytes,
                file_options={"content-type": content_type},
            )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="File upload failed",
        )

    return path


def get_signed_url(file_path: str) -> str:
    expires_in: int = 365 * 24 * 3600

    try:
        response = supabase_client.storage \
            .from_(settings.SUPABASE_BUCKET) \
            .create_signed_url(file_path, expires_in)

        signed_url: str = response["signedURL"]
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not generate download URL",
        )

    return signed_url


def delete_file(file_path: str) -> None:
    try:
        supabase_client.storage \
            .from_(settings.SUPABASE_BUCKET) \
            .remove([file_path])
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="File deletion failed",
        )
