"""
Skill Normalizer - Maps raw/free-text skill names to the canonical skills taxonomy.

Used by CVExtractor.normalize_skills() to turn whatever text the LLM extracted
from a CV into the canonical skill names stored in the `skills` DB table.
"""


class SkillNormalizer:
    """Normalizes raw skill names against the `skills` taxonomy table.

    MVP: exact/alias lookup against the skills table.
    Later: fuzzy matching / embeddings for near-miss names.
    """

    def __init__(self) -> None:
        # TODO: inject a skills repository once app.repositories exists, e.g.
        # def __init__(self, skills_repository: SkillsRepository) -> None:
        #     self._skills_repository = skills_repository
        ...

    async def normalize(self, raw_name: str) -> str | None:
        """Normalize a single raw skill name to its canonical form.

        Args:
            raw_name: Skill name as extracted from free text (unnormalized).

        Returns:
            Canonical skill name if a match is found, otherwise None.
        """
        # TODO: look up raw_name (case-insensitive, trimmed) against skills.name
        #       and skills.aliases via app.repositories (not yet created)
        # TODO: consider fuzzy matching (e.g. rapidfuzz) for near-miss names
        ...
