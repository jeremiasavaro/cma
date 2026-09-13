"""
LLM Prompts - Templates for prompts sent to the LLM.

Keeping prompt text separate from client/business logic makes it easier to
iterate on prompts without touching the calling code.
"""

# TODO: write the actual system/user prompt for CV -> structured profile extraction.
# Should instruct the model to return JSON matching app.services.cv.schemas.UserProfile.
CV_EXTRACTION_PROMPT_TEMPLATE = ""

# TODO: write the actual prompt for mapping raw/free-text skill names to the
# canonical skills taxonomy (used by CVExtractor.normalize_skills).
SKILL_NORMALIZATION_PROMPT_TEMPLATE = ""


def build_cv_extraction_prompt(cv_text: str) -> list[dict]:
    """Build the chat messages used to extract a structured profile from a CV.

    Args:
        cv_text: Raw CV text pasted by the user.

    Returns:
        List of chat messages (system + user) ready to pass to LLMClient.complete()
        or LLMClient.structured_output().
    """
    # TODO: fill in CV_EXTRACTION_PROMPT_TEMPLATE and format it with cv_text.
    # TODO: decide whether to include few-shot examples for better extraction quality.
    ...


def build_skill_normalization_prompt(raw_skills: list[str]) -> list[dict]:
    """Build the chat messages used to normalize a list of raw skill names.

    Args:
        raw_skills: Skill names as extracted from free text (unnormalized).

    Returns:
        List of chat messages ready to pass to LLMClient.structured_output().
    """
    # TODO: fill in SKILL_NORMALIZATION_PROMPT_TEMPLATE and format it with raw_skills.
    # TODO: decide whether to pass the known skills taxonomy as context for matching.
    ...
