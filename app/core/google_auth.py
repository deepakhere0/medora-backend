from google.oauth2 import id_token
from google.auth.transport import requests as google_requests


def verify_google_token(token: str, client_id: str) -> dict:
    """Verify Google OAuth ID token and return user info.

    Raises ValueError if the token is invalid or expired.
    """
    idinfo = id_token.verify_oauth2_token(
        token,
        google_requests.Request(),
        client_id,
    )
    return {
        "email": idinfo.get("email"),
        "name": idinfo.get("name"),
        "picture": idinfo.get("picture"),
        "email_verified": idinfo.get("email_verified", False),
        "google_id": idinfo.get("sub"),
    }
