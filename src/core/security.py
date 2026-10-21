"""Authentication and tenant security dependencies using X-API-Key."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from src.core.config import settings
from src.models.project import Project

logger = logging.getLogger(__name__)

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

DEMO_FALLBACK_KEYS = {"demo-readonly-key", "demo-api-key"}


def is_demo_api_key(api_key: Optional[str]) -> bool:
    """Check if the provided API key matches the configured demo credentials."""
    if not settings.DEMO_MODE or not api_key:
        return False
    key = api_key.strip()
    configured_key = (settings.DEMO_API_KEY or "").strip()
    return bool(
        (configured_key and key == configured_key)
        or key in DEMO_FALLBACK_KEYS
    )


def enforce_read_only_demo_guard(api_key: str) -> None:
    """Enforces that write mutations (create/update/delete) are forbidden for demo credentials.

    Raises:
        HTTPException (403): If the caller is using demo credentials on a mutation endpoint.
    """
    if is_demo_api_key(api_key):
        logger.warning("Rejected write mutation attempt from demo API key '%s'", api_key)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo Mode: Write operations (create, update, delete) are disabled for demo credentials. Read-only access is granted for search, RAG, and document inspection.",
        )


async def get_current_api_key(
    api_key: Optional[str] = Security(api_key_header),
) -> str:
    """Validate and extract the caller's API key from the X-API-Key header.

    Returns:
        str: Validated API key string identifying the caller's tenant.

    Raises:
        HTTPException (401): If the header is missing, empty, or whitespace.
    """
    if not api_key or not api_key.strip():
        logger.warning("Unauthorized access attempt: Missing or empty %s header", API_KEY_NAME)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Missing or invalid API key in {API_KEY_NAME} header.",
            headers={"WWW-Authenticate": API_KEY_NAME},
        )
    return api_key.strip()


async def get_current_tenant(
    api_key: Optional[str] = Security(api_key_header),
) -> str:
    """Validate and extract the caller's tenant identifier from the X-API-Key header.

    Alias for get_current_api_key ensuring semantic clarity for tenant-scoped operations.
    """
    return await get_current_api_key(api_key)


def verify_project_tenant_access(project: Project, current_api_key: str) -> None:
    """Enforce tenant isolation on a project entity.

    Args:
        project: The Project ORM entity being accessed.
        current_api_key: The authenticated API key of the caller.

    Raises:
        HTTPException (403): If the project belongs to another tenant.
    """
    owner = project.tenant_id or project.owner_api_key
    # If the project is claimed by an owner, ensure the caller matches
    if owner and owner != current_api_key:
        # In Demo Mode, callers using the demo API key are allowed read access to the demo workspace
        if is_demo_api_key(current_api_key) and (
            project.name == "DevPilot Evaluation Workspace"
            or owner in (settings.DEMO_API_KEY, "devpilot-demo-key", "demo-readonly-key")
        ):
            return

        logger.warning(
            "Forbidden cross-tenant access: Caller '%s' attempted accessing project '%s' owned by '%s'",
            current_api_key,
            project.id,
            owner,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to access this project.",
        )
