"""
Main Application Entry Point.

FastAPI application factory with lifespan management, CORS, and routing.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import analyze, health
from app.config import get_settings
from app.database import close_db, init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    
    Runs on startup (before yield) and shutdown (after yield).
    """
    settings = get_settings()
    
    # Startup
    await init_db()
    
    yield
    
    # Shutdown
    await close_db()


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.
    
    Factory pattern allows creating app with different settings for tests.
    
    Returns:
        FastAPI: Configured application instance
    """
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        debug=settings.DEBUG,
        lifespan=lifespan,
        # Disable docs in production
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
    )

    # CORS Middleware - allows frontend to call API
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Restrict in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global exception handler - catches unhandled errors
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "message": str(exc) if settings.DEBUG else "An unexpected error occurred",
            },
        )

    # Include routers
    app.include_router(health.router, prefix=settings.API_PREFIX)
    app.include_router(analyze.router, prefix=settings.API_PREFIX)

    # Root endpoint
    @app.get("/", include_in_schema=False)
    async def root():
        return {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "docs": "/docs" if settings.DEBUG else "disabled",
            "health": f"{settings.API_PREFIX}/health",
        }

    return app


# Create app instance (imported by uvicorn)
app = create_app()