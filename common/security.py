"""Authentication for every service.

Incoming: every request needs `Authorization: Bearer <token>`, except /health
and the public agent card. Three modes (A2A_AUTH_MODE):

    shared_secret  local development: one shared token
    entra          the app checks the Entra ID JWT itself (signature, audience, issuer)
    easy_auth      Azure Container Apps checks the token before the request
                   reaches us, and adds the X-MS-CLIENT-PRINCIPAL-ID header

Outgoing (service to service): the caller gets a token for its own managed
identity. No secrets are stored anywhere.
"""
import asyncio
import hmac

import jwt
from fastapi import Request
from fastapi.responses import JSONResponse

from common.config import settings

PUBLIC_PATHS = {"/health", "/.well-known/agent-card.json", "/docs", "/openapi.json"}

_jwks_client = None


async def require_bearer_token(request: Request, call_next):
    """FastAPI HTTP middleware: reject unauthenticated requests with 401."""
    if request.url.path in PUBLIC_PATHS or await is_authenticated(request):
        return await call_next(request)
    return JSONResponse(
        status_code=401,
        content={"detail": "Not authenticated"},
        headers={"WWW-Authenticate": "Bearer"},
    )


async def is_authenticated(request: Request) -> bool:
    mode = settings.a2a_auth_mode
    if mode == "easy_auth":
        return bool(request.headers.get("X-MS-CLIENT-PRINCIPAL-ID"))

    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        return False
    if mode == "shared_secret":
        return hmac.compare_digest(token, settings.a2a_shared_secret)
    try:
        await asyncio.to_thread(validate_entra_token, token)
        return True
    except (jwt.PyJWTError, OSError):
        return False


def validate_entra_token(token: str) -> dict:
    """Check the JWT signature against Entra's public keys, then audience and issuer."""
    global _jwks_client
    tenant = settings.a2a_entra_tenant_id
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(
            f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys"
        )
    signing_key = _jwks_client.get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=settings.a2a_entra_audience,
        issuer=f"https://login.microsoftonline.com/{tenant}/v2.0",
    )


async def get_outgoing_token() -> str:
    """Token this service sends when it calls another agent."""
    if settings.a2a_auth_mode == "shared_secret":
        return settings.a2a_shared_secret
    # Managed identity: Azure issues a short-lived token for the shared A2A API.
    from azure.identity import DefaultAzureCredential

    scope = f"{settings.a2a_entra_audience}/.default"
    token = await asyncio.to_thread(DefaultAzureCredential().get_token, scope)
    return token.token
