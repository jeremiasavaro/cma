"""Unit tests for scripts/ingest.py (the manual ingestion CLI).

Three layers, none touching the network or a database:
- build_search_params: pure flag -> search-params mapping (defaults, CSV
  splitting, and that omitted flags never leak None-valued keys).
- argparse: invalid input fails cleanly with the standard usage-error exit.
- main(): orchestration against a monkeypatched run_ingestion_cycle — the CLI
  must forward the right kwargs, print a readable summary, and map
  success/failure to exit codes 0/1.
"""

import pytest

from app.ingestion.freehire.upserter import IngestionStats
from scripts import ingest


def parse(argv: list[str]):
    """Parse argv through the real CLI parser."""
    return ingest.build_parser().parse_args(argv)


# --- build_search_params -----------------------------------------------------


def test_defaults_match_scheduler_window() -> None:
    """No flags = the scheduler's daily incremental query (2 days, recent first)."""
    params = ingest.build_search_params(parse([]))

    assert params == {"posted_within_days": 2, "sort": "posted_at", "order": "desc"}


def test_omitted_options_are_absent_not_none() -> None:
    """Optional filters never appear as None-valued keys (client treats keys as set)."""
    params = ingest.build_search_params(parse([]))

    assert "q" not in params
    assert "skills" not in params
    assert "countries" not in params


def test_q_maps_to_full_text_query() -> None:
    params = ingest.build_search_params(parse(["--q", "backend engineer"]))

    assert params["q"] == "backend engineer"


def test_skills_comma_splitting() -> None:
    """--skills A,B,C becomes a clean list (whitespace and empties dropped)."""
    params = ingest.build_search_params(parse(["--skills", "python, fastapi,,sql "]))

    assert params["skills"] == ["python", "fastapi", "sql"]


def test_country_repeatable_and_comma_separated() -> None:
    """--country combines repeated flags and comma-separated values into one list."""
    params = ingest.build_search_params(parse(["--country", "US,AR", "--country", "DE"]))

    assert params["countries"] == ["US", "AR", "DE"]


def test_days_maps_to_posted_within_days() -> None:
    params = ingest.build_search_params(parse(["--days", "7"]))

    assert params["posted_within_days"] == 7


# --- argument parsing errors -------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        ["--max-jobs", "lots"],
        ["--days", "two"],
        ["--unknown-flag"],
    ],
)
def test_invalid_arguments_exit_with_usage_error(argv: list[str], capsys) -> None:
    """Bad input fails fast with argparse's standard exit code 2, not a traceback."""
    with pytest.raises(SystemExit) as excinfo:
        parse(argv)

    assert excinfo.value.code == 2
    assert "usage" in capsys.readouterr().err


# --- main() orchestration ----------------------------------------------------


def test_main_forwards_params_and_prints_summary(monkeypatch, capsys) -> None:
    """main() passes flags through to run_ingestion_cycle and reports the stats."""
    captured: dict = {}

    async def fake_cycle(**kwargs):
        captured.update(kwargs)
        return IngestionStats(jobs_inserted=3, jobs_updated=1, skip_reasons={"missing_title": 2})

    monkeypatch.setattr(ingest, "run_ingestion_cycle", fake_cycle)

    exit_code = ingest.main(
        ["--skills", "python,sql", "--days", "5", "--max-jobs", "42", "--no-snapshot"]
    )

    assert exit_code == 0
    assert captured["search_params"] == {
        "posted_within_days": 5,
        "sort": "posted_at",
        "order": "desc",
        "skills": ["python", "sql"],
    }
    assert captured["max_jobs"] == 42
    assert captured["create_snapshot"] is False

    out = capsys.readouterr().out
    assert "jobs inserted:     3" in out
    assert "jobs updated:      1" in out
    assert "missing_title=2" in out


def test_main_defaults_enable_snapshot_and_cap_jobs(monkeypatch) -> None:
    """Without flags the CLI keeps the snapshot and the default 500-job cap."""
    captured: dict = {}

    async def fake_cycle(**kwargs):
        captured.update(kwargs)
        return IngestionStats()

    monkeypatch.setattr(ingest, "run_ingestion_cycle", fake_cycle)

    assert ingest.main([]) == 0
    assert captured["max_jobs"] == 500
    assert captured["create_snapshot"] is True


def test_main_failure_returns_nonzero(monkeypatch, capsys) -> None:
    """An exception from the cycle becomes exit code 1 with an error message."""

    async def failing_cycle(**kwargs):
        raise RuntimeError("DB is down")

    monkeypatch.setattr(ingest, "run_ingestion_cycle", failing_cycle)

    exit_code = ingest.main([])

    assert exit_code == 1
    assert "Ingestion failed: DB is down" in capsys.readouterr().err


# --- format_stats ------------------------------------------------------------


def test_format_stats_without_skips_omits_reasons_line() -> None:
    text = ingest.format_stats(IngestionStats(jobs_inserted=10))

    assert "jobs inserted:     10" in text
    assert "skip reasons" not in text
