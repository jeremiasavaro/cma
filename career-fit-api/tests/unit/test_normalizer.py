"""Unit tests for app.ingestion.freehire.normalizer (pure functions, no I/O).

The normalizer is the trust boundary between the external Freehire payload
and our database: these tests protect the mapping rules (identity, salary
annualization) and the hardening behaviors (NUL stripping, hostile numbers,
caps, URL scheme filtering) that keep bad external data out of Postgres.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from app.ingestion.freehire.normalizer import (
    _sanitize_json,
    _to_decimal,
    normalize_job,
    normalize_skills,
)


def make_raw_job(**overrides: Any) -> dict[str, Any]:
    """A realistic enriched Freehire job payload (live-verified shape)."""
    raw: dict[str, Any] = {
        "external_id": "freehire_12345",
        "public_slug": "senior-backend-engineer-acme-12345",
        "title": "Senior Backend Engineer",
        "company": "Acme Corp",
        "company_slug": "acme-corp",
        "location": "Berlin, Germany",
        "skills": ["python", "postgresql", "docker"],
        "description": "Build and operate backend services.",
        "posted_at": "2026-10-08T12:00:00Z",
        "created_at": "2026-10-07T09:00:00Z",
        "enriched_at": "2026-10-09T01:00:00Z",
        "enrichment": {
            "salary_min": 7000,
            "salary_max": 9000,
            "salary_currency": "USD",
            "salary_period": "monthly",
        },
    }
    raw.update(overrides)
    return raw


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_normalize_job_happy_path() -> None:
    """A realistic enriched job maps to a complete NormalizedRecord.

    Protects the core field mapping end to end: identity, title, company
    slug identity, skill dedup and the monthly->annual salary conversion.
    """
    raw = make_raw_job(skills=["python", "Python", "postgresql", "docker "])

    record, reason = normalize_job(raw)

    assert reason is None
    assert record is not None
    assert record.job.external_id == "freehire_12345"
    assert record.job.title == "Senior Backend Engineer"
    assert record.job.location == "Berlin, Germany"
    assert record.job.posted_at == datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
    # No explicit URL field: the public_slug builds the canonical job URL.
    assert record.job.source_url == "https://freehire.me/jobs/senior-backend-engineer-acme-12345"

    assert record.company is not None
    assert record.company.external_id == "acme-corp"
    assert record.company.name == "Acme Corp"

    # Dedup is case-insensitive and whitespace-tolerant.
    assert record.skills == ["python", "postgresql", "docker"]

    assert record.salary is not None
    assert record.salary.min_salary == Decimal(84000)  # 7000 x 12
    assert record.salary.max_salary == Decimal(108000)  # 9000 x 12
    assert record.salary.median_salary == Decimal(96000)
    assert record.salary.currency == "USD"
    assert record.salary.period == "monthly"
    assert record.salary.confidence == 1.0


def test_identity_falls_back_to_public_slug() -> None:
    """When external_id is missing, public_slug is a valid stable identity."""
    raw = make_raw_job(external_id=None)

    record, reason = normalize_job(raw)

    assert reason is None
    assert record is not None
    assert record.job.external_id == "senior-backend-engineer-acme-12345"


def test_company_slug_falls_back_to_slugified_name() -> None:
    """A company without company_slug still gets a deterministic identity."""
    raw = make_raw_job(company="Globex & Söhne GmbH", company_slug=None)

    record, _ = normalize_job(raw)

    assert record is not None
    assert record.company is not None
    # Slug keeps alphanumerics (unicode included), hyphenates the rest.
    assert record.company.external_id == "globex-söhne-gmbh"
    assert record.company.name == "Globex & Söhne GmbH"


# ---------------------------------------------------------------------------
# Salary annualization and confidence tiers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("period", "expected_annual"),
    [
        ("yearly", Decimal(50)),
        ("annual", Decimal(50)),
        ("monthly", Decimal(600)),
        ("weekly", Decimal(2600)),
        ("daily", Decimal(13000)),
        ("hourly", Decimal(104000)),
    ],
)
def test_salary_annualization_per_period(period: str, expected_annual: Decimal) -> None:
    """Each salary period is annualized by its documented multiplier.

    Protects comparability: observations stored in the DB must all be on an
    annual basis regardless of how the posting expressed them.
    """
    raw = make_raw_job(
        enrichment={
            "salary_min": 50,
            "salary_max": 50,
            "salary_currency": "USD",
            "salary_period": period,
        }
    )

    record, _ = normalize_job(raw)

    assert record is not None
    assert record.salary is not None
    assert record.salary.min_salary == expected_annual
    assert record.salary.max_salary == expected_annual
    assert record.salary.median_salary == expected_annual


@pytest.mark.parametrize(
    ("currency", "period", "expected_confidence"),
    [
        ("USD", "yearly", 1.0),  # USD + known period: full confidence.
        ("EUR", "yearly", 0.6),  # Non-USD (no FX conversion yet): degraded.
        ("USD", "fortnightly", 0.5),  # Unknown period, stored as-is.
        ("EUR", "fortnightly", 0.5),  # Unknown period dominates non-USD.
    ],
)
def test_salary_confidence_tiers(currency: str, period: str, expected_confidence: float) -> None:
    """Confidence encodes how comparable the observation is to annual USD."""
    raw = make_raw_job(
        enrichment={
            "salary_min": 1000,
            "salary_max": 2000,
            "salary_currency": currency,
            "salary_period": period,
        }
    )

    record, _ = normalize_job(raw)

    assert record is not None
    assert record.salary is not None
    assert record.salary.confidence == expected_confidence
    assert record.salary.currency == currency


def test_unknown_period_stores_values_as_is() -> None:
    """Unknown periods must not be silently multiplied — stored unconverted."""
    raw = make_raw_job(
        enrichment={
            "salary_min": 1000,
            "salary_max": 2000,
            "salary_currency": "USD",
            "salary_period": "fortnightly",
        }
    )

    record, _ = normalize_job(raw)

    assert record is not None
    assert record.salary is not None
    assert record.salary.min_salary == Decimal(1000)
    assert record.salary.max_salary == Decimal(2000)


def test_salary_median_falls_back_to_single_bound() -> None:
    """With only one bound present, that bound becomes the median."""
    raw = make_raw_job(
        enrichment={"salary_min": 100000, "salary_currency": "USD", "salary_period": "yearly"}
    )

    record, _ = normalize_job(raw)

    assert record is not None
    assert record.salary is not None
    assert record.salary.min_salary == Decimal(100000)
    assert record.salary.max_salary is None
    assert record.salary.median_salary == Decimal(100000)


def test_unenriched_job_has_no_salary_observation() -> None:
    """Salary only exists under enrichment and only once enriched_at is set.

    An unenriched job must not produce an observation even if an enrichment
    bag is (unexpectedly) present — protects stats from premature data.
    """
    raw = make_raw_job(enriched_at=None)

    record, reason = normalize_job(raw)

    assert reason is None
    assert record is not None
    assert record.salary is None


# ---------------------------------------------------------------------------
# Skip paths: unusable records never raise
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected_reason"),
    [
        ("not a dict at all", "not_a_dict"),
        (None, "not_a_dict"),
        ({"title": "Engineer"}, "missing_identity"),  # No external_id nor slug.
        ({"external_id": "freehire_1", "title": "   "}, "missing_title"),
        ({"external_id": "freehire_1"}, "missing_title"),
    ],
)
def test_unusable_records_return_skip_reason(raw: Any, expected_reason: str) -> None:
    """Malformed records come back as (None, reason) so batches never abort."""
    record, reason = normalize_job(raw)

    assert record is None
    assert reason == expected_reason


# ---------------------------------------------------------------------------
# Hardening behaviors
# ---------------------------------------------------------------------------


def test_clean_str_strips_nul_characters() -> None:
    """NUL bytes are stripped from strings: Postgres rejects \\x00 in text."""
    raw = make_raw_job(title="Sen\x00ior Engineer")

    record, _ = normalize_job(raw)

    assert record is not None
    assert record.job.title == "Senior Engineer"


def test_description_nul_stripped_but_not_truncated() -> None:
    """Description is NUL-stripped (Postgres rejects \\x00) but never truncated.

    The Job.description column is unlimited Text and raw descriptions are
    wanted in full — only the NUL bytes must go.
    """
    raw = make_raw_job(description="A" * 600 + "\x00" + "B" * 600)

    record, _ = normalize_job(raw)

    assert record is not None
    assert record.job.description == "A" * 600 + "B" * 600


def test_title_truncated_to_column_limit() -> None:
    """Over-length values are truncated to the Job column limit (500 chars)."""
    raw = make_raw_job(title="T" * 600)

    record, _ = normalize_job(raw)

    assert record is not None
    assert len(record.job.title) == 500


@pytest.mark.parametrize(
    "hostile",
    ["NaN", "Infinity", "-Infinity", "1e999999", -50000, 0, 100_000_000, True, "garbage", None],
)
def test_to_decimal_rejects_hostile_values(hostile: Any) -> None:
    """Posting-controlled numbers outside (0, 1e8) or non-finite become None.

    These values must never reach salary stats or the DB flush: "1e999999"
    parses as a finite Decimal but is absurd, NaN/Infinity break aggregates.
    """
    assert _to_decimal(hostile) is None


@pytest.mark.parametrize(
    ("value", "expected"), [(50000, Decimal(50000)), ("50000.5", Decimal("50000.5"))]
)
def test_to_decimal_accepts_plausible_values(value: Any, expected: Decimal) -> None:
    assert _to_decimal(value) == expected


def test_skills_capped_and_deduped() -> None:
    """Unbounded skill arrays are capped at 50 to protect the Skill table."""
    raw_skills = [f"skill-{i}" for i in range(80)] + ["skill-0"]

    skills = normalize_skills(raw_skills)

    assert len(skills) == 50
    assert skills == [f"skill-{i}" for i in range(50)]


def test_skills_tolerate_junk_entries() -> None:
    """Non-string / empty entries are dropped instead of raising."""
    assert normalize_skills(["python", None, 42, "  ", {"x": 1}]) == ["python"]
    assert normalize_skills("not-a-list") == []


def test_javascript_source_url_rejected_https_kept() -> None:
    """Only http(s) source URLs are stored: javascript:/data: are dropped."""
    raw = make_raw_job(url="javascript:alert(1)", apply_url="https://jobs.example/apply")

    record, _ = normalize_job(raw)

    assert record is not None
    assert record.job.source_url == "https://jobs.example/apply"


def test_all_bad_urls_and_no_slug_gives_none() -> None:
    """With no acceptable URL and no slug, source_url stays empty."""
    raw = make_raw_job(public_slug=None, url="javascript:alert(1)", apply_url="data:text/html,x")

    record, _ = normalize_job(raw)

    assert record is not None
    assert record.job.source_url is None


def test_naive_datetime_becomes_utc_aware() -> None:
    """Naive timestamps are coerced to UTC: columns are timezone-aware."""
    raw = make_raw_job(posted_at="2026-10-08T12:00:00")  # No Z, no offset.

    record, _ = normalize_job(raw)

    assert record is not None
    assert record.job.posted_at == datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
    assert record.job.posted_at.tzinfo is not None


def test_raw_data_sanitized_for_jsonb() -> None:
    """normalize_job's raw_data is JSONB-safe: no NUL chars, no non-finite floats."""
    raw = make_raw_job(
        note="prefix\x00suffix",
        metrics={"score": float("inf"), "values": [float("nan"), "a\x00b"]},
    )

    record, _ = normalize_job(raw)

    assert record is not None
    assert record.job.raw_data["note"] == "prefixsuffix"
    assert record.job.raw_data["metrics"]["score"] is None
    assert record.job.raw_data["metrics"]["values"] == [None, "ab"]


def test_sanitize_json_cleans_nested_keys_and_values() -> None:
    """Direct check: NUL in dict keys and non-finite floats anywhere become safe."""
    dirty = {"k\x00ey": float("-inf"), "nested": [{"deep": float("nan")}]}

    assert _sanitize_json(dirty) == {"key": None, "nested": [{"deep": None}]}
