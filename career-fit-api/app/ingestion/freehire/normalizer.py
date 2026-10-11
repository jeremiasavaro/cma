"""
Freehire Normalizer - Pure functions mapping raw API job dicts to our models.

No I/O here. Every function tolerates missing/None/odd-typed keys (the payload
is loosely typed external data) and never raises on a weird record: a record
that can't be normalized comes back as (None, skip_reason) so the upserter can
count skips instead of aborting the batch.

Payload facts this mapping relies on (live-verified 2026-10-09):
- Identity: external_id (string, source-prefixed) or public_slug (stable).
- company is a flat string + company_slug; no nested company object.
- location is a flat string; countries/regions/cities are parallel arrays.
- skills: array of lowercase hyphenated strings, possibly empty.
- Salary lives ONLY under enrichment.salary_* and only once enriched_at is
  non-null; the enrichment object may contain any subset of keys.
"""

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit

# Column length limits from our models (see app/models/*.py).
_MAX_EXTERNAL_ID = 100
_MAX_TITLE = 500
_MAX_LOCATION = 200
_MAX_URL = 1000
_MAX_COMPANY_NAME = 300
_MAX_SKILL_NAME = 200

# Cap unique skills per record: unbounded arrays pollute the Skill table.
_MAX_SKILLS_PER_JOB = 50

# Plausibility bounds for annualized salary values (exclusive).
_MAX_ANNUAL_SALARY = Decimal(100_000_000)

# Multipliers converting a salary period to an annual figure.
_PERIOD_TO_ANNUAL = {
    "yearly": 1,
    "annual": 1,
    "year": 1,
    "monthly": 12,
    "month": 12,
    "weekly": 52,
    "week": 52,
    "daily": 260,
    "day": 260,
    "hourly": 2080,
    "hour": 2080,
}


@dataclass
class NormalizedCompany:
    """Company extracted from a job payload (flat string + slug only)."""

    external_id: str  # company_slug, falling back to a slug of the name
    name: str
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedSalaryObservation:
    """Salary mapped to our SalaryObservation columns (annualized values)."""

    min_salary: Decimal | None
    max_salary: Decimal | None
    median_salary: Decimal | None
    currency: str
    period: str
    source: str
    confidence: float
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedJob:
    """Job mapped to our Job columns."""

    external_id: str
    title: str
    description: str | None
    location: str | None
    work_mode: str | None
    posted_at: datetime | None
    source_url: str | None
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedRecord:
    """Everything the upserter needs for one job posting."""

    job: NormalizedJob
    company: NormalizedCompany | None
    skills: list[str]
    salary: NormalizedSalaryObservation | None


## AUXILIARY NORMALIZATION FUNCTIONS ##
def _clean_str(value: Any, max_len: int) -> str | None:
    """Coerce to a stripped, length-capped string; None for empty/non-string.

    NUL characters are stripped: Postgres rejects \\x00 in text and JSONB.
    """
    if not isinstance(value, str):
        return None
    stripped = value.replace("\x00", "").strip()
    if not stripped:
        return None
    return stripped[:max_len]


def _sanitize_json(value: Any) -> Any:
    """Recursively make a payload safe for JSONB: no NUL chars, no NaN/Inf."""
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {_sanitize_json(k): _sanitize_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_json(item) for item in value]
    return value


