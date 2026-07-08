import ssl

import httpx


async def fetch_bytes(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 120,
    allow_legacy_ssl: bool = False,
) -> bytes:
    verify: bool | ssl.SSLContext = True
    if allow_legacy_ssl:
        ctx = ssl.create_default_context()
        ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT
        verify = ctx

    async with httpx.AsyncClient(
        timeout=timeout,
        headers=headers,
        follow_redirects=True,
        verify=verify,
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.content
