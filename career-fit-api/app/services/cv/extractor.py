"""
CV Extractor - Converts raw CV text into a structured user profile.

MVP: LLM extraction + dictionary normalization against the skills taxonomy.
Later: NER, embeddings, or a specialized extraction model.
"""

from app.services.cv.schemas import Skill, UserProfile


class CVExtractor:
    """Extracts a structured profile from CV text.

    MVP: LLM + dictionary normalization.
    Later: NER, embeddings, specialized extraction model.
    """

    async def extract(self, cv_text: str) -> UserProfile:
        """Parse CV text into a structured UserProfile.

        Args:
            cv_text: Raw CV text (any format the user pastes).

        Returns:
            UserProfile with skills, experience, roles, education,
            languages, seniority, industries, management_experience.
        """
        # TODO: build the extraction prompt via app.services.llm.prompts.build_cv_extraction_prompt
        # TODO: call LLMClient.structured_output() with a JSON schema matching UserProfile
        # TODO: call self.normalize_skills() on the raw extracted skill names
        # TODO: handle edge cases: no skills found, ambiguous seniority, missing sections
        ...

    async def normalize_skills(self, raw_skills: list[str]) -> list[Skill]:
        """Map extracted skill names to the normalized skills taxonomy.

        Uses the skills table as a dictionary for canonical names.

        Args:
            raw_skills: Skill names as extracted from free text (unnormalized).

        Returns:
            List of Skill objects with canonical names.
        """
        # TODO: integrate app.services.cv.normalizer to match raw names against
        # the `skills` table (exact match, alias match, fuzzy match)
        # TODO: fall back to LLM-based normalization for unmatched names
        # TODO: decide how to handle skills that cannot be normalized at all
        ...
