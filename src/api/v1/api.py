"""API v1 Router aggregator."""

from fastapi import APIRouter

from src.api.v1.endpoints import documents, health, jobs, projects

api_router = APIRouter()

api_router.include_router(health.router, tags=["Health"])
api_router.include_router(projects.router, prefix="/projects", tags=["Projects"])
api_router.include_router(documents.router, prefix="/documents", tags=["Documents"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["Processing Jobs"])
