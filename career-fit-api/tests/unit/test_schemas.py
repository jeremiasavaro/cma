"""Unit tests for Pydantic request schemas and CV service schemas."""

import pytest
from pydantic import ValidationError

from app.api.schemas.request import AnalyzeRequest, TargetRole
from app.services.cv.schemas import UserProfile
from tests.fixtures import SAMPLE_CV_TEXT


def test_analyze_request_valid() -> None:
    request = AnalyzeRequest(
        cv=SAMPLE_CV_TEXT,
        target=TargetRole(role="Senior Backend Engineer"),
    )

    assert request.target.role == "Senior Backend Engineer"
    assert request.analysis.level == "full"


def test_analyze_request_invalid_cv_too_short() -> None:
    with pytest.raises(ValidationError):
        AnalyzeRequest(
            cv="too short",
            target=TargetRole(role="Senior Backend Engineer"),
        )


def test_user_profile_valid_minimal() -> None:
    profile = UserProfile(seniority="senior")

    assert profile.seniority == "senior"
    assert profile.skills == []
    assert profile.management_experience is False


def test_user_profile_missing_required_field() -> None:
    with pytest.raises(ValidationError):
        UserProfile()
