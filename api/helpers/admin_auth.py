import hmac

from fastapi import HTTPException, status


def require_admin_token(x_admin_token: str) -> None:
    """Shared check for the `_require_admin` dependency duplicated across
    store_api.py, sponsored_post_api.py, and subscription_api.py.

    Denies the request outright when ADMIN_TOKEN isn't configured, rather
    than comparing against an empty string — an unset secret must never be
    treated as a wildcard match for an empty/missing header.
    """
    from config import AdminConfig

    expected = AdminConfig.ADMIN_TOKEN
    if not expected or not x_admin_token or not hmac.compare_digest(x_admin_token, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin token")
