"""
Health Check Endpoint.

Simple endpoint to verify the API and database are running.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(session: AsyncSession = Depends(get_session)):
    """
    Health check endpoint.

    Verifies:
    - API is running
    - Database connection works

    Returns:
        JSON with status and database connectivity
    """
    # Test database connection
    await session.execute(text("SELECT 1"))

    return {
        "status": "healthy",
        "database": "connected",
    }
