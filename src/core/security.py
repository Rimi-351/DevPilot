"""Authentication and tenant security dependencies using X-API-Key."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from src.models.project import Project

logger = logging.getLogger(__name__)

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


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
