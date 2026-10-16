"""Project management REST endpoints."""

import math
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
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
    db: AsyncSession = Depends(get_db),
) -> Project:
    """Create a new project entity."""
    project = Project(
        name=project_in.name,
        description=project_in.description,
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
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Retrieve paginated list of projects ordered by creation date."""
    offset = (page - 1) * page_size

    total_query = select(func.count()).select_from(Project)
    total_result = await db.execute(total_query)
    total = total_result.scalar_one()

    query = (
        select(Project)
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
    db: AsyncSession = Depends(get_db),
) -> Project:
    """Retrieve a single project by its UUID."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found.",
        )
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
    db: AsyncSession = Depends(get_db),
) -> Project:
    """Partially update an existing project."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found.",
        )

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
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a project and cascade delete associated documents and jobs."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found.",
        )
    await db.delete(project)
