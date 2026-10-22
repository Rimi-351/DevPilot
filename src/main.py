"""FastAPI Main Application Factory and Lifespan."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.v1.api import api_router
from src.core.config import settings
from src.core.database import engine
from src.core.exceptions import (
    DevPilotException,
    EntityConflictError,
    EntityNotFoundError,
    FileTooLargeError,
    UnsupportedFileExtensionError,
)
from src.core.security import is_demo_api_key


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager handling startup and shutdown events."""
    # Startup actions
    yield
    # Shutdown actions: gracefully close database connection pool
    await engine.dispose()


from pathlib import Path
from typing import Any

from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).parent / "static"
INDEX_HTML = STATIC_DIR / "index.html"


def create_application() -> FastAPI:
    """Instantiate and configure the FastAPI application."""
    openapi_tags = [
        {"name": "Health", "description": "Service health check and database connectivity probe."},
        {"name": "Projects", "description": "Multi-tenant project workspace management and lifecycle."},
        {"name": "Documents", "description": "Document upload, parsing, and chunking pipeline."},
        {"name": "Search", "description": "Hybrid dense-vector and BM25 sparse keyword retrieval with RRF."},
        {"name": "RAG", "description": "Grounded question answering with cross-encoder neural reranking and citation guardrails."},
        {"name": "Agent", "description": "Autonomous 4-phase bounded research agent FSM (SEARCH -> INSPECT -> SUMMARIZE -> PROPOSE)."},
        {"name": "Processing Jobs", "description": "Asynchronous background document ingestion status and lifecycle."},
        {"name": "UI", "description": "Single-Page Web UI dashboard."},
        {"name": "Root", "description": "Root service metadata and status."},
    ]

    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description="Production-grade multi-tenant cascading hybrid RAG platform with bounded agentic research FSM and active citation verification.",
        debug=settings.DEBUG,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        openapi_tags=openapi_tags,
    )

    # Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def demo_mode_guard_middleware(request: Request, call_next):
        """Enforce read-only demo mode: permit read/inference, block write mutations for demo keys."""
        api_key = request.headers.get("X-API-Key")
        if api_key and is_demo_api_key(api_key):
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                path = request.url.path
                is_safe_inference = (
                    path.endswith("/search")
                    or path.endswith("/rag")
                    or path.endswith("/agent/workflow")
                )
                if not is_safe_inference:
                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={
                            "detail": "Demo Mode: Write operations (create, update, delete) are disabled for demo credentials. Read-only access is granted for search, RAG, and document inspection."
                        },
                    )
        return await call_next(request)

    @app.exception_handler(EntityNotFoundError)
    async def entity_not_found_handler(request: Request, exc: EntityNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": exc.message, "details": exc.details},
        )

    @app.exception_handler(FileTooLargeError)
    async def file_too_large_handler(request: Request, exc: FileTooLargeError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            content={"detail": exc.message, "details": exc.details},
        )

    @app.exception_handler(UnsupportedFileExtensionError)
    async def unsupported_extension_handler(
        request: Request, exc: UnsupportedFileExtensionError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": exc.message, "details": exc.details},
        )

    @app.exception_handler(EntityConflictError)
    async def entity_conflict_handler(
        request: Request, exc: EntityConflictError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": exc.message, "details": exc.details},
        )

    @app.exception_handler(DevPilotException)
    async def devpilot_exception_handler(request: Request, exc: DevPilotException) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": exc.message, "details": exc.details},
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": str(exc)},
        )

    # Include Routers
    app.include_router(api_router, prefix=settings.API_V1_STR)

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/ui", response_class=HTMLResponse, tags=["UI"], summary="Web Dashboard UI")
    async def web_ui() -> HTMLResponse:
        """Serve the native bilingual single-page Web UI dashboard."""
        if INDEX_HTML.exists():
            return HTMLResponse(content=INDEX_HTML.read_text(encoding="utf-8"))
        return HTMLResponse(
            content="<h1>DevPilot UI</h1><p>index.html not found.</p>",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    @app.get("/openapi.json", include_in_schema=False)
    async def openapi_endpoint() -> JSONResponse:
        """Direct OpenAPI schema endpoint."""
        return JSONResponse(content=app.openapi())

    @app.get("/", tags=["Root"], summary="Application root status and discovery")
    async def root(request: Request) -> Any:
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            return RedirectResponse(url="/ui")
        return {
            "service": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "status": "online",
            "docs": "/docs",
            "ui": "/ui",
        }

    return app


app = create_application()
