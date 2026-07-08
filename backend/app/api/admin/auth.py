from fastapi import Header, HTTPException, status

from app.core.config import get_settings


async def require_admin_api_key(x_admin_api_key: str | None = Header(default=None)) -> None:
    expected = get_settings().admin_api_key
    if not expected or x_admin_api_key != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin API key")
