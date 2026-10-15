"""Gateway authentication and service-to-service tokens.

This file is the one the interviewer will probably ask about, so it is written to
show the *shape* of the production auth without needing any live Azure resources.

Two directions of trust:

1. Inbound (user -> orchestrator gateway):   OAuth2 Bearer / JWT.
   In production the token is an Entra ID (Azure AD) access token. Azure Container
   Apps "Easy Auth" can validate it at the edge; we ALSO validate in-app so the
   service is safe if it is ever reached directly. Validation = verify the RS256
   signature against the tenant JWKS, then check audience + issuer.

2. Service-to-service (orchestrator -> research agent, the A2A hop):
   the caller presents its OWN identity. In production that is a *managed identity*
   via DefaultAzureCredential — no secret is stored anywhere; Azure mints a token
   for the research agent's app registration.

For the local demo (AUTH_MODE=dev) both collapse to a single shared bearer token,
so you can run everything with no cloud dependencies. The production code paths are
present and commented, just not exercised offline.
"""
from __future__ import annotations

import asyncio

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from common.config import settings

_bearer = HTTPBearer(auto_error=True)


# --------------------------------------------------------------------------- #
# Inbound gateway auth
# --------------------------------------------------------------------------- #
def verify_bearer(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    """FastAPI dependency. Returns the validated principal (claims) or 401.

    Usage:  @app.post("/invoke", dependencies=[Depends(verify_bearer)])
    """
    return check_token(creds.credentials)


def check_token(token: str) -> dict:
    """The one place a bearer token is checked (dev token, or Entra JWT)."""
    if settings.auth_mode == "dev":
        if token != settings.dev_token:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid dev token")
        return {"sub": "dev-user", "mode": "dev"}

    # AUTH_MODE=entra — production path.
    return _validate_entra_jwt(token)


# The SDK mounts the A2A routes itself, so the agent app checks the token in a
# middleware instead of a per-route Depends. Same check, same 401.
PUBLIC_PATHS = {"/health", "/.well-known/agent-card.json"}   # the agent card must be public


async def require_bearer_token(request: Request, call_next):
    if request.url.path in PUBLIC_PATHS:
        return await call_next(request)
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    try:
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
        await asyncio.to_thread(check_token, token)
    except HTTPException as e:
        return JSONResponse(
            {"detail": e.detail}, status_code=e.status_code,
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await call_next(request)


def _validate_entra_jwt(token: str) -> dict:
    """Validate an Entra ID access token against the tenant JWKS.

    Requires the `azure` extra (PyJWT[crypto]). Kept out of the offline demo path.
    """
    try:
        import jwt
        from jwt import PyJWKClient
    except ImportError as e:  # pragma: no cover - prod-only dependency
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "entra auth requires the 'azure' extra (PyJWT[crypto])",
        ) from e

    tenant = settings.entra_tenant_id
    jwks_url = f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys"
    issuer = f"https://login.microsoftonline.com/{tenant}/v2.0"

    try:
        signing_key = PyJWKClient(jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.entra_api_audience,
            issuer=issuer,
        )
    except Exception as e:  # pragma: no cover - prod-only path
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {e}") from e

    return claims


# --------------------------------------------------------------------------- #
# Outbound service-to-service auth (the A2A hop)
# --------------------------------------------------------------------------- #
def get_service_token() -> str:
    """Token the orchestrator attaches when calling the research agent.

    dev   : shared bearer token.
    entra : managed identity — DefaultAzureCredential mints a token scoped to the
            research agent's app registration. No secret is stored by us.
    """
    if settings.auth_mode == "dev":
        return settings.dev_token

    # production path
    from azure.identity import DefaultAzureCredential  # pragma: no cover

    scope = f"{settings.research_agent_app_id_uri}/.default"
    cred = DefaultAzureCredential()
    return cred.get_token(scope).token


def auth_header() -> dict[str, str]:
    """Convenience: Authorization header for an outbound A2A call."""
    return {"Authorization": f"Bearer {get_service_token()}"}
