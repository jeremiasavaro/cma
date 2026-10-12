"""
Manual ingestion CLI - run one Freehire ingestion cycle by hand.

Wraps `run_ingestion_cycle()` (the same entry point the daily scheduler uses)
behind argparse flags, so you can pull a custom slice of jobs into the local
database without waiting for the 3 AM UTC run:

    uv run python scripts/ingest.py --skills python,fastapi --days 7 -v

The heavy lifting (HTTP client, normalization, upsert, snapshot, commit) all
lives in app/ingestion/ — this script only translates flags into search
params, configures console logging (scripts own their logging setup; app
modules never call basicConfig), runs the cycle, and prints the final
IngestionStats summary. Exit code 0 on success, 1 on failure.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

# Allow running as a plain script (`python scripts/ingest.py`): Python puts
# scripts/ on sys.path, not the project root, so `import app` needs this.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ingestion.freehire.scheduler import run_ingestion_cycle  # noqa: E402
from app.ingestion.freehire.upserter import IngestionStats  # noqa: E402

logger = logging.getLogger("scripts.ingest")


def build_parser() -> argparse.ArgumentParser:
    """The CLI surface: filters for the Freehire search plus run controls."""
    parser = argparse.ArgumentParser(
        prog="ingest.py",
        description="Run one Freehire ingestion cycle by hand (fetch -> normalize -> upsert).",
    )
    parser.add_argument("--q", help="Full-text query (e.g. 'backend engineer')")
    parser.add_argument(
        "--skills",
        help="Comma-separated skills filter, OR logic (e.g. python,fastapi)",
    )
    parser.add_argument(
        "--country",
        action="append",
        default=[],
        metavar="XX",
        help="Country code filter; repeatable and/or comma-separated (e.g. --country US,AR)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=2,
        help="Only jobs posted within the last N days (default: 2, same as the scheduler)",
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=500,
        help="Stop after ingesting this many jobs (default: 500)",
    )
    parser.add_argument(
        "--no-snapshot",
        action="store_true",
        help="Skip creating/updating the daily market snapshot at the end",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="DEBUG-level logging (shows pagination and upsert details)",
    )
    return parser


def _split_csv(values: list[str]) -> list[str]:
    """Flatten repeatable comma-separated flags into a clean list of tokens."""
    return [token.strip() for value in values for token in value.split(",") if token.strip()]


def build_search_params(args: argparse.Namespace) -> dict[str, Any]:
    """Translate parsed CLI flags into FreehireClient search params.

    Pure function (no I/O) so it can be unit-tested. Mirrors the scheduler's
    defaults (recent-first ordering, posted_within_days window) and only adds
    optional filters that were actually given — never None-valued keys.
    """
    params: dict[str, Any] = {
        "posted_within_days": args.days,
        "sort": "posted_at",
        "order": "desc",
    }
    if args.q:
        params["q"] = args.q
    skills = _split_csv([args.skills] if args.skills else [])
    if skills:
        params["skills"] = skills
    countries = _split_csv(args.country)
    if countries:
        params["countries"] = countries
    return params


def format_stats(stats: IngestionStats) -> str:
    """Human-readable summary of an ingestion run for the console."""
    lines = [
        "Ingestion finished:",
        f"  jobs inserted:     {stats.jobs_inserted}",
        f"  jobs updated:      {stats.jobs_updated}",
        f"  jobs skipped:      {stats.jobs_skipped}",
        f"  companies created: {stats.companies_created}",
        f"  skills created:    {stats.skills_created}",
        f"  salaries upserted: {stats.salaries_upserted}",
    ]
    if stats.skip_reasons:
        reasons = ", ".join(f"{reason}={count}" for reason, count in stats.skip_reasons.items())
        lines.append(f"  skip reasons:      {reasons}")
    return "\n".join(lines)


def _configure_logging(verbose: bool) -> None:
    """Console logging for the whole pipeline; -v flips it to DEBUG."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    """Parse flags, run one ingestion cycle, print the summary.

    Returns the process exit code: 0 on success, 1 on any failure.
    """
    args = build_parser().parse_args(argv)
    _configure_logging(args.verbose)

    search_params = build_search_params(args)
    logger.info("Running manual ingestion with params=%s max_jobs=%d", search_params, args.max_jobs)

    try:
        stats = asyncio.run(
            run_ingestion_cycle(
                search_params=search_params,
                max_jobs=args.max_jobs,
                create_snapshot=not args.no_snapshot,
            )
        )
    except Exception as exc:
        logger.exception("Ingestion cycle failed")
        print(f"Ingestion failed: {exc}", file=sys.stderr)  # noqa: T201
        return 1

    print(format_stats(stats))  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
