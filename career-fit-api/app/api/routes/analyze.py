"""
Analysis Endpoint.

Main endpoint: POST /v1/analyze
Receives CV + target role, returns market analysis.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.request import AnalyzeRequest
from app.api.schemas.response import AnalyzeResponse
from app.database import get_session

router = APIRouter(tags=["analysis"])


@router.post("/analyze", response_model=AnalyzeResponse, status_code=status.HTTP_200_OK)
async def analyze_cv(
    request: AnalyzeRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Analyze a CV against a target role using market data.
    
    This is the main endpoint. It:
    1. Parses CV to structured profile (LLM)
    2. Normalizes target role
    3. Queries market data for target role
    4. Calculates market fit score
    5. Identifies skill gaps
    6. Estimates salary
    7. Finds unlocked opportunities
    
    Args:
        request: CV text + target role + analysis config
        session: Database session
        
    Returns:
        Complete analysis response
        
    Raises:
        HTTPException: If analysis fails
    """
    # TODO: Implement full analysis pipeline
    # For now, return a placeholder response
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Analysis pipeline not implemented yet. TODO: implement in services layer.",
    )