def _parse_datetime(value: Any) -> datetime | None:
    """Parse ISO8601 strings (with trailing Z) defensively; always tz-aware."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        # Columns are DateTime(timezone=True); keep everything aware (UTC).
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _to_decimal(value: Any) -> Decimal | None:
    """Coerce numbers (or numeric strings) to a plausible salary Decimal.

    Rejects (returns None) non-finite values and anything outside the
    (0, _MAX_ANNUAL_SALARY) range — posting-controlled strings like "NaN",
    "Infinity" or "1e999999" must never reach stats or the flush.
    """
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not result.is_finite():
        return None
    if result <= 0 or result >= _MAX_ANNUAL_SALARY:
        return None
    return result


## END AUXILIARY NORMALIZATION FUNCTIONS ##


## NORMALIZATION FUNCTIONS ##
def normalize_skills(raw_skills: Any) -> list[str]:
    """Clean a skills array into deduped, lowercase-hyphenated canonical names."""
    if not isinstance(raw_skills, list):
        return []
    seen: set[str] = set()  # Track canonical skill names to avoid duplicates.
    skills: list[str] = []  # Final list of normalized skills to return.
    for item in raw_skills:
        cleaned = _clean_str(item, _MAX_SKILL_NAME)
        if cleaned is None:
            continue
        # Arrive lowercase-hyphenated; enforce it so lookups stay consistent.
        canonical = cleaned.lower().replace(" ", "-")
        if canonical not in seen:
            seen.add(canonical)
            skills.append(canonical)
            if len(skills) >= _MAX_SKILLS_PER_JOB:
                break
    return skills


def _slugify(name: str) -> str:
    """Minimal slug for companies missing company_slug."""
    slug = "".join(ch if ch.isalnum() else "-" for ch in name.lower())
    return "-".join(part for part in slug.split("-") if part)[:_MAX_EXTERNAL_ID]


def normalize_company(raw: dict[str, Any]) -> NormalizedCompany | None:
    """Extract the company from a job payload; None when no usable name."""
    name = _clean_str(raw.get("company"), _MAX_COMPANY_NAME)
    if name is None:
        return None
    slug = _clean_str(raw.get("company_slug"), _MAX_EXTERNAL_ID) or _slugify(name)
    if not slug:
        return None
    return NormalizedCompany(
        external_id=slug,
        name=name,
        raw_data=_sanitize_json({"company": name, "company_slug": raw.get("company_slug")}),
    )


def normalize_salary(raw: dict[str, Any]) -> NormalizedSalaryObservation | None:
    """Build a salary observation from enrichment.salary_*, or None.

    Salary data only exists once enriched_at is non-null, and the enrichment
    bag may hold any subset of keys — every subkey is checked independently.

    Normalization decision (MVP): values are annualized by period multiplier
    but NOT currency-converted (no FX source yet). USD observations get
    confidence 1.0; non-USD keep their original currency code at confidence
    0.6; unknown periods are stored as-is at confidence 0.5.
    """
    if raw.get("enriched_at") is None:
        return None
    enrichment = raw.get("enrichment")
    if not isinstance(enrichment, dict):
        return None

    min_raw = _to_decimal(enrichment.get("salary_min"))
    max_raw = _to_decimal(enrichment.get("salary_max"))
    if min_raw is None and max_raw is None:
        return None

    currency = _clean_str(enrichment.get("salary_currency"), 3) or "USD"
    currency = currency.upper()
    period_raw = _clean_str(enrichment.get("salary_period"), 20) or "yearly"
    period = period_raw.lower()

    multiplier = _PERIOD_TO_ANNUAL.get(period)
    confidence = 1.0 if currency == "USD" else 0.6
    if multiplier is None:
        multiplier = 1  # Unknown period: store values as-is, flag low confidence.
        confidence = min(confidence, 0.5)

    min_salary = min_raw * multiplier if min_raw is not None else None
    max_salary = max_raw * multiplier if max_raw is not None else None
    if min_salary is not None and max_salary is not None:
        median = (min_salary + max_salary) / 2
    else:
        median = min_salary if min_salary is not None else max_salary

    return NormalizedSalaryObservation(
        min_salary=min_salary,
        max_salary=max_salary,
        median_salary=median,
        currency=currency,
        period=period,
        source="posted",
        confidence=confidence,
        raw_data=_sanitize_json(
            {
                "salary_min": enrichment.get("salary_min"),
                "salary_max": enrichment.get("salary_max"),
                "salary_currency": enrichment.get("salary_currency"),
                "salary_period": enrichment.get("salary_period"),
            }
        ),
    )


def _derive_work_mode(raw: dict[str, Any], location: str | None) -> str | None:
    """Best-effort work mode: the API has no explicit field, so infer from text."""
    candidates: list[str] = []
    enrichment = raw.get("enrichment")
    if isinstance(enrichment, dict):
        employment = enrichment.get("workplace_type") or enrichment.get("work_mode")
        if isinstance(employment, str):
            candidates.append(employment.lower())
    if location:
        candidates.append(location.lower())
    for text in candidates:
        if "remote" in text:
            return "remote"
        if "hybrid" in text:
            return "hybrid"
        if "onsite" in text or "on-site" in text:
            return "onsite"
    return None


def _is_http_url(url: str) -> bool:
    """Only http/https schemes are acceptable (rejects javascript:, data:, ...)."""
    try:
        return urlsplit(url).scheme in ("http", "https")
    except ValueError:
        return False


def _job_source_url(raw: dict[str, Any], slug: str | None) -> str | None:
    """Pick an explicit http(s) URL field if present, else build one from the slug."""
    for key in ("url", "apply_url", "source_url"):
        url = _clean_str(raw.get(key), _MAX_URL)
        if url is not None and _is_http_url(url):
            return url
    if slug:
        return f"https://freehire.me/jobs/{slug}"[:_MAX_URL]
    return None


## END NORMALIZATION FUNCTIONS ##


## MAIN ENTRY POINT ##
def normalize_job(raw: Any) -> tuple[NormalizedRecord | None, str | None]:
    """Map one raw Freehire job dict to a NormalizedRecord.

    Returns (record, None) on success or (None, skip_reason) when the record
    is unusable. Never raises on malformed input.
    """
    if not isinstance(raw, dict):
        return None, "not_a_dict"

    slug = _clean_str(raw.get("public_slug"), _MAX_EXTERNAL_ID)
    external_id = _clean_str(raw.get("external_id"), _MAX_EXTERNAL_ID) or slug
    if external_id is None:
        return None, "missing_identity"

    title = _clean_str(raw.get("title"), _MAX_TITLE)
    if title is None:
        return None, "missing_title"

    location = _clean_str(raw.get("location"), _MAX_LOCATION)

    job = NormalizedJob(
        external_id=external_id,
        title=title,
        # Description is deliberately NOT truncated (unlimited Text column; raw
        # descriptions are wanted) but must be NUL-free: Postgres rejects \x00.
        description=(
            raw["description"].replace("\x00", "")
            if isinstance(raw.get("description"), str)
            else None
        ),
        location=location,
        work_mode=_derive_work_mode(raw, location),
        posted_at=_parse_datetime(raw.get("posted_at")) or _parse_datetime(raw.get("created_at")),
        source_url=_job_source_url(raw, slug),
        raw_data=_sanitize_json(raw),
    )

    return (
        NormalizedRecord(
            job=job,
            company=normalize_company(raw),
            skills=normalize_skills(raw.get("skills")),
            salary=normalize_salary(raw),
        ),
        None,
    )
