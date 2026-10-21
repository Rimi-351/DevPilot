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


class DevPilotFastAPI(FastAPI):
    """FastAPI subclass providing flattened routes inspection for test and tooling compatibility."""

    @property
    def routes(self):
        flat = []
        for r in self.router.routes:
            if hasattr(r, "effective_route_contexts"):
                for rc in r.effective_route_contexts():
                    flat.append(rc)
            else:
                flat.append(r)
        return flat


def create_application() -> FastAPI:
    """Instantiate and configure the FastAPI application."""
    app = DevPilotFastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        debug=settings.DEBUG,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
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

    @app.exception_handler(DevPilotException)
    async def devpilot_exception_handler(request: Request, exc: DevPilotException) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": exc.message, "details": exc.details},
        )

    # Include Routers
    app.include_router(api_router, prefix=settings.API_V1_STR)

    @app.get("/", tags=["Root"])
    async def root() -> dict[str, str]:
        return {
            "service": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "status": "online",
            "docs": "/docs",
        }

    return app


app = create_application()
