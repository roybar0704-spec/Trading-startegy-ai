"""Data-version helpers for RunIdentity (Stage A / B-1, D-067).

General-purpose, content-hash based -- distinct from TickParquetStore's and
DukascopyDownloader's narrower ``data_version()`` methods, which hash
pre-written ``.sha256`` sidecar files for a specific on-disk cache layout.
These take file paths or an in-memory tick sequence directly, so a
fixture/synthetic run (D-037) gets a real, reproducible ``data_version``
without anything needing to be written to disk first.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.core.types import Tick


def data_version_for_files(paths: list[Path]) -> str:
    """SHA256 of a canonical, path-sorted manifest of (relpath, content-sha256).

    ``paths`` should be stable/relative paths chosen by the caller (e.g. relative
    to a data root) so the hash doesn't embed machine-specific absolute prefixes.
    Input order doesn't matter -- the manifest is sorted before hashing.
    """
    manifest = sorted(
        (str(path), hashlib.sha256(Path(path).read_bytes()).hexdigest())
        for path in paths
    )
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def data_version_for_ticks(ticks: list[Tick]) -> str:
    """SHA256 of a canonical serialization of an in-memory tick sequence.

    Ticks are hashed in the order given -- callers pass them in a fixed, known
    order (e.g. already ts-sorted), so reordering is a genuine content change,
    not something this function treats as equivalent.
    """
    canonical = json.dumps(
        [[t.ts.isoformat(), t.bid, t.ask] for t in ticks],
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()
