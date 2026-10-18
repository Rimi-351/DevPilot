"""Project management REST endpoints."""

import math
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import get_current_api_key, verify_project_tenant_access
from src.models.project import Project
from src.schemas.common import PaginatedResponse
from src.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate

router = APIRouter()


@router.post(
    "",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new Project",
)
async def create_project(
    project_in: ProjectCreate,
    api_key: str = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> Project:
    """Create a new project entity with tenant ownership."""
    project = Project(
        name=project_in.name,
        description=project_in.description,
        tenant_id=api_key,
        owner_api_key=api_key,
    )
    db.add(project)
    await db.flush()
    await db.refresh(project)
    return project


@router.get(
    "",
    response_model=PaginatedResponse[ProjectRead],
    status_code=status.HTTP_200_OK,
    summary="List Projects with pagination",
)
async def list_projects(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    api_key: str = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Retrieve paginated list of projects belonging to the authenticated tenant."""
    offset = (page - 1) * page_size

    # Filter projects for the current tenant or legacy unclaimed projects
    tenant_filter = (Project.tenant_id == api_key) | (Project.owner_api_key == api_key) | (Project.tenant_id.is_(None))

    total_query = select(func.count()).select_from(Project).where(tenant_filter)
    total_result = await db.execute(total_query)
    total = total_result.scalar_one()

    query = (
        select(Project)
        .where(tenant_filter)
        .order_by(Project.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(query)
    items = result.scalars().all()

    total_pages = math.ceil(total / page_size) if total > 0 else 0

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


@router.get(
    "/{project_id}",
    response_model=ProjectRead,
    status_code=status.HTTP_200_OK,
    summary="Get Project by ID",
)
async def get_project(
    project_id: UUID,
    api_key: str = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> Project:
    """Retrieve a single project by its UUID with tenant isolation."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found.",
        )
    verify_project_tenant_access(project, api_key)
    return project


@router.patch(
    "/{project_id}",
    response_model=ProjectRead,
    status_code=status.HTTP_200_OK,
    summary="Update Project",
)
async def update_project(
    project_id: UUID,
    project_in: ProjectUpdate,
    api_key: str = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> Project:
    """Partially update an existing project with tenant access check."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found.",
        )
    verify_project_tenant_access(project, api_key)

    update_data = project_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)

    await db.flush()
    await db.refresh(project)
    return project


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Project",
)
async def delete_project(
    project_id: UUID,
    api_key: str = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a project with tenant isolation check."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found.",
        )
    verify_project_tenant_access(project, api_key)
    await db.delete(project)
