"""
Freehire Ingestion - Fetch, normalize and upsert job postings from Freehire.

Pipeline: FreehireClient (HTTP) -> normalizer (pure mapping) -> FreehireUpserter
(DB writes via repositories) -> SnapshotManager (daily aggregates).
"""

from app.ingestion.freehire.client import FreehireAPIError, FreehireClient, FreehirePage
from app.ingestion.freehire.normalizer import normalize_job
from app.ingestion.freehire.upserter import FreehireUpserter, IngestionStats

__all__ = [
    "FreehireAPIError",
    "FreehireClient",
    "FreehirePage",
    "FreehireUpserter",
    "IngestionStats",
    "normalize_job",
]
