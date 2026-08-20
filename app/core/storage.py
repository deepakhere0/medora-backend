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




def upload_certificate(
    file_bytes: bytes,
    file_name: str,
    content_type: str,
    org_id: UUID,
) -> str:
    timestamp = int(time.time())
    safe_name = file_name.replace(" ", "_")
    path = f"registration-certificates/{org_id}/{timestamp}_{safe_name}"

    try:
        supabase_client.storage             .from_(settings.SUPABASE_BUCKET)             .upload(
                path=path,
                file=file_bytes,
                file_options={"content-type": content_type, "upsert": "true"},
            )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Certificate upload failed: {exc}",
        )

    public_url: str = supabase_client.storage         .from_(settings.SUPABASE_BUCKET)         .get_public_url(path)
    return public_url

def upload_doctor_photo(
    file_bytes: bytes,
    content_type: str,
    doctor_id: UUID,
    ext: str,
) -> str:
    """Upload a doctor's profile photo and return its public URL."""
    path = f"doctors/{doctor_id}/profile.{ext}"
    try:
        supabase_client.storage \
            .from_(settings.SUPABASE_BUCKET) \
            .upload(
                path=path,
                file=file_bytes,
                file_options={"content-type": content_type, "upsert": "true"},
            )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Photo upload failed: {exc}",
        )
    return supabase_client.storage.from_(settings.SUPABASE_BUCKET).get_public_url(path)


def upload_doctor_certificate(
    file_bytes: bytes,
    content_type: str,
    doctor_id: UUID,
    ext: str,
) -> str:
    """Upload a doctor's NMC certificate and return its public URL."""
    path = f"doctors/{doctor_id}/nmc_certificate.{ext}"
    try:
        supabase_client.storage \
            .from_(settings.SUPABASE_BUCKET) \
            .upload(
                path=path,
                file=file_bytes,
                file_options={"content-type": content_type, "upsert": "true"},
            )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Certificate upload failed: {exc}",
        )
    return supabase_client.storage.from_(settings.SUPABASE_BUCKET).get_public_url(path)


def upload_logo(
    file_bytes: bytes,
    file_name: str,
    content_type: str,
    org_id: UUID,
) -> str:
    timestamp = int(time.time())
    safe_name = file_name.replace(" ", "_")
    path = f"logos/{org_id}/{timestamp}_{safe_name}"

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
            detail="Logo upload failed",
        )

    # 10-year signed URL — effectively permanent for a logo
    expires_in = 10 * 365 * 24 * 3600
    try:
        response = supabase_client.storage \
            .from_(settings.SUPABASE_BUCKET) \
            .create_signed_url(path, expires_in)
        return response["signedURL"]
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not generate logo URL",
        )